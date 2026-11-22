"""领料单配料、实发与周领用核清。

关键口径
--------
- 提交领料单只做「配料占用」（reservation），不直接扣库存；配额不足即为缺口。
- 配料优先让尽可能多的领料单整单领齐；同等单数时先到先得。
- 领料（issue）把占用转为实发记录并扣减现存；已发数量不可回退。
- 盘点把现存校正为实盘值，然后只重排未领部分；旧单仍可查到当前可领数量。
- 同一 request_key 的重试返回原单，不重复占用。
- 同一周同一规格的实发记录在核清时合并写入周领用；未核清的周保持缺传。
"""

import threading
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from src.constants.enums import RequisitionStatus
from src.models.entities import (
    FulfillmentLock, Issue, Reconciliation, Requisition, RequisitionLine, Reservation, Sleeve, Stock,
    Usage, Workstation,
)
from src.services import allocation
from src.services.business import audit

# 同一进程内的串行化；跨进程由数据库单行锁保证。
_LOCK = threading.RLock()
LOCK_ID = 1


def ensure_lock_row(db):
    """确保配料锁行存在；由启动流程调用，避免首次并发提交时争抢插入。"""
    if db.scalar(select(FulfillmentLock).where(FulfillmentLock.id == LOCK_ID)) is None:
        db.add(FulfillmentLock(id=LOCK_ID))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def lock_stock(db):
    """取得配料全局锁：单行 FOR UPDATE，确保并发提交/实发/盘点串行。"""
    query = select(FulfillmentLock).where(FulfillmentLock.id == LOCK_ID).with_for_update()
    row = db.scalar(query)
    if row is None:
        try:
            with db.begin_nested():
                db.add(FulfillmentLock(id=LOCK_ID))
        except IntegrityError:
            pass
        row = db.scalar(query)
    return row


def mark_pending_week(db, sleeve_code, week):
    """发生实发但尚未核清的周，在周领用里保持缺传，避免被当作零领用。"""
    row = db.scalar(select(Usage).where(Usage.sleeve_code == sleeve_code, Usage.week == week))
    if row is None:
        db.add(Usage(sleeve_code=sleeve_code, week=week, state='missing', units=None))
    elif row.state == 'observed':
        # 已核清的周又发生实发，需重新核清；在核清前仍按缺传处理。
        row.state, row.units = 'missing', None
    db.flush()


def _stock_map(db):
    return {row.sleeve_code: row.on_hand for row in db.scalars(select(Stock).order_by(Stock.sleeve_code))}


def _substitute_map(db):
    return {sleeve.code: sleeve.substitute_code
            for sleeve in db.scalars(select(Sleeve))
            if sleeve.substitute_code}


def _reserved_by_spec(db):
    reserved = defaultdict(int)
    for spec, units in db.execute(select(Reservation.sleeve_code, func.sum(Reservation.units))
                                  .group_by(Reservation.sleeve_code)).all():
        reserved[spec] = int(units or 0)
    return reserved


def replan(db):
    """重排所有未领齐领料单的占用。调用方需已持有库存锁并在同一事务内提交。"""
    stock = _stock_map(db)
    substitutes = _substitute_map(db)
    requisitions = list(db.scalars(
        select(Requisition).where(Requisition.status != RequisitionStatus.ISSUED)
        .order_by(Requisition.created_at, Requisition.id)))
    demands, line_by_key = [], {}
    for requisition in requisitions:
        remaining_lines = [(line.sleeve_code, line.requested_units - line.issued_units)
                           for line in requisition.lines
                           if line.requested_units - line.issued_units > 0]
        if not remaining_lines:
            requisition.status = RequisitionStatus.ISSUED
            continue
        demands.append({'id': requisition.id, 'lines': remaining_lines})
        for line in requisition.lines:
            line_by_key[(requisition.id, line.sleeve_code)] = line

    open_ids = [requisition.id for requisition in requisitions]
    if open_ids:
        db.execute(delete(Reservation).where(Reservation.requisition_id.in_(open_ids)))

    allocations, _ = allocation.plan(demands, stock, substitutes)
    for demand in demands:
        requisition = next(item for item in requisitions if item.id == demand['id'])
        by_code = allocations.get(requisition.id, {})
        allocated_total = 0
        for code, _ in demand['lines']:
            line = line_by_key[(requisition.id, code)]
            per_spec = by_code.get(code, {})
            for spec, units in per_spec.items():
                if units <= 0:
                    continue
                db.add(Reservation(requisition_id=requisition.id, requisition_line_id=line.id,
                                   sleeve_code=spec, units=units))
                allocated_total += units
        remaining_total = sum(units for _, units in demand['lines'])
        requisition.status = (RequisitionStatus.READY if allocated_total == remaining_total
                              else RequisitionStatus.SHORT)
    db.flush()


def _line_view(line, reservations):
    remaining = line.requested_units - line.issued_units
    reserved = sum(row.units for row in reservations)
    return {
        'sleeve_code': line.sleeve_code,
        'requested_units': line.requested_units,
        'issued_units': line.issued_units,
        'remaining_units': remaining,
        'reserved_units': reserved,
        'shortage_units': max(remaining - reserved, 0),
        'allocation': [{'sleeve_code': row.sleeve_code, 'units': row.units}
                       for row in sorted(reservations, key=lambda item: item.sleeve_code)],
    }


def requisition_view(db, requisition):
    reservations = defaultdict(list)
    for row in db.scalars(select(Reservation).where(Reservation.requisition_id == requisition.id)):
        reservations[row.requisition_line_id].append(row)
    lines = [_line_view(line, reservations.get(line.id, [])) for line in requisition.lines]
    return {
        'id': requisition.id,
        'workstation_code': requisition.workstation.code,
        'workstation_title': requisition.workstation.title,
        'week': requisition.week.isoformat(),
        'status': requisition.status,
        'request_key': requisition.request_key,
        'note': requisition.note,
        'created_at': requisition.created_at.isoformat() if requisition.created_at else None,
        'lines': lines,
        'totals': {
            'requested_units': sum(line['requested_units'] for line in lines),
            'issued_units': sum(line['issued_units'] for line in lines),
            'reserved_units': sum(line['reserved_units'] for line in lines),
            'shortage_units': sum(line['shortage_units'] for line in lines),
        },
    }


def fulfillment_view(db):
    reserved = _reserved_by_spec(db)
    sleeves = {sleeve.code: sleeve for sleeve in db.scalars(select(Sleeve))}
    stock = []
    for row in sorted(db.scalars(select(Stock)), key=lambda item: item.sleeve_code):
        sleeve = sleeves.get(row.sleeve_code)
        used = reserved.get(row.sleeve_code, 0)
        stock.append({
            'sleeve_code': row.sleeve_code,
            'title': sleeve.title if sleeve else row.sleeve_code,
            'substitute_code': sleeve.substitute_code if sleeve else None,
            'on_hand': row.on_hand,
            'reserved': used,
            'available': row.on_hand - used,
        })
    requisitions = list(db.scalars(select(Requisition).order_by(Requisition.id.desc())))
    return {
        'stock': stock,
        'workstations': [{'code': item.code, 'title': item.title}
                         for item in db.scalars(select(Workstation).order_by(Workstation.code))],
        'requisitions': [requisition_view(db, item) for item in requisitions],
    }


def _same_order(requisition, data):
    if (requisition.workstation.code != data.workstation_code
            or requisition.week != data.week
            or len(requisition.lines) != len(data.lines)):
        return False
    existing = {(line.sleeve_code, line.requested_units) for line in requisition.lines}
    requested = {(line.sleeve_code, line.units) for line in data.lines}
    return existing == requested


def submit_requisition(db, data, user):
    with _LOCK:
        lock_stock(db)
        if data.request_key:
            existing = db.scalar(select(Requisition).where(Requisition.request_key == data.request_key))
            if existing:
                if not _same_order(existing, data):
                    raise HTTPException(409, '该提交编号已用于其他领料单')
                return requisition_view(db, existing)
        workstation = db.scalar(select(Workstation).where(Workstation.code == data.workstation_code))
        if not workstation:
            raise HTTPException(422, '请选择有效工位')
        codes = [line.sleeve_code for line in data.lines]
        known = set(db.scalars(select(Sleeve.code).where(Sleeve.code.in_(codes))))
        unknown = [code for code in codes if code not in known]
        if unknown:
            raise HTTPException(422, f'规格不存在：{"、".join(unknown)}')

        requisition = Requisition(workstation_id=workstation.id, week=data.week,
                                  status=RequisitionStatus.SHORT, request_key=data.request_key,
                                  note='', requester_id=user.id)
        db.add(requisition)
        db.flush()
        for line in data.lines:
            db.add(RequisitionLine(requisition_id=requisition.id, sleeve_code=line.sleeve_code,
                                   requested_units=line.units, issued_units=0))
        audit(db, user, 'requisition', f'{requisition.id}/{data.request_key or "-"}')
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if data.request_key:
                existing = db.scalar(select(Requisition).where(Requisition.request_key == data.request_key))
                if existing and _same_order(existing, data):
                    return requisition_view(db, existing)
            raise HTTPException(409, '领料单提交冲突，请重试') from exc
        replan(db)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if data.request_key:
                existing = db.scalar(select(Requisition).where(Requisition.request_key == data.request_key))
                if existing and _same_order(existing, data):
                    return requisition_view(db, existing)
            raise HTTPException(409, '领料单提交冲突，请重试') from exc
        db.refresh(requisition)
        return requisition_view(db, requisition)


def get_requisition(db, requisition_id):
    requisition = db.get(Requisition, requisition_id)
    if not requisition:
        raise HTTPException(404, '找不到领料单')
    return requisition_view(db, requisition)


def issue_requisition(db, requisition_id, user):
    with _LOCK:
        lock_stock(db)
        requisition = db.scalar(select(Requisition).where(Requisition.id == requisition_id)
                                .with_for_update())
        if not requisition:
            raise HTTPException(404, '找不到领料单')
        if requisition.status == RequisitionStatus.ISSUED:
            return requisition_view(db, requisition)
        reservations = list(db.scalars(select(Reservation)
                                       .where(Reservation.requisition_id == requisition.id)))
        if not reservations:
            # 当前没有可领数量，保持原状但刷新一次配料结果。
            replan(db)
            db.commit()
            db.refresh(requisition)
            return requisition_view(db, requisition)

        stocks = {row.sleeve_code: row for row in db.scalars(
            select(Stock).where(Stock.sleeve_code.in_([row.sleeve_code for row in reservations]))
            .with_for_update())}
        lines = {line.id: line for line in requisition.lines}
        for row in reservations:
            line = lines[row.requisition_line_id]
            stock = stocks.get(row.sleeve_code)
            claimable = line.requested_units - line.issued_units
            units = min(row.units, stock.on_hand if stock else 0, claimable)
            if units > 0:
                stock.on_hand -= units
                line.issued_units += units
                db.add(Issue(requisition_id=requisition.id, requisition_line_id=line.id,
                             workstation_id=requisition.workstation_id, sleeve_code=row.sleeve_code,
                             week=requisition.week, units=units))
                mark_pending_week(db, row.sleeve_code, requisition.week)
        audit(db, user, 'issue', requisition.id)
        # 占用行由 replan 统一删除并按最新库存重排，避免与批量删除重复处理同一行。
        db.flush()
        replan(db)
        db.commit()
        db.refresh(requisition)
        return requisition_view(db, requisition)


def receive_stock(db, data, user):
    with _LOCK:
        lock_stock(db)
        if not db.scalar(select(Sleeve.id).where(Sleeve.code == data.sleeve_code)):
            raise HTTPException(422, '请选择有效封套规格')
        stock = db.scalar(select(Stock).where(Stock.sleeve_code == data.sleeve_code)
                          .with_for_update())
        if stock is None:
            stock = Stock(sleeve_code=data.sleeve_code, on_hand=0)
            db.add(stock)
            db.flush()
        stock.on_hand += data.units
        audit(db, user, 'receive', f'{data.sleeve_code}:{data.units}')
        replan(db)
        db.commit()
        return _stock_view(db, data.sleeve_code)


def stocktake(db, data, user):
    with _LOCK:
        lock_stock(db)
        if not db.scalar(select(Sleeve.id).where(Sleeve.code == data.sleeve_code)):
            raise HTTPException(422, '请选择有效封套规格')
        stock = db.scalar(select(Stock).where(Stock.sleeve_code == data.sleeve_code)
                          .with_for_update())
        if stock is None:
            stock = Stock(sleeve_code=data.sleeve_code, on_hand=0)
            db.add(stock)
            db.flush()
        before = stock.on_hand
        stock.on_hand = data.counted_units
        audit(db, user, 'stocktake', f'{data.sleeve_code}:{before}->{data.counted_units}')
        replan(db)
        db.commit()
        return {**_stock_view(db, data.sleeve_code), 'before': before}


def _stock_view(db, sleeve_code):
    reserved = _reserved_by_spec(db).get(sleeve_code, 0)
    stock = db.get(Stock, sleeve_code)
    return {'sleeve_code': sleeve_code, 'on_hand': stock.on_hand if stock else 0,
            'reserved': reserved, 'available': (stock.on_hand if stock else 0) - reserved}


def reconcile_week(db, data, user):
    with _LOCK:
        lock_stock(db)
        existing = db.scalar(select(Reconciliation).where(Reconciliation.week == data.week)
                             .with_for_update())
        if existing is None:
            existing = Reconciliation(week=data.week, user_id=user.id, note=data.note)
            db.add(existing)
            db.flush()
            audit(db, user, 'reconcile', data.week.isoformat())
        elif data.note:
            existing.note = data.note

        totals = {code: int(units or 0)
                  for code, units in db.execute(
                      select(Issue.sleeve_code, func.sum(Issue.units))
                      .where(Issue.week == data.week)
                      .group_by(Issue.sleeve_code)).all()}
        merged = []
        # 合并同周同规格的实发记录为周领用；只有发生过实发的规格从缺传转为已核。
        for code in sorted(totals):
            units = totals[code]
            row = db.scalar(select(Usage).where(Usage.sleeve_code == code,
                                                Usage.week == data.week).with_for_update())
            if row is None:
                db.add(Usage(sleeve_code=code, week=data.week, state='observed', units=units))
            else:
                row.state, row.units = 'observed', units
            merged.append({'sleeve_code': code, 'units': units})
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, '该周已由其他操作核清，请刷新后重试') from exc
        return {'week': data.week.isoformat(), 'note': existing.note, 'usage': merged}


def list_reconciliations(db):
    return [{'id': row.id, 'week': row.week.isoformat(), 'note': row.note,
             'created_at': row.created_at.isoformat() if row.created_at else None}
            for row in db.scalars(select(Reconciliation).order_by(Reconciliation.week.desc()))]


def create_workstation(db, data, user):
    workstation = Workstation(code=data.code, title=data.title)
    db.add(workstation)
    audit(db, user, 'workstation', data.code)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '工位编号已存在') from exc
    return {'code': workstation.code, 'title': workstation.title}


def list_workstations(db):
    return [{'code': item.code, 'title': item.title}
            for item in db.scalars(select(Workstation).order_by(Workstation.code))]

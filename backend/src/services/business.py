from fastapi import HTTPException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.config.settings import REDIS_URL
from src.constants.enums import Status
from src.models.entities import Analysis, Audit, Sleeve, Usage

queue = Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
QUEUE = 'sleeve-demand:notifications'


def record(obj, exclude=()):
    return {col.key: getattr(obj, col.key) for col in obj.__table__.columns if col.key not in exclude}


def audit(db, user, action, subject):
    db.add(Audit(user_id=user.id, action=action, subject=str(subject)))


def save_input(db, model, data, user):
    if model is Usage:
        if not db.scalar(select(Sleeve.id).where(Sleeve.code == data.sleeve_code)):
            raise HTTPException(422, '请选择有效封套规格')
        key = f'{data.sleeve_code}/{data.week}'
    else:
        key = data.code
    item = model(**data.model_dump())
    db.add(item)
    audit(db, user, 'create', key)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '规格编号或领用周已经登记') from exc
    return record(item)


def amend_usage(db, id, data, user):
    row = db.scalar(select(Usage).where(Usage.id == id).with_for_update())
    if row is None:
        raise HTTPException(404, '找不到领用周记录')
    if (row.sleeve_code, row.week) != (data.sleeve_code, data.week):
        raise HTTPException(422, '补报时保留原规格与周日期')
    row.state, row.units = data.state, data.units
    audit(db, user, 'amend_week', f'{row.sleeve_code}/{row.week}')
    db.commit()
    return record(row)


def get_input(db, sleeve_code):
    query = select(Usage).where(Usage.sleeve_code == sleeve_code).order_by(Usage.week)
    return [{**record(row), 'week': row.week.isoformat()} for row in db.scalars(query)]


def submit(db, data, user):
    sleeve = db.scalar(select(Sleeve).where(Sleeve.code == data.sleeve_code))
    if not sleeve:
        raise HTTPException(422, '请选择有效封套规格')
    parameters = {**data.model_dump(exclude={'title'}), 'pack_size':sleeve.pack_size, 'lead_weeks':sleeve.lead_weeks}
    item = Analysis(title=data.title, status=Status.QUEUED, parameters=parameters,
                    snapshot=get_input(db, sleeve.code), author_id=user.id, result=None)
    db.add(item)
    db.flush()
    audit(db, user, 'queue', item.id)
    db.commit()
    try:
        queue.lpush(QUEUE, item.id)
    except RedisError:
        pass
    return record(item, ('snapshot',))


def get_analysis(db, id):
    item = db.get(Analysis, id)
    if not item:
        raise HTTPException(404, '找不到备料单')
    return item


def publish(db, id, note, user):
    item = db.scalar(select(Analysis).where(Analysis.id == id).with_for_update())
    if not item:
        raise HTTPException(404, '找不到备料单')
    if item.status != Status.COMPLETED:
        raise HTTPException(409, '只有已完成的备料单可签核')
    item.status = Status.PUBLISHED
    item.note = note
    audit(db, user, 'publish', id)
    db.commit()
    return record(item, ('snapshot',))

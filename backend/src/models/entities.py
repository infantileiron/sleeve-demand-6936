from datetime import date, datetime
from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(16))


class Sleeve(Base):
    __tablename__ = 'sleeves'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    pack_size: Mapped[int]
    lead_weeks: Mapped[int]
    # 可代用的大一号规格；为空表示只收原规格。
    substitute_code: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Usage(Base):
    __tablename__ = 'weekly_usage'
    __table_args__ = (UniqueConstraint('sleeve_code', 'week', name='uq_usage_sleeve_week'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sleeve_code: Mapped[str] = mapped_column(ForeignKey('sleeves.code'))
    week: Mapped[date] = mapped_column(Date)
    state: Mapped[str] = mapped_column(String(12))
    units: Mapped[int | None]


class Analysis(Base):
    __tablename__ = 'forecast_sheets'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), index=True)
    parameters: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Audit(Base):
    __tablename__ = 'audits'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Workstation(Base):
    __tablename__ = 'workstations'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(100))


class Stock(Base):
    __tablename__ = 'stock'
    sleeve_code: Mapped[str] = mapped_column(ForeignKey('sleeves.code'), primary_key=True)
    on_hand: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FulfillmentLock(Base):
    """单行锁记录，串行化所有配料、领发与盘点事务。"""

    __tablename__ = 'fulfillment_lock'
    id: Mapped[int] = mapped_column(primary_key=True)


class Reservation(Base):
    """领料单尚未领取的配料占用：某行需求计划由哪个规格实发多少。"""

    __tablename__ = 'reservations'
    __table_args__ = (UniqueConstraint('requisition_line_id', 'sleeve_code', name='uq_reservation_line_spec'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey('requisitions.id'), index=True)
    requisition_line_id: Mapped[int] = mapped_column(ForeignKey('requisition_lines.id'), index=True)
    sleeve_code: Mapped[str] = mapped_column(ForeignKey('sleeves.code'))
    units: Mapped[int]


class Requisition(Base):
    __tablename__ = 'requisitions'
    id: Mapped[int] = mapped_column(primary_key=True)
    workstation_id: Mapped[int] = mapped_column(ForeignKey('workstations.id'))
    week: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), index=True)
    request_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    note: Mapped[str] = mapped_column(Text, default='')
    requester_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    workstation: Mapped[Workstation] = relationship(lazy='joined')
    lines: Mapped[list['RequisitionLine']] = relationship(
        back_populates='requisition', cascade='all, delete-orphan', order_by='RequisitionLine.id')


class RequisitionLine(Base):
    __tablename__ = 'requisition_lines'
    __table_args__ = (UniqueConstraint('requisition_id', 'sleeve_code', name='uq_line_requisition_sleeve'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey('requisitions.id'), index=True)
    sleeve_code: Mapped[str] = mapped_column(ForeignKey('sleeves.code'))
    requested_units: Mapped[int]
    issued_units: Mapped[int] = mapped_column(default=0)
    requisition: Mapped[Requisition] = relationship(back_populates='lines')


class Issue(Base):
    __tablename__ = 'issues'
    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey('requisitions.id'), index=True)
    requisition_line_id: Mapped[int] = mapped_column(ForeignKey('requisition_lines.id'))
    workstation_id: Mapped[int] = mapped_column(ForeignKey('workstations.id'))
    sleeve_code: Mapped[str] = mapped_column(ForeignKey('sleeves.code'))
    week: Mapped[date] = mapped_column(Date, index=True)
    units: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Reconciliation(Base):
    __tablename__ = 'reconciliations'
    id: Mapped[int] = mapped_column(primary_key=True)
    week: Mapped[date] = mapped_column(Date, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

from enum import StrEnum


class Role(StrEnum):
    MANAGER = 'manager'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class Status(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PUBLISHED = 'published'


class RequisitionStatus(StrEnum):
    SHORT = 'short'          # 有缺口，等待补料
    READY = 'ready'          # 可整单领齐
    ISSUED = 'issued'        # 已全部实发

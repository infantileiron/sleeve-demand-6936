import json
from datetime import date, timedelta
from sqlalchemy import func, select

from src.config.database import Base, Session, engine
from src.constants.enums import Role, Status
from src.models.entities import Analysis, Sleeve, Usage, User
from src.services.business import get_input
from src.utils.security import password_hash

SKUS = [('SL-A4','A4 无酸封套',25,3),('SL-8X10','8×10 涂布档案套',10,4),('SL-MAP','大幅地图封套',5,5)]
BASE = date(2025,9,15)


def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in Role:
            email = f'{role}@huaiye.demo'
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, role=role, password_hash=password_hash('Archive2026!')))
        known = set(db.scalars(select(Sleeve.code)))
        db.add_all(Sleeve(code=code, title=title, pack_size=pack, lead_weeks=lead)
                   for code, title, pack, lead in SKUS if code not in known)
        db.flush()
        used = set(db.execute(select(Usage.sleeve_code, Usage.week)).tuples())
        for idx, (code, _, _, _) in enumerate(SKUS):
            for i in range(58):
                week = BASE + timedelta(weeks=i)
                if (code, week) in used:
                    continue
                missing = i == 5 or (code == 'SL-MAP' and i == 57)
                units = None if missing else (18+((i*7+idx)%14) if i%(4+idx) in (0, 1) and i%3 else 0)
                db.add(Usage(sleeve_code=code, week=week, state='missing' if missing else 'observed', units=units))
        db.flush()
        title = 'A4 无酸封套 · 秋季备料'
        if not db.scalar(select(Analysis).where(Analysis.title == title)):
            owner = db.scalar(select(User).where(User.role == Role.ANALYST))
            db.add(Analysis(title=title, status=Status.QUEUED, author_id=owner.id,
                            parameters={'sleeve_code':'SL-A4','lead_weeks':3,'pack_size':25,'alpha':.2,'baseline_weeks':8},
                            snapshot=get_input(db, 'SL-A4'), result=None))
        db.commit()
        return {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                for model in (User, Sleeve, Usage, Analysis)}


if __name__ == '__main__':
    print(json.dumps(seed(), sort_keys=True))

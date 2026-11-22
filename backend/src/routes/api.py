from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.config.database import get_db
from src.controllers.auth import current, login, manager, writable
from src.controllers.export import export
from src.models.entities import Analysis, Audit, Sleeve, Usage
from src.schemas.business import AnalysisInput, SleeveInput, UsageInput, Login, Publication
from src.services import business as svc

router = APIRouter(prefix='/api')


@router.post('/auth/login')
def sign_in(data: Login, db=Depends(get_db)):
    return login(data, db)


@router.get('/auth/me')
def me(user=Depends(current)):
    return {'email': user.email, 'role': user.role}


@router.get('/sleeves')
def sleeves(db=Depends(get_db), user=Depends(current)):
    return [svc.record(item) for item in db.scalars(select(Sleeve).order_by(Sleeve.code))]


@router.post('/sleeves', status_code=201)
def create_sleeve(data: SleeveInput, db=Depends(get_db), user=Depends(writable)):
    return svc.save_input(db, Sleeve, data, user)


@router.get('/usage')
def usage(sleeve_code: str | None = None, db=Depends(get_db), user=Depends(current)):
    query = select(Usage).order_by(Usage.week.desc(), Usage.id.desc())
    if sleeve_code:
        query = query.where(Usage.sleeve_code == sleeve_code)
    return [svc.record(item) for item in db.scalars(query)]


@router.post('/usage', status_code=201)
def create_usage(data: UsageInput, db=Depends(get_db), user=Depends(writable)):
    return svc.save_input(db, Usage, data, user)


@router.post('/usage/{id}/amend')
def amend(id: int, data: UsageInput, db=Depends(get_db), user=Depends(writable)):
    return svc.amend_usage(db, id, data, user)


@router.get('/analyses')
def analyses(db=Depends(get_db), user=Depends(current)):
    return [svc.record(item, ('snapshot', 'result')) for item in db.scalars(select(Analysis).order_by(Analysis.id.desc()))]


@router.post('/analyses', status_code=202)
def enqueue(data: AnalysisInput, db=Depends(get_db), user=Depends(writable)):
    return svc.submit(db, data, user)


@router.get('/analyses/{id}')
def analysis(id: int, db=Depends(get_db), user=Depends(current)):
    return svc.record(svc.get_analysis(db, id), ('snapshot',))


@router.get('/analyses/{id}/export')
def download(id: int, db=Depends(get_db), user=Depends(current)):
    return export(svc.get_analysis(db, id))


@router.post('/analyses/{id}/publish')
def publish(id: int, data: Publication, db=Depends(get_db), user=Depends(manager)):
    return svc.publish(db, id, data.note, user)


@router.get('/audits')
def audit_log(db=Depends(get_db), user=Depends(manager)):
    return [svc.record(item) for item in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))]

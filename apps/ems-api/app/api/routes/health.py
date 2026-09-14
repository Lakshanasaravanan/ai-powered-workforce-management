from fastapi import APIRouter
from app.core.config import Settings
router = APIRouter()
@router.get('/health')
def health(): return {'status':'ok','service':'infotech-ems-api'}
@router.get('/api/v1/system/info')
def info():
    settings=Settings()
    return {'application_name':settings.app_name,'environment':settings.environment,'api_version':settings.api_version}

from fastapi import FastAPI
from app.api.routes.health import router
app=FastAPI(title='InfoTech Workspace EMS API',version='v1')
app.include_router(router)

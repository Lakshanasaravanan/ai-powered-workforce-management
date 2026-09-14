from fastapi import FastAPI
from app.api.routes.health import router
from app.api.routes.auth import router as auth_router
from app.api.routes.employees import router as employee_router
app=FastAPI(title='InfoTech Workspace EMS API',version='v1')
app.include_router(router)
app.include_router(auth_router)
app.include_router(employee_router)

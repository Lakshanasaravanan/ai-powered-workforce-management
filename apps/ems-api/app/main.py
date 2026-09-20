from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.health import router
from app.api.routes.auth import router as auth_router
from app.api.routes.employees import router as employee_router
from app.api.routes.leaves import router as leave_router
from app.api.routes.notifications import router as notification_router
from app.api.routes.chat import router as chat_router
app=FastAPI(title='InfoTech Workspace EMS API',version='v1')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(leave_router)
app.include_router(notification_router)
app.include_router(chat_router)

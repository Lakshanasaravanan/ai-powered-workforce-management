from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis
from app.core.config import Settings
from app.api.routes.health import router
from app.api.routes.auth import router as auth_router
from app.api.routes.employees import router as employee_router
from app.api.routes.leaves import router as leave_router
from app.api.routes.notifications import router as notification_router
from app.api.routes.chat import router as chat_router
from app.api.routes.calendar import router as calendar_router
from app.services.websocket_tickets import RedisWebSocketTicketStore
app=FastAPI(title='InfoTech Workspace EMS API',version='v1')
settings=Settings()
app.state.websocket_ticket_store = RedisWebSocketTicketStore(
    redis.Redis.from_url(settings.redis_url, decode_responses=True), settings.websocket_ticket_ttl_seconds
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(leave_router)
app.include_router(notification_router)
app.include_router(chat_router)
app.include_router(calendar_router)

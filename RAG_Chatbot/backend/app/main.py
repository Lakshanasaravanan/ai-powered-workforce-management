"""FastAPI application entry point for the standalone Agentic RAG service."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.planner import DeterministicPlanner
from app.agents.service import AgentService
from app.api.routes import auth, chat, health
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_context
from app.rag.ingestion import VECTOR_STORE_DIR
from app.rag.service import RAGServiceError, create_rag_service
from app.services.pending_actions import PendingActionStore, RedisPendingActionStore
from app.services.slams import SLAMSWorkforceProvider
from app.services.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.services.workforce import MockWorkforceProvider
from app.tools.actions import RegularizeAttendanceTool, RequestLeaveTool
from app.tools.rag_tool import PolicyAnswerTool
from app.tools.registry import ToolRegistry
from app.tools.workforce import GetMyAttendanceRecordsTool, GetMyAttendanceSummaryTool, GetMyLeaveBalanceTool, GetMyProfileTool


logger = logging.getLogger("agentic_rag.request")
HTTP_REQUESTS = Counter("agentic_rag_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("agentic_rag_http_latency_seconds", "HTTP latency", ["method", "route"])


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.rag_service = create_rag_service(settings, VECTOR_STORE_DIR)
    workforce = SLAMSWorkforceProvider.from_settings(settings) if settings.slams_enabled else MockWorkforceProvider()
    app.state.workforce_provider = workforce
    redis_client = None
    if settings.redis_enabled:
        import redis
        try:
            redis_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
            redis_client.ping()
        except redis.RedisError as exc:
            logger.error("redis_unavailable", extra={"dependency": "redis"})
            raise RuntimeError("Required Redis dependency is unavailable") from exc
        pending_actions = RedisPendingActionStore(redis_client, ttl=timedelta(seconds=settings.pending_action_ttl_seconds), execution_lease=timedelta(seconds=settings.pending_action_execution_lease_seconds))
    else:
        pending_actions = PendingActionStore(ttl=timedelta(seconds=settings.pending_action_ttl_seconds))
    app.state.redis_client = redis_client
    app.state.rate_limiter = RedisRateLimiter(redis_client) if redis_client is not None else InMemoryRateLimiter()
    app.state.agent_service = AgentService(
        planner=DeterministicPlanner(),
        registry=ToolRegistry([
            PolicyAnswerTool(app.state.rag_service),
            GetMyProfileTool(workforce),
            GetMyLeaveBalanceTool(workforce),
            GetMyAttendanceSummaryTool(workforce),
            GetMyAttendanceRecordsTool(workforce),
            RequestLeaveTool(pending_actions),
            RegularizeAttendanceTool(pending_actions),
        ]),
        pending_actions=pending_actions,
        action_provider=workforce,
    )
    logger.info("application_started")
    yield
    close = getattr(workforce, "close", None)
    if close is not None:
        close()
    if redis_client is not None:
        redis_client.close()
    logger.info("application_stopped")


app = FastAPI(
    title="Workforce Agentic RAG Service",
    version="0.1.0",
    description="Standalone AI assistant service. Phase 1 foundation only.",
    lifespan=lifespan,
)
app.include_router(health.router)
if get_settings().development_auth_enabled:
    app.include_router(auth.router)
app.include_router(chat.router)

@app.get("/metrics", include_in_schema=False)
def metrics():
    from fastapi.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _request_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = _request_id(request.headers.get("X-Request-ID"))
    token = request_id_context.set(request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={"endpoint": request.url.path, "method": request.method, "status": 500},
        )
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "internal_error", "message": "Internal server error", "request_id": request_id}},
        )
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    HTTP_REQUESTS.labels(request.method, request.url.path, str(response.status_code)).inc()
    HTTP_LATENCY.labels(request.method, request.url.path).observe(time.perf_counter() - started_at)
    logger.info(
        "request_completed",
        extra={
            "endpoint": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    request_id_context.reset(token)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "request_id": request_id_context.get(),
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": "http_error",
                "message": detail,
                "request_id": request_id_context.get(),
            }
        },
    )


@app.exception_handler(RAGServiceError)
async def rag_service_exception_handler(request: Request, exc: RAGServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": {
                "code": "rag_service_unavailable",
                "message": "The policy assistant is temporarily unavailable. Please try again later.",
                "request_id": request_id_context.get(),
            }
        },
    )

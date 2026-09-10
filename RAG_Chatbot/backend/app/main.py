"""FastAPI application entry point for the standalone Agentic RAG service."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.planner import DeterministicPlanner
from app.agents.service import AgentService
from app.api.routes import auth, chat, health
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_context
from app.rag.ingestion import VECTOR_STORE_DIR
from app.rag.service import RAGServiceError, create_rag_service
from app.services.pending_actions import PendingActionStore
from app.services.slams import SLAMSWorkforceProvider
from app.services.workforce import MockWorkforceProvider
from app.tools.actions import RegularizeAttendanceTool, RequestLeaveTool
from app.tools.rag_tool import PolicyAnswerTool
from app.tools.registry import ToolRegistry
from app.tools.workforce import GetMyAttendanceSummaryTool, GetMyLeaveBalanceTool, GetMyProfileTool


logger = logging.getLogger("agentic_rag.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.rag_service = create_rag_service(settings, VECTOR_STORE_DIR)
    workforce = SLAMSWorkforceProvider.from_settings(settings) if settings.slams_enabled else MockWorkforceProvider()
    app.state.workforce_provider = workforce
    pending_actions = PendingActionStore()
    app.state.agent_service = AgentService(
        planner=DeterministicPlanner(),
        registry=ToolRegistry([
            PolicyAnswerTool(app.state.rag_service),
            GetMyProfileTool(workforce),
            GetMyLeaveBalanceTool(workforce),
            GetMyAttendanceSummaryTool(workforce),
            RequestLeaveTool(pending_actions),
            RegularizeAttendanceTool(pending_actions),
        ]),
        pending_actions=pending_actions,
    )
    logger.info("application_started")
    yield
    close = getattr(workforce, "close", None)
    if close is not None:
        close()
    logger.info("application_stopped")


app = FastAPI(
    title="Workforce Agentic RAG Service",
    version="0.1.0",
    description="Standalone AI assistant service. Phase 1 foundation only.",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)


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

import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings


router = APIRouter(tags=["health"])
logger = logging.getLogger("agentic_rag.readiness")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    settings = get_settings()
    dependencies = {"rag": "ready", "redis": "disabled"}
    ok = True
    if settings.redis_enabled:
        try:
            request.app.state.redis_client.ping()
            dependencies["redis"] = "ready"
        except Exception:
            dependencies["redis"] = "unavailable"; ok = False
    payload = {"status": "ready" if ok else "not_ready", "environment": settings.environment, "warnings": settings.readiness_warnings, "dependencies": dependencies}
    logger.info("dependency_readiness", extra={"dependency": "redis", "status": dependencies["redis"]})
    return JSONResponse(status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

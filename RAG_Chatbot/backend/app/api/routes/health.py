from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, object]:
    settings = get_settings()
    return {"status": "ready", "environment": settings.environment, "warnings": settings.readiness_warnings}

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "InfoTech Workspace EMS API"
    environment: str = "development"
    api_version: str = "v1"
    database_url: str = "postgresql+asyncpg://infotech:infotech-local-only@localhost:5432/infotech"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

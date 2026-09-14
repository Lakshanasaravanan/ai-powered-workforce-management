from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "InfoTech Workspace EMS API"
    environment: str = "development"
    api_version: str = "v1"
    database_url: str = "postgresql+asyncpg://infotech:infotech@localhost:5432/infotech"
    redis_url: str = "redis://localhost:6379/0"

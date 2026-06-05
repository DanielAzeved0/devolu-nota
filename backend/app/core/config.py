from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(..., min_length=1)
    app_name: str = Field(..., min_length=1)
    api_v1_prefix: str = Field(..., min_length=1)
    database_url: str = Field(..., min_length=1)
    redis_url: str = Field(..., min_length=1)
    jwt_secret_key: str = Field(..., min_length=1)
    jwt_access_token_expire_minutes: int = Field(..., gt=0)
    jwt_refresh_token_expire_days: int = Field(..., gt=0)
    encryption_key: str = Field(..., min_length=1)
    cors_origins: str = Field(..., min_length=1)
    tiny_api_base_url: str = Field(..., min_length=1)
    mercado_livre_client_id: str = Field(..., min_length=1)
    mercado_livre_client_secret: str = Field(..., min_length=1)
    shopee_client_id: str = Field(..., min_length=1)
    shopee_client_secret: str = Field(..., min_length=1)
    storage_endpoint_url: str = Field(..., min_length=1)
    storage_bucket_name: str = Field(..., min_length=1)
    storage_access_key: str = Field(..., min_length=1)
    storage_secret_key: str = Field(..., min_length=1)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

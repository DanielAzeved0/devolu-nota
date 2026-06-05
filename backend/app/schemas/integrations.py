from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IntegrationProvider = Literal["TINY", "MERCADO_LIVRE", "SHOPEE"]
IntegrationStatus = Literal["ACTIVE", "INVALID_TOKEN", "EXPIRED", "DISCONNECTED", "ERROR"]
CredentialField = Literal["access_token", "refresh_token", "api_token", "client_secret"]
SENSITIVE_SETTING_FIELDS = {"access_token", "refresh_token", "api_token", "client_secret"}


def validate_public_settings(settings: dict[str, Any] | None) -> dict[str, Any] | None:
    if settings is None:
        return settings

    sensitive_fields = SENSITIVE_SETTING_FIELDS.intersection(settings.keys())
    if sensitive_fields:
        raise ValueError("settings cannot contain sensitive credential fields")

    return settings


class IntegrationCredentialsRequest(BaseModel):
    access_token: str | None = Field(default=None, min_length=1)
    refresh_token: str | None = Field(default=None, min_length=1)
    api_token: str | None = Field(default=None, min_length=1)
    client_secret: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_at_least_one_credential(self) -> "IntegrationCredentialsRequest":
        if not self.to_sensitive_dict():
            raise ValueError("At least one credential field is required")
        return self

    def to_sensitive_dict(self) -> dict[CredentialField, str]:
        credentials: dict[CredentialField, str] = {}
        for field_name in SENSITIVE_SETTING_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                credentials[field_name] = value
        return credentials


class IntegrationCreateRequest(BaseModel):
    provider: IntegrationProvider
    settings: dict[str, Any] | None = None
    credentials: IntegrationCredentialsRequest | None = None

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_public_settings(value)


class IntegrationUpdateRequest(BaseModel):
    status: IntegrationStatus | None = None
    settings: dict[str, Any] | None = None

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_public_settings(value)


class IntegrationPublic(BaseModel):
    id: UUID
    company_id: UUID
    provider: str
    status: str
    settings: dict[str, Any] | None = None
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

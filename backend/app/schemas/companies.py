from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

CompanyRole = Literal["OWNER", "ADMIN", "OPERATOR", "VIEWER"]


class CompanyCreateRequest(BaseModel):
    legal_name: str = Field(..., min_length=2, max_length=255)
    document: str = Field(..., min_length=3, max_length=32)
    trade_name: str | None = Field(default=None, max_length=255)

    @field_validator("document")
    @classmethod
    def normalize_document(cls, value: str) -> str:
        return value.strip()

    @field_validator("legal_name", "trade_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class CompanyPublic(BaseModel):
    id: UUID
    legal_name: str
    trade_name: str | None
    document: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyUserCreateRequest(BaseModel):
    user_id: UUID
    role: CompanyRole


class CompanyUserPublic(BaseModel):
    id: UUID
    company_id: UUID
    user_id: UUID
    user_email: str
    user_name: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime

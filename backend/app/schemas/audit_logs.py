from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogPublic(BaseModel):
    id: UUID
    company_id: UUID
    user_id: UUID | None = None
    action: str
    entity_type: str
    entity_id: UUID
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogPublic]
    limit: int
    offset: int

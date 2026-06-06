from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.integrations.mock_scenarios import MockScenario


class ReturnNoteMockCreateRequest(BaseModel):
    scenario: MockScenario = "success"


class ReturnNotePublic(BaseModel):
    id: UUID
    company_id: UUID
    return_order_id: UUID
    status: str
    original_nfe_key: str | None = None
    return_nfe_key: str | None = None
    number: str | None = None
    series: str | None = None
    issued_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReturnNoteListResponse(BaseModel):
    items: list[ReturnNotePublic]
    limit: int
    offset: int
    count: int

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MockEmissionScenario = Literal["success", "partial_failure", "failure"]


class EmissionBatchMockCreateRequest(BaseModel):
    return_note_ids: list[UUID] = Field(..., min_length=1)
    scenario: MockEmissionScenario = "success"

    @field_validator("return_note_ids")
    @classmethod
    def reject_duplicate_return_note_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("return_note_ids must not contain duplicates")
        return value


class EmissionJobPublic(BaseModel):
    id: UUID
    company_id: UUID
    batch_id: UUID
    return_note_id: UUID
    status: str
    attempts: int
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmissionBatchPublic(BaseModel):
    id: UUID
    company_id: UUID
    requested_by_user_id: UUID | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmissionBatchCreatedResponse(EmissionBatchPublic):
    jobs: list[EmissionJobPublic]


class EmissionJobListResponse(BaseModel):
    items: list[EmissionJobPublic]

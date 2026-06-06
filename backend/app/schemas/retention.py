from uuid import UUID

from pydantic import BaseModel


class RetentionJobPublic(BaseModel):
    id: UUID
    company_id: UUID
    storage_archive_id: UUID | None
    status: str
    error_message: str | None = None


class RetentionMockRunResponse(BaseModel):
    company_id: UUID
    archived_count: int
    deleted_count: int
    skipped_count: int
    jobs: list[RetentionJobPublic]

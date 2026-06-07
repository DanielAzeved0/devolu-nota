from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FiscalDocumentPublic(BaseModel):
    id: UUID
    company_id: UUID
    return_note_id: UUID
    document_type: str
    status: str
    access_key: str | None = None
    xml_storage_archive_id: UUID | None = None
    pdf_storage_archive_id: UUID | None = None
    issued_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FiscalDocumentListResponse(BaseModel):
    items: list[FiscalDocumentPublic]
    limit: int
    offset: int

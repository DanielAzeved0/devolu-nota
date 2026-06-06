from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FiscalDocumentType = Literal["NFE_XML", "DANFE_PDF", "TINY_JSON", "SEFAZ_EVENT"]


class FiscalDocumentMockStoreRequest(BaseModel):
    document_type: FiscalDocumentType
    content: str = Field(..., min_length=1, max_length=200_000)
    content_type: str = Field(..., min_length=1, max_length=128)
    access_key: str | None = Field(default=None, min_length=44, max_length=44)


class FiscalDocumentPublic(BaseModel):
    id: UUID
    company_id: UUID
    return_note_id: UUID
    document_type: str
    status: str
    access_key: str | None = None
    storage_archive_id: UUID | None = None
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
    count: int

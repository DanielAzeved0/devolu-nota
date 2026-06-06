from hashlib import sha256
from uuid import UUID

from app.core.config import get_settings
from app.models import FiscalDocument, User
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.schemas.fiscal_documents import FiscalDocumentMockStoreRequest
from app.services.companies import CompanyService
from app.services.return_notes import ReturnNoteNotFoundError


class FiscalDocumentStorageService:
    def __init__(
        self,
        *,
        companies: CompanyService,
        return_notes: ReturnNoteRepository,
        fiscal_documents: FiscalDocumentRepository,
    ) -> None:
        self.companies = companies
        self.return_notes = return_notes
        self.fiscal_documents = fiscal_documents
        self.settings = get_settings()

    async def store_mock_document(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
        payload: FiscalDocumentMockStoreRequest,
        current_user: User,
    ) -> FiscalDocument:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return_note = await self.return_notes.get_by_company_id(
            company_id=company_id,
            return_note_id=return_note_id,
        )
        if return_note is None:
            raise ReturnNoteNotFoundError("Return note not found")

        content_bytes = payload.content.encode("utf-8")
        checksum = sha256(content_bytes).hexdigest()
        object_key = (
            f"mock/{company_id}/{return_note_id}/{payload.document_type.lower()}/{checksum}"
        )
        archive = await self.fiscal_documents.create_storage_archive(
            company_id=company_id,
            storage_provider="LOCAL",
            bucket=self.settings.storage_bucket_name,
            object_key=object_key,
            content_type=payload.content_type,
            checksum=checksum,
            size_bytes=len(content_bytes),
        )
        return await self.fiscal_documents.create_fiscal_document(
            company_id=company_id,
            return_note_id=return_note_id,
            document_type=payload.document_type,
            storage_archive_id=archive.id,
            access_key=payload.access_key,
            issued_at=return_note.issued_at,
        )

    async def list_return_note_documents(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
        current_user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FiscalDocument]:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return_note = await self.return_notes.get_by_company_id(
            company_id=company_id,
            return_note_id=return_note_id,
        )
        if return_note is None:
            raise ReturnNoteNotFoundError("Return note not found")

        return await self.fiscal_documents.list_by_return_note(
            company_id=company_id,
            return_note_id=return_note_id,
            limit=limit,
            offset=offset,
        )

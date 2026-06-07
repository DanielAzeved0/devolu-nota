from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from app.models import User
from app.models import FiscalDocument, StorageArchive
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.services.companies import COMPANY_READER_ROLES, CompanyService
from app.storage.local import LocalStorageProvider, ObjectNotFoundError

FISCAL_DOCUMENT_BUCKET = "fiscal-documents"
DEFAULT_COLD_AFTER_YEARS = 5
SUPPORTED_STORED_DOCUMENT_TYPES = ("NFE_XML", "DANFE_PDF")


class FiscalDocumentError(ValueError):
    pass


class FiscalDocumentNotFoundError(FiscalDocumentError):
    pass


class FiscalDocumentUnsupportedTypeError(FiscalDocumentError):
    pass


class FiscalDocumentIntegrityError(FiscalDocumentError):
    pass


class ReturnNoteFiscalDocumentNotFoundError(FiscalDocumentError):
    pass


@dataclass(frozen=True)
class StoredFiscalDocument:
    fiscal_document: FiscalDocument
    storage_archive: StorageArchive


@dataclass(frozen=True)
class FiscalDocumentContent:
    document: FiscalDocument
    archive: StorageArchive
    content: bytes


class FiscalDocumentStorageService:
    def __init__(
        self,
        *,
        fiscal_documents: FiscalDocumentRepository,
        return_notes: ReturnNoteRepository,
        companies: CompanyService | None = None,
        storage: LocalStorageProvider | None = None,
    ) -> None:
        self.fiscal_documents = fiscal_documents
        self.return_notes = return_notes
        self.companies = companies
        self.storage = storage or LocalStorageProvider()

    async def store_document(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
        document_type: str,
        content_bytes: bytes,
        content_type: str,
        access_key: str | None = None,
        issued_at: datetime | None = None,
    ) -> StoredFiscalDocument:
        if document_type not in SUPPORTED_STORED_DOCUMENT_TYPES:
            raise FiscalDocumentUnsupportedTypeError("Unsupported fiscal document type")

        return_note = await self.return_notes.get_by_company_id(
            company_id=company_id,
            return_note_id=return_note_id,
        )
        if return_note is None:
            raise ReturnNoteFiscalDocumentNotFoundError("Return note not found")

        checksum = calculate_checksum(content_bytes)
        document_issued_at = issued_at or utcnow()
        retention_until = add_years(document_issued_at, DEFAULT_COLD_AFTER_YEARS)
        object_key = build_fiscal_object_key(
            company_id=company_id,
            return_note_id=return_note_id,
            document_type=document_type,
            content_type=content_type,
        )
        saved_object = self.storage.save_object(
            bucket=FISCAL_DOCUMENT_BUCKET,
            object_key=object_key,
            content_bytes=content_bytes,
            content_type=content_type,
        )
        saved_bytes = self.storage.read_object(
            bucket=saved_object.bucket,
            object_key=saved_object.object_key,
        )
        if calculate_checksum(saved_bytes) != checksum:
            raise FiscalDocumentIntegrityError("Stored fiscal document checksum mismatch")

        archive = await self.fiscal_documents.create_storage_archive(
            company_id=company_id,
            bucket=saved_object.bucket,
            object_key=saved_object.object_key,
            content_type=saved_object.content_type,
            checksum=checksum,
            size_bytes=saved_object.size_bytes,
            retention_until=retention_until,
        )
        document = await self.fiscal_documents.create_fiscal_document(
            company_id=company_id,
            return_note_id=return_note_id,
            document_type=document_type,
            storage_archive=archive,
            access_key=access_key,
            issued_at=document_issued_at,
        )
        return StoredFiscalDocument(fiscal_document=document, storage_archive=archive)

    async def list_documents(
        self,
        *,
        company_id: UUID,
        current_user: User,
        return_note_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FiscalDocument]:
        await self._require_read_access(company_id=company_id, current_user=current_user)
        return await self.fiscal_documents.list_documents_by_company_id(
            company_id=company_id,
            return_note_id=return_note_id,
            limit=limit,
            offset=offset,
        )

    async def read_document(self, *, company_id: UUID, fiscal_document_id: UUID) -> bytes:
        content = await self.get_document_content(
            company_id=company_id,
            fiscal_document_id=fiscal_document_id,
        )
        return content.content

    async def read_document_for_user(
        self,
        *,
        company_id: UUID,
        fiscal_document_id: UUID,
        current_user: User,
    ) -> FiscalDocumentContent:
        await self._require_read_access(company_id=company_id, current_user=current_user)
        return await self.get_document_content(
            company_id=company_id,
            fiscal_document_id=fiscal_document_id,
        )

    async def get_document_content(
        self,
        *,
        company_id: UUID,
        fiscal_document_id: UUID,
    ) -> FiscalDocumentContent:
        document = await self.fiscal_documents.get_document_by_company_id(
            company_id=company_id,
            fiscal_document_id=fiscal_document_id,
        )
        if document is None:
            raise FiscalDocumentNotFoundError("Fiscal document not found")

        storage_archive_id = document.xml_storage_archive_id or document.pdf_storage_archive_id
        if storage_archive_id is None:
            raise FiscalDocumentNotFoundError("Fiscal document storage archive not found")

        archive = await self.fiscal_documents.get_storage_archive_by_company_id(
            company_id=company_id,
            storage_archive_id=storage_archive_id,
        )
        if archive is None:
            raise FiscalDocumentNotFoundError("Fiscal document storage archive not found")

        try:
            content = self.storage.read_object(bucket=archive.bucket, object_key=archive.object_key)
        except ObjectNotFoundError:
            raise FiscalDocumentNotFoundError("Fiscal document storage object not found") from None

        if archive.checksum is not None and calculate_checksum(content) != archive.checksum:
            raise FiscalDocumentIntegrityError("Fiscal document checksum mismatch")
        return FiscalDocumentContent(document=document, archive=archive, content=content)

    async def _require_read_access(self, *, company_id: UUID, current_user: User) -> None:
        if self.companies is None:
            return
        await self.companies.require_company_role(
            company_id=company_id,
            current_user=current_user,
            allowed_roles=COMPANY_READER_ROLES,
        )


def calculate_checksum(content_bytes: bytes) -> str:
    return sha256(content_bytes).hexdigest()


def add_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def build_fiscal_object_key(
    *,
    company_id: UUID,
    return_note_id: UUID,
    document_type: str,
    content_type: str,
) -> str:
    extension = extension_for_document(document_type=document_type, content_type=content_type)
    return (
        f"{company_id}/return-notes/{return_note_id}/"
        f"{document_type.lower()}-{uuid4().hex}{extension}"
    )


def extension_for_document(*, document_type: str, content_type: str) -> str:
    if document_type == "NFE_XML" or content_type == "application/xml":
        return ".xml"
    if document_type == "DANFE_PDF" or content_type == "application/pdf":
        return ".pdf"
    return ".bin"

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FiscalDocument, StorageArchive


class FiscalDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_storage_archive(
        self,
        *,
        company_id: UUID,
        storage_provider: str,
        bucket: str,
        object_key: str,
        content_type: str,
        checksum: str,
        size_bytes: int,
        retention_until: datetime | None = None,
    ) -> StorageArchive:
        archive = StorageArchive(
            company_id=company_id,
            storage_provider=storage_provider,
            bucket=bucket,
            object_key=object_key,
            content_type=content_type,
            status="ACTIVE",
            checksum=checksum,
            size_bytes=size_bytes,
            retention_until=retention_until,
        )
        self.session.add(archive)
        await self.session.flush()
        await self.session.refresh(archive)
        return archive

    async def create_fiscal_document(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
        document_type: str,
        storage_archive_id: UUID,
        access_key: str | None = None,
        issued_at: datetime | None = None,
    ) -> FiscalDocument:
        fiscal_document = FiscalDocument(
            company_id=company_id,
            return_note_id=return_note_id,
            document_type=document_type,
            status="AVAILABLE",
            access_key=access_key,
            storage_archive_id=storage_archive_id,
            xml_storage_archive_id=storage_archive_id if document_type == "NFE_XML" else None,
            pdf_storage_archive_id=storage_archive_id if document_type == "DANFE_PDF" else None,
            issued_at=issued_at,
        )
        self.session.add(fiscal_document)
        await self.session.flush()
        await self.session.refresh(fiscal_document)
        return fiscal_document

    async def list_by_return_note(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FiscalDocument]:
        statement: Select[tuple[FiscalDocument]] = select(FiscalDocument).where(
            FiscalDocument.company_id == company_id,
            FiscalDocument.return_note_id == return_note_id,
        )
        result = await self.session.execute(
            statement.order_by(FiscalDocument.created_at.desc(), FiscalDocument.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

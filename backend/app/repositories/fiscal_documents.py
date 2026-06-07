from uuid import UUID

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FiscalDocument, StorageArchive


class FiscalDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_storage_archive(
        self,
        *,
        company_id: UUID,
        bucket: str,
        object_key: str,
        content_type: str,
        checksum: str,
        size_bytes: int,
        retention_until: datetime,
    ) -> StorageArchive:
        archive = StorageArchive(
            company_id=company_id,
            storage_provider="LOCAL",
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
        storage_archive: StorageArchive,
        access_key: str | None,
        issued_at: datetime | None,
    ) -> FiscalDocument:
        document = FiscalDocument(
            company_id=company_id,
            return_note_id=return_note_id,
            document_type=document_type,
            status="AVAILABLE",
            access_key=access_key,
            issued_at=issued_at,
        )
        if document_type == "NFE_XML":
            document.xml_storage_archive_id = storage_archive.id
        if document_type == "DANFE_PDF":
            document.pdf_storage_archive_id = storage_archive.id

        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def get_document_by_company_id(
        self,
        *,
        company_id: UUID,
        fiscal_document_id: UUID,
    ) -> FiscalDocument | None:
        result = await self.session.execute(
            select(FiscalDocument).where(
                FiscalDocument.id == fiscal_document_id,
                FiscalDocument.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_documents_by_company_id(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FiscalDocument]:
        query = select(FiscalDocument).where(FiscalDocument.company_id == company_id)
        if return_note_id is not None:
            query = query.where(FiscalDocument.return_note_id == return_note_id)
        result = await self.session.execute(
            query.order_by(FiscalDocument.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def get_storage_archive_by_company_id(
        self,
        *,
        company_id: UUID,
        storage_archive_id: UUID,
    ) -> StorageArchive | None:
        result = await self.session.execute(
            select(StorageArchive).where(
                StorageArchive.id == storage_archive_id,
                StorageArchive.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

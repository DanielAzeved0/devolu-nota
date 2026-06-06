from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FiscalDocument, RetentionJob, StorageArchive


class RetentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_archives_created_before(
        self,
        *,
        company_id: UUID,
        cutoff: datetime,
    ) -> list[StorageArchive]:
        statement: Select[tuple[StorageArchive]] = select(StorageArchive).where(
            StorageArchive.company_id == company_id,
            StorageArchive.created_at <= cutoff,
            StorageArchive.status.in_(("ACTIVE", "COLD")),
        )
        result = await self.session.execute(
            statement.order_by(StorageArchive.created_at.asc(), StorageArchive.id.asc())
        )
        return list(result.scalars().all())

    async def create_job(
        self,
        *,
        company_id: UUID,
        storage_archive_id: UUID,
        status: str,
        processed_at: datetime,
        error_message: str | None = None,
    ) -> RetentionJob:
        job = RetentionJob(
            company_id=company_id,
            storage_archive_id=storage_archive_id,
            status=status,
            processed_at=processed_at,
            error_message=error_message,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def mark_documents_deleted_for_archive(
        self,
        *,
        company_id: UUID,
        storage_archive_id: UUID,
    ) -> None:
        await self.session.execute(
            update(FiscalDocument)
            .where(
                FiscalDocument.company_id == company_id,
                or_(
                    FiscalDocument.storage_archive_id == storage_archive_id,
                    FiscalDocument.xml_storage_archive_id == storage_archive_id,
                    FiscalDocument.pdf_storage_archive_id == storage_archive_id,
                ),
            )
            .values(status="DELETED")
        )

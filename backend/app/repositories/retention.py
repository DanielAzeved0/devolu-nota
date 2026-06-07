from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StorageArchive


class RetentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_archives_for_deletion(
        self,
        *,
        company_id: UUID,
        delete_retention_cutoff: datetime,
    ) -> list[StorageArchive]:
        result = await self.session.execute(
            select(StorageArchive).where(
                StorageArchive.company_id == company_id,
                StorageArchive.retention_until.is_not(None),
                StorageArchive.retention_until <= delete_retention_cutoff,
                StorageArchive.status.in_(("ACTIVE", "COLD")),
            )
        )
        return list(result.scalars().all())

    async def list_archives_for_cold_storage(
        self,
        *,
        company_id: UUID,
        cold_cutoff: datetime,
    ) -> list[StorageArchive]:
        result = await self.session.execute(
            select(StorageArchive).where(
                StorageArchive.company_id == company_id,
                StorageArchive.retention_until.is_not(None),
                StorageArchive.retention_until <= cold_cutoff,
                StorageArchive.status == "ACTIVE",
            )
        )
        return list(result.scalars().all())

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RetentionJob


class RetentionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        company_id: UUID,
        scheduled_for: datetime,
        storage_archive_id: UUID | None = None,
    ) -> RetentionJob:
        job = RetentionJob(
            company_id=company_id,
            storage_archive_id=storage_archive_id,
            status="RUNNING",
            scheduled_for=scheduled_for,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def mark_completed(self, *, job_id: UUID, processed_at: datetime) -> RetentionJob | None:
        job = await self.session.get(RetentionJob, job_id)
        if job is None:
            return None
        job.status = "COMPLETED"
        job.processed_at = processed_at
        job.error_message = None
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def mark_failed(
        self,
        *,
        job_id: UUID,
        processed_at: datetime,
        error_message: str,
    ) -> RetentionJob | None:
        job = await self.session.get(RetentionJob, job_id)
        if job is None:
            return None
        job.status = "FAILED"
        job.processed_at = processed_at
        job.error_message = error_message
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def list_recent_for_company(self, *, company_id: UUID, limit: int = 50) -> list[RetentionJob]:
        result = await self.session.execute(
            select(RetentionJob)
            .where(RetentionJob.company_id == company_id)
            .order_by(RetentionJob.created_at.desc(), RetentionJob.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

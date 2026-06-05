from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmissionBatch, EmissionJob, ReturnNote


class EmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_batch_by_company_id(
        self,
        *,
        company_id: UUID,
        batch_id: UUID,
    ) -> EmissionBatch | None:
        result = await self.session.execute(
            select(EmissionBatch).where(
                EmissionBatch.id == batch_id,
                EmissionBatch.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_jobs_by_batch_id(
        self,
        *,
        company_id: UUID,
        batch_id: UUID,
    ) -> list[EmissionJob]:
        result = await self.session.execute(
            select(EmissionJob)
            .where(
                EmissionJob.company_id == company_id,
                EmissionJob.batch_id == batch_id,
            )
            .order_by(EmissionJob.created_at, EmissionJob.id)
        )
        return list(result.scalars().all())

    async def list_return_notes_for_update(
        self,
        *,
        company_id: UUID,
        return_note_ids: Sequence[UUID],
    ) -> list[ReturnNote]:
        result = await self.session.execute(
            select(ReturnNote).where(
                ReturnNote.company_id == company_id,
                ReturnNote.id.in_(return_note_ids),
            )
        )
        return list(result.scalars().all())

    async def list_active_jobs_for_return_notes(
        self,
        *,
        company_id: UUID,
        return_note_ids: Sequence[UUID],
    ) -> list[EmissionJob]:
        result = await self.session.execute(
            select(EmissionJob).where(
                EmissionJob.company_id == company_id,
                EmissionJob.return_note_id.in_(return_note_ids),
                EmissionJob.status.in_(("PENDING", "RUNNING", "RETRYING")),
            )
        )
        return list(result.scalars().all())

    async def create_batch(
        self,
        *,
        company_id: UUID,
        requested_by_user_id: UUID,
    ) -> EmissionBatch:
        batch = EmissionBatch(
            company_id=company_id,
            requested_by_user_id=requested_by_user_id,
            status="PENDING",
        )
        self.session.add(batch)
        await self.session.flush()
        await self.session.refresh(batch)
        return batch

    async def create_job(
        self,
        *,
        company_id: UUID,
        batch_id: UUID,
        return_note_id: UUID,
    ) -> EmissionJob:
        job = EmissionJob(
            company_id=company_id,
            batch_id=batch_id,
            return_note_id=return_note_id,
            status="PENDING",
            attempts=0,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

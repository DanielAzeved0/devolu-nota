from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReturnNote

ACTIVE_RETURN_NOTE_STATUSES = (
    "DRAFT",
    "READY_TO_EMIT",
    "QUEUED",
    "PROCESSING",
    "ISSUED",
    "FAILED",
)


class ReturnNoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_by_return_order(
        self,
        *,
        company_id: UUID,
        return_order_id: UUID,
    ) -> ReturnNote | None:
        result = await self.session.execute(
            select(ReturnNote).where(
                ReturnNote.company_id == company_id,
                ReturnNote.return_order_id == return_order_id,
                ReturnNote.status.in_(ACTIVE_RETURN_NOTE_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_company_id(
        self,
        *,
        company_id: UUID,
        return_note_id: UUID,
    ) -> ReturnNote | None:
        result = await self.session.execute(
            select(ReturnNote).where(
                ReturnNote.id == return_note_id,
                ReturnNote.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_mock_draft(
        self,
        *,
        company_id: UUID,
        return_order_id: UUID,
        original_nfe_key: str,
    ) -> ReturnNote:
        return_note = ReturnNote(
            company_id=company_id,
            return_order_id=return_order_id,
            status="DRAFT",
            original_nfe_key=original_nfe_key,
        )
        self.session.add(return_note)
        await self.session.flush()
        await self.session.refresh(return_note)
        return return_note

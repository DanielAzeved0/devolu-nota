from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.users import UserRepository
from app.schemas.return_notes import ReturnNoteListResponse, ReturnNotePublic
from app.services.companies import CompanyNotFoundError, CompanyService
from app.services.return_notes import ReturnNoteNotFoundError, ReturnNoteQueryService

router = APIRouter(prefix="/api/v1/companies/{company_id}/return-notes", tags=["return-notes"])

ReturnNoteStatus = Literal[
    "DRAFT",
    "READY_TO_EMIT",
    "QUEUED",
    "PROCESSING",
    "ISSUED",
    "FAILED",
    "CANCELLED",
    "ARCHIVED",
    "DELETED_BY_RETENTION",
]


def build_return_note_query_service(session: AsyncSession) -> ReturnNoteQueryService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return ReturnNoteQueryService(
        companies=company_service,
        return_notes=ReturnNoteRepository(session),
    )


@router.get("", response_model=ReturnNoteListResponse, summary="Lista notas de devolucao persistidas")
async def list_return_notes(
    company_id: UUID,
    status_filter: ReturnNoteStatus | None = Query(default=None, alias="status"),
    return_order_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnNoteListResponse:
    service = build_return_note_query_service(session)
    try:
        return_notes = await service.list_company_return_notes(
            company_id=company_id,
            current_user=current_user,
            status=status_filter,
            return_order_id=return_order_id,
            limit=limit,
            offset=offset,
        )
    except CompanyNotFoundError:
        raise not_found("Company not found") from None

    return ReturnNoteListResponse(
        items=[ReturnNotePublic.model_validate(return_note) for return_note in return_notes],
        limit=limit,
        offset=offset,
        count=len(return_notes),
    )


@router.get(
    "/{return_note_id}",
    response_model=ReturnNotePublic,
    summary="Consulta nota de devolucao persistida",
)
async def get_return_note(
    company_id: UUID,
    return_note_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnNotePublic:
    service = build_return_note_query_service(session)
    try:
        return_note = await service.get_company_return_note(
            company_id=company_id,
            return_note_id=return_note_id,
            current_user=current_user,
        )
    except (CompanyNotFoundError, ReturnNoteNotFoundError):
        raise not_found("Return note not found") from None

    return ReturnNotePublic.model_validate(return_note)


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

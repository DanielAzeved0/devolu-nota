from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.emissions import EmissionRepository
from app.repositories.users import UserRepository
from app.schemas.emissions import (
    EmissionBatchCreatedResponse,
    EmissionBatchMockCreateRequest,
    EmissionBatchPublic,
    EmissionJobListResponse,
    EmissionJobPublic,
)
from app.services.companies import CompanyNotFoundError, CompanyPermissionDeniedError, CompanyService
from app.services.emissions import (
    EmissionBatchMockService,
    EmissionBatchNotFoundError,
    ReturnNoteAlreadyQueuedError,
    ReturnNoteNotEligibleError,
)

router = APIRouter(prefix="/api/v1/companies/{company_id}/emission-batches", tags=["emission-batches"])


def build_emission_batch_service(session: AsyncSession) -> EmissionBatchMockService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return EmissionBatchMockService(
        companies=company_service,
        emissions=EmissionRepository(session),
        audit_logs=AuditLogRepository(session),
    )


@router.post(
    "/mock",
    response_model=EmissionBatchCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria lote de emissao mockada",
)
async def create_mock_emission_batch(
    company_id: UUID,
    payload: EmissionBatchMockCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmissionBatchCreatedResponse:
    service = build_emission_batch_service(session)
    try:
        batch, jobs = await service.create_mock_batch(
            company_id=company_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
        await session.refresh(batch)
        for job in jobs:
            await session.refresh(job)
    except CompanyNotFoundError:
        await session.rollback()
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        await session.rollback()
        raise forbidden("Insufficient company role") from None
    except (ReturnNoteNotEligibleError, ReturnNoteAlreadyQueuedError) as exc:
        await session.rollback()
        raise conflict(str(exc)) from None

    return EmissionBatchCreatedResponse(
        **EmissionBatchPublic.model_validate(batch).model_dump(),
        jobs=[EmissionJobPublic.model_validate(job) for job in jobs],
    )


@router.get(
    "/{batch_id}",
    response_model=EmissionBatchPublic,
    summary="Consulta lote de emissao",
)
async def get_emission_batch(
    company_id: UUID,
    batch_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmissionBatchPublic:
    service = build_emission_batch_service(session)
    try:
        batch = await service.get_batch(
            company_id=company_id,
            batch_id=batch_id,
            current_user=current_user,
        )
    except (CompanyNotFoundError, EmissionBatchNotFoundError):
        raise not_found("Emission batch not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None

    return EmissionBatchPublic.model_validate(batch)


@router.get(
    "/{batch_id}/jobs",
    response_model=EmissionJobListResponse,
    summary="Lista jobs de um lote de emissao",
)
async def list_emission_batch_jobs(
    company_id: UUID,
    batch_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmissionJobListResponse:
    service = build_emission_batch_service(session)
    try:
        jobs = await service.list_jobs(
            company_id=company_id,
            batch_id=batch_id,
            current_user=current_user,
        )
    except (CompanyNotFoundError, EmissionBatchNotFoundError):
        raise not_found("Emission batch not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None

    return EmissionJobListResponse(items=[EmissionJobPublic.model_validate(job) for job in jobs])


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

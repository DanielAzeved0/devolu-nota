from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.retention import RetentionRepository
from app.repositories.users import UserRepository
from app.schemas.retention import RetentionApplyResponse
from app.services.audit_logs import AuditLogService
from app.services.companies import CompanyNotFoundError, CompanyPermissionDeniedError, CompanyService
from app.services.retention import RetentionService

router = APIRouter(prefix="/api/v1/companies/{company_id}/retention", tags=["retention"])


def build_retention_service(session: AsyncSession) -> RetentionService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return RetentionService(
        retention=RetentionRepository(session),
        companies=company_service,
        audit_logs=AuditLogService(
            audit_logs=AuditLogRepository(session),
            companies=company_service,
        ),
    )


@router.post(
    "/apply",
    response_model=RetentionApplyResponse,
    summary="Aplica politica de retencao da empresa",
)
async def apply_company_retention(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RetentionApplyResponse:
    service = build_retention_service(session)
    try:
        result = await service.apply_company_retention_for_user(
            company_id=company_id,
            current_user=current_user,
        )
        await session.commit()
    except CompanyNotFoundError:
        await session.rollback()
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        await session.rollback()
        raise forbidden("Insufficient company role") from None

    return RetentionApplyResponse(
        moved_to_cold=result.moved_to_cold,
        moved_to_deleted=result.moved_to_deleted,
        skipped=result.skipped,
    )


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

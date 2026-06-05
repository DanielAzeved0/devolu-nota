from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.users import UserRepository
from app.schemas.audit_logs import AuditLogListResponse, AuditLogPublic
from app.services.audit_logs import AuditLogService
from app.services.companies import CompanyNotFoundError, CompanyService

router = APIRouter(prefix="/api/v1/companies/{company_id}/audit-logs", tags=["audit-logs"])


def build_audit_log_service(session: AsyncSession) -> AuditLogService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return AuditLogService(
        audit_logs=AuditLogRepository(session),
        companies=company_service,
    )


@router.get("", response_model=AuditLogListResponse, summary="Lista historico operacional")
async def list_audit_logs(
    company_id: UUID,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    action: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AuditLogListResponse:
    service = build_audit_log_service(session)
    try:
        logs = await service.list_company_logs(
            company_id=company_id,
            current_user=current_user,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
            offset=offset,
        )
    except CompanyNotFoundError:
        raise not_found("Company not found") from None

    return AuditLogListResponse(
        items=[AuditLogPublic.model_validate(log) for log in logs],
        limit=limit,
        offset=offset,
    )


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

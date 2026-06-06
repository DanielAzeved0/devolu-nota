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
from app.schemas.retention import RetentionJobPublic, RetentionMockRunResponse
from app.services.audit_logs import AuditLogService
from app.services.companies import CompanyNotFoundError, CompanyService
from app.services.retention import RetentionMockService

router = APIRouter(prefix="/api/v1/companies/{company_id}/retention-jobs", tags=["retention"])


def build_retention_service(session: AsyncSession) -> RetentionMockService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return RetentionMockService(
        companies=company_service,
        retention=RetentionRepository(session),
    )


def build_audit_log_service(session: AsyncSession) -> AuditLogService:
    return AuditLogService(audit_logs=AuditLogRepository(session))


@router.post(
    "/mock-run",
    response_model=RetentionMockRunResponse,
    summary="Executa politica de retencao mockada",
)
async def run_mock_retention(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RetentionMockRunResponse:
    service = build_retention_service(session)
    audit_logs = build_audit_log_service(session)
    try:
        archived_count, deleted_count, skipped_count, jobs = await service.run_company_retention(
            company_id=company_id,
            current_user=current_user,
        )
        for job, action in jobs:
            await audit_logs.create_log(
                company_id=company_id,
                user_id=current_user.id,
                action=action,
                entity_type="retention_job",
                entity_id=job.id,
                metadata={
                    "storage_archive_id": str(job.storage_archive_id),
                    "status": job.status,
                },
            )
        await session.commit()
    except CompanyNotFoundError:
        await session.rollback()
        raise not_found("Company not found") from None

    return RetentionMockRunResponse(
        company_id=company_id,
        archived_count=archived_count,
        deleted_count=deleted_count,
        skipped_count=skipped_count,
        jobs=[
            RetentionJobPublic(
                id=job.id,
                company_id=job.company_id,
                storage_archive_id=job.storage_archive_id,
                status=job.status,
                error_message=job.error_message,
            )
            for job, _action in jobs
        ],
    )


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

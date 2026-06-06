from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.users import UserRepository
from app.schemas.fiscal_documents import (
    FiscalDocumentListResponse,
    FiscalDocumentMockStoreRequest,
    FiscalDocumentPublic,
)
from app.services.audit_logs import AuditLogService
from app.services.companies import CompanyNotFoundError, CompanyService
from app.services.fiscal_documents import FiscalDocumentStorageService
from app.services.return_notes import ReturnNoteNotFoundError

router = APIRouter(
    prefix="/api/v1/companies/{company_id}/return-notes/{return_note_id}/fiscal-documents",
    tags=["fiscal-documents"],
)


def build_fiscal_document_service(session: AsyncSession) -> FiscalDocumentStorageService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return FiscalDocumentStorageService(
        companies=company_service,
        return_notes=ReturnNoteRepository(session),
        fiscal_documents=FiscalDocumentRepository(session),
    )


def build_audit_log_service(session: AsyncSession) -> AuditLogService:
    return AuditLogService(audit_logs=AuditLogRepository(session))


@router.post(
    "/mock",
    response_model=FiscalDocumentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Registra documento fiscal em storage mockado",
)
async def store_mock_fiscal_document(
    company_id: UUID,
    return_note_id: UUID,
    payload: FiscalDocumentMockStoreRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FiscalDocumentPublic:
    service = build_fiscal_document_service(session)
    audit_logs = build_audit_log_service(session)
    try:
        fiscal_document = await service.store_mock_document(
            company_id=company_id,
            return_note_id=return_note_id,
            payload=payload,
            current_user=current_user,
        )
        await audit_logs.create_log(
            company_id=company_id,
            user_id=current_user.id,
            action="FISCAL_DOCUMENT_STORED",
            entity_type="fiscal_document",
            entity_id=fiscal_document.id,
            metadata={
                "document_type": fiscal_document.document_type,
                "status": fiscal_document.status,
                "return_note_id": str(return_note_id),
                "storage_archive_id": str(fiscal_document.storage_archive_id),
            },
        )
        await session.commit()
        await session.refresh(fiscal_document)
    except (CompanyNotFoundError, ReturnNoteNotFoundError):
        await session.rollback()
        raise not_found("Return note not found") from None

    return FiscalDocumentPublic.model_validate(fiscal_document)


@router.get(
    "",
    response_model=FiscalDocumentListResponse,
    summary="Lista documentos fiscais vinculados a nota",
)
async def list_fiscal_documents(
    company_id: UUID,
    return_note_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FiscalDocumentListResponse:
    service = build_fiscal_document_service(session)
    try:
        documents = await service.list_return_note_documents(
            company_id=company_id,
            return_note_id=return_note_id,
            current_user=current_user,
            limit=limit,
            offset=offset,
        )
    except (CompanyNotFoundError, ReturnNoteNotFoundError):
        raise not_found("Return note not found") from None

    return FiscalDocumentListResponse(
        items=[FiscalDocumentPublic.model_validate(document) for document in documents],
        limit=limit,
        offset=offset,
        count=len(documents),
    )


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

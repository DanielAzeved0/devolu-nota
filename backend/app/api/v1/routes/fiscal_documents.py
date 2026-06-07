from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.users import UserRepository
from app.schemas.fiscal_documents import FiscalDocumentListResponse, FiscalDocumentPublic
from app.services.companies import CompanyNotFoundError, CompanyPermissionDeniedError, CompanyService
from app.services.fiscal_documents import (
    FiscalDocumentIntegrityError,
    FiscalDocumentNotFoundError,
    FiscalDocumentStorageService,
)

router = APIRouter(prefix="/api/v1/companies/{company_id}/fiscal-documents", tags=["fiscal-documents"])


def build_fiscal_document_service(session: AsyncSession) -> FiscalDocumentStorageService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return FiscalDocumentStorageService(
        fiscal_documents=FiscalDocumentRepository(session),
        return_notes=ReturnNoteRepository(session),
        companies=company_service,
    )


@router.get("", response_model=FiscalDocumentListResponse, summary="Lista documentos fiscais")
async def list_fiscal_documents(
    company_id: UUID,
    return_note_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FiscalDocumentListResponse:
    service = build_fiscal_document_service(session)
    try:
        documents = await service.list_documents(
            company_id=company_id,
            current_user=current_user,
            return_note_id=return_note_id,
            limit=limit,
            offset=offset,
        )
    except CompanyNotFoundError:
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None

    return FiscalDocumentListResponse(
        items=[FiscalDocumentPublic.model_validate(document) for document in documents],
        limit=limit,
        offset=offset,
    )


@router.get("/{fiscal_document_id}/download", summary="Baixa documento fiscal armazenado")
async def download_fiscal_document(
    company_id: UUID,
    fiscal_document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    service = build_fiscal_document_service(session)
    try:
        stored = await service.read_document_for_user(
            company_id=company_id,
            fiscal_document_id=fiscal_document_id,
            current_user=current_user,
        )
    except (CompanyNotFoundError, FiscalDocumentNotFoundError):
        raise not_found("Fiscal document not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None
    except FiscalDocumentIntegrityError:
        raise conflict("Fiscal document checksum mismatch") from None

    return Response(
        content=stored.content,
        media_type=stored.archive.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{stored.document.document_type.lower()}-{stored.document.id}"'
            )
        },
    )


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

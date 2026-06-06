from uuid import UUID

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.integrations.errors import MockIntegrationError
from app.models import User
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.return_orders import ReturnOrderRepository
from app.repositories.users import UserRepository
from app.schemas.return_notes import ReturnNoteMockCreateRequest, ReturnNotePublic
from app.schemas.mock_integrations import MarketplaceProvider
from app.schemas.return_orders import (
    ReturnOrderListResponse,
    ReturnOrderMockSyncRequest,
    ReturnOrderMockSyncResponse,
    ReturnOrderPublic,
)
from app.services.companies import CompanyNotFoundError, CompanyService
from app.services.return_notes import (
    ReturnNoteAlreadyExistsError,
    ReturnNoteInvalidOriginalInvoiceError,
    ReturnNoteMockCreationService,
)
from app.services.return_orders import (
    ReturnOrderMockSyncService,
    ReturnOrderNotFoundError,
    ReturnOrderQueryService,
)

ReturnOrderStatus = Literal["OPEN", "READY_TO_REVIEW", "LINKED_TO_NFE", "CANCELLED", "ARCHIVED"]

router = APIRouter(prefix="/api/v1/companies/{company_id}/return-orders", tags=["return-orders"])


def build_return_order_mock_sync_service(session: AsyncSession) -> ReturnOrderMockSyncService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return ReturnOrderMockSyncService(
        companies=company_service,
        return_orders=ReturnOrderRepository(session),
    )


def build_return_note_mock_creation_service(session: AsyncSession) -> ReturnNoteMockCreationService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return ReturnNoteMockCreationService(
        companies=company_service,
        return_orders=ReturnOrderRepository(session),
        return_notes=ReturnNoteRepository(session),
    )


def build_return_order_query_service(session: AsyncSession) -> ReturnOrderQueryService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return ReturnOrderQueryService(
        companies=company_service,
        return_orders=ReturnOrderRepository(session),
    )


@router.get("", response_model=ReturnOrderListResponse, summary="Lista devolucoes persistidas")
async def list_return_orders(
    company_id: UUID,
    status_filter: ReturnOrderStatus | None = Query(default=None, alias="status"),
    marketplace: MarketplaceProvider | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnOrderListResponse:
    service = build_return_order_query_service(session)
    try:
        return_orders = await service.list_company_return_orders(
            company_id=company_id,
            current_user=current_user,
            status=status_filter,
            marketplace=marketplace,
            limit=limit,
            offset=offset,
        )
    except CompanyNotFoundError:
        raise not_found("Company not found") from None

    return ReturnOrderListResponse(
        items=[ReturnOrderPublic.model_validate(return_order) for return_order in return_orders],
        limit=limit,
        offset=offset,
        count=len(return_orders),
    )


@router.get(
    "/{return_order_id}",
    response_model=ReturnOrderPublic,
    summary="Consulta devolucao persistida",
)
async def get_return_order(
    company_id: UUID,
    return_order_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnOrderPublic:
    service = build_return_order_query_service(session)
    try:
        return_order = await service.get_company_return_order(
            company_id=company_id,
            return_order_id=return_order_id,
            current_user=current_user,
        )
    except (CompanyNotFoundError, ReturnOrderNotFoundError):
        raise not_found("Return order not found") from None

    return ReturnOrderPublic.model_validate(return_order)


@router.post(
    "/mock-sync",
    response_model=ReturnOrderMockSyncResponse,
    summary="Sincroniza devolucoes mockadas de marketplace",
)
async def sync_mock_return_orders(
    company_id: UUID,
    payload: ReturnOrderMockSyncRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnOrderMockSyncResponse:
    service = build_return_order_mock_sync_service(session)
    try:
        response = await service.sync_marketplace_returns(
            company_id=company_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
    except CompanyNotFoundError:
        await session.rollback()
        raise not_found("Company not found") from None
    except MockIntegrationError as exc:
        await session.rollback()
        raise provider_error(exc) from None

    return response


@router.post(
    "/{return_order_id}/return-notes/mock",
    response_model=ReturnNotePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Cria nota de entrada de devolucao mockada",
)
async def create_mock_return_note(
    company_id: UUID,
    return_order_id: UUID,
    payload: ReturnNoteMockCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReturnNotePublic:
    service = build_return_note_mock_creation_service(session)
    try:
        return_note = await service.create_mock_return_note(
            company_id=company_id,
            return_order_id=return_order_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
        await session.refresh(return_note)
    except (CompanyNotFoundError, ReturnOrderNotFoundError):
        await session.rollback()
        raise not_found("Return order not found") from None
    except ReturnNoteAlreadyExistsError:
        await session.rollback()
        raise conflict("Return note already exists") from None
    except ReturnNoteInvalidOriginalInvoiceError:
        await session.rollback()
        raise unprocessable("Original invoice key is invalid") from None
    except MockIntegrationError as exc:
        await session.rollback()
        raise provider_error(exc) from None

    return ReturnNotePublic.model_validate(return_note)


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def provider_error(exc: MockIntegrationError) -> HTTPException:
    status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if exc.payload.retryable
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(status_code=status_code, detail=exc.payload.model_dump())

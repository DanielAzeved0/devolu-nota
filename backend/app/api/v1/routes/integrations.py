from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.integrations import IntegrationRepository
from app.repositories.users import UserRepository
from app.schemas.integrations import (
    IntegrationCreateRequest,
    IntegrationCredentialsRequest,
    IntegrationPublic,
    IntegrationUpdateRequest,
)
from app.services.companies import CompanyNotFoundError, CompanyPermissionDeniedError, CompanyService
from app.services.integrations import IntegrationNotFoundError, IntegrationService

router = APIRouter(prefix="/api/v1/companies/{company_id}/integrations", tags=["integrations"])


def build_integration_service(session: AsyncSession) -> IntegrationService:
    company_service = CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )
    return IntegrationService(
        integrations=IntegrationRepository(session),
        companies=company_service,
    )


@router.post(
    "",
    response_model=IntegrationPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Cria integracao para uma empresa",
)
async def create_integration(
    company_id: UUID,
    payload: IntegrationCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> IntegrationPublic:
    service = build_integration_service(session)
    try:
        integration = await service.create_integration(
            company_id=company_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
        await session.refresh(integration)
    except CompanyNotFoundError:
        await session.rollback()
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        await session.rollback()
        raise forbidden("Insufficient company role") from None

    return IntegrationPublic.model_validate(integration)


@router.get("", response_model=list[IntegrationPublic], summary="Lista integracoes da empresa")
async def list_integrations(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[IntegrationPublic]:
    service = build_integration_service(session)
    try:
        integrations = await service.list_integrations(company_id=company_id, current_user=current_user)
    except CompanyNotFoundError:
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None

    return [IntegrationPublic.model_validate(integration) for integration in integrations]


@router.get(
    "/{integration_id}",
    response_model=IntegrationPublic,
    summary="Consulta integracao da empresa",
)
async def get_integration(
    company_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> IntegrationPublic:
    service = build_integration_service(session)
    try:
        integration = await service.get_integration(
            company_id=company_id,
            integration_id=integration_id,
            current_user=current_user,
        )
    except (CompanyNotFoundError, IntegrationNotFoundError):
        raise not_found("Integration not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None

    return IntegrationPublic.model_validate(integration)


@router.patch(
    "/{integration_id}",
    response_model=IntegrationPublic,
    summary="Atualiza status e configuracoes nao sensiveis",
)
async def update_integration(
    company_id: UUID,
    integration_id: UUID,
    payload: IntegrationUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> IntegrationPublic:
    service = build_integration_service(session)
    try:
        integration = await service.update_integration(
            company_id=company_id,
            integration_id=integration_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
        await session.refresh(integration)
    except (CompanyNotFoundError, IntegrationNotFoundError):
        await session.rollback()
        raise not_found("Integration not found") from None
    except CompanyPermissionDeniedError:
        await session.rollback()
        raise forbidden("Insufficient company role") from None

    return IntegrationPublic.model_validate(integration)


@router.put(
    "/{integration_id}/credentials",
    response_model=IntegrationPublic,
    summary="Substitui credenciais sensiveis da integracao",
)
async def replace_integration_credentials(
    company_id: UUID,
    integration_id: UUID,
    payload: IntegrationCredentialsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> IntegrationPublic:
    service = build_integration_service(session)
    try:
        integration = await service.replace_credentials(
            company_id=company_id,
            integration_id=integration_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
        await session.refresh(integration)
    except (CompanyNotFoundError, IntegrationNotFoundError):
        await session.rollback()
        raise not_found("Integration not found") from None
    except CompanyPermissionDeniedError:
        await session.rollback()
        raise forbidden("Insufficient company role") from None

    return IntegrationPublic.model_validate(integration)


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

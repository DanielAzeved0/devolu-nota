from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.users import UserRepository
from app.schemas.companies import (
    CompanyCreateRequest,
    CompanyPublic,
    CompanyUserCreateRequest,
    CompanyUserPublic,
)
from app.services.companies import (
    CompanyDocumentAlreadyExistsError,
    CompanyNotFoundError,
    CompanyPermissionDeniedError,
    CompanyService,
    CompanyUserAlreadyExistsError,
    UserNotFoundError,
)

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


def build_company_service(session: AsyncSession) -> CompanyService:
    return CompanyService(
        companies=CompanyRepository(session),
        company_users=CompanyUserRepository(session),
        users=UserRepository(session),
    )


@router.post(
    "",
    response_model=CompanyPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma empresa",
)
async def create_company(
    payload: CompanyCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyPublic:
    service = build_company_service(session)
    try:
        company = await service.create_company(payload=payload, current_user=current_user)
        await session.commit()
        await session.refresh(company)
    except CompanyDocumentAlreadyExistsError:
        await session.rollback()
        raise conflict("Company document already exists") from None
    except IntegrityError:
        await session.rollback()
        raise conflict("Company document already exists") from None

    return CompanyPublic.model_validate(company)


@router.get("", response_model=list[CompanyPublic], summary="Lista empresas acessiveis")
async def list_companies(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[CompanyPublic]:
    service = build_company_service(session)
    companies = await service.list_companies(current_user)
    return [CompanyPublic.model_validate(company) for company in companies]


@router.get("/{company_id}", response_model=CompanyPublic, summary="Consulta empresa acessivel")
async def get_company(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyPublic:
    service = build_company_service(session)
    try:
        company = await service.get_company(company_id=company_id, current_user=current_user)
    except CompanyNotFoundError:
        raise not_found("Company not found") from None

    return CompanyPublic.model_validate(company)


@router.get(
    "/{company_id}/users",
    response_model=list[CompanyUserPublic],
    summary="Lista usuarios vinculados a empresa",
)
async def list_company_users(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[CompanyUserPublic]:
    service = build_company_service(session)
    try:
        return await service.list_company_users(company_id=company_id, current_user=current_user)
    except CompanyNotFoundError:
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        raise forbidden("Insufficient company role") from None


@router.post(
    "/{company_id}/users",
    response_model=CompanyUserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Vincula usuario existente a empresa",
)
async def add_company_user(
    company_id: UUID,
    payload: CompanyUserCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyUserPublic:
    service = build_company_service(session)
    try:
        membership = await service.add_company_user(
            company_id=company_id,
            payload=payload,
            current_user=current_user,
        )
        await session.commit()
    except CompanyNotFoundError:
        await session.rollback()
        raise not_found("Company not found") from None
    except CompanyPermissionDeniedError:
        await session.rollback()
        raise forbidden("Insufficient company role") from None
    except UserNotFoundError:
        await session.rollback()
        raise not_found("User not found") from None
    except CompanyUserAlreadyExistsError:
        await session.rollback()
        raise conflict("Company user already exists") from None
    except IntegrityError:
        await session.rollback()
        raise conflict("Company user already exists") from None

    return membership


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

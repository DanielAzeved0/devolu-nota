from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth import AuthService, DuplicateEmailError, InactiveUserError, InvalidCredentialsError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def build_auth_service(session: AsyncSession) -> AuthService:
    return AuthService(UserRepository(session))


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra um usuario",
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = build_auth_service(session)
    try:
        _, tokens = await service.register(payload)
        await session.commit()
    except DuplicateEmailError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    return tokens


@router.post("/login", response_model=TokenResponse, summary="Autentica um usuario")
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = build_auth_service(session)
    try:
        return await service.login(payload)
    except InvalidCredentialsError:
        raise invalid_credentials() from None
    except InactiveUserError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")


@router.post("/refresh", response_model=TokenResponse, summary="Renova o access token")
async def refresh(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = build_auth_service(session)
    try:
        return await service.refresh(payload.refresh_token)
    except InvalidCredentialsError:
        raise invalid_credentials() from None
    except InactiveUserError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")


@router.get("/me", response_model=AuthenticatedUserResponse, summary="Retorna o usuario autenticado")
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

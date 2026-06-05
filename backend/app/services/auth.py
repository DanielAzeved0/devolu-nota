from uuid import UUID

from app.core.security import (
    REFRESH_TOKEN_TYPE,
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_expires_in_seconds,
    verify_password,
)
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


class DuplicateEmailError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class InactiveUserError(ValueError):
    pass


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def register(self, payload: RegisterRequest) -> tuple[User, TokenResponse]:
        existing_user = await self.users.get_by_email(payload.email)
        if existing_user is not None:
            raise DuplicateEmailError("Email already exists")

        user = await self.users.create(
            email=payload.email,
            name=payload.name.strip(),
            password_hash=hash_password(payload.password),
        )
        return user, self._issue_tokens(user)

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.users.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise InvalidCredentialsError("Invalid credentials")

        self._ensure_active(user)
        return self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError, TokenValidationError) as exc:
            raise InvalidCredentialsError("Invalid token") from exc

        user = await self.users.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("Invalid token")

        self._ensure_active(user)
        return self._issue_tokens(user)

    def _issue_tokens(self, user: User) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            expires_in=token_expires_in_seconds(),
        )

    def _ensure_active(self, user: User) -> None:
        if user.status != "ACTIVE" or user.deleted_at is not None:
            raise InactiveUserError("Inactive user")

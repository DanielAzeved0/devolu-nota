from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


class TokenValidationError(ValueError):
    pass


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return create_token(subject=user_id, token_type=ACCESS_TOKEN_TYPE, expires_delta=expires_delta)


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()
    expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    return create_token(subject=user_id, token_type=REFRESH_TOKEN_TYPE, expires_delta=expires_delta)


def create_token(subject: UUID, token_type: str, expires_delta: timedelta) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + expires_delta
    payload = {"sub": str(subject), "type": token_type, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    settings = get_settings()

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise TokenValidationError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise TokenValidationError("Invalid token type")

    subject = payload.get("sub")
    if not subject:
        raise TokenValidationError("Invalid token subject")

    return payload


def token_expires_in_seconds() -> int:
    settings = get_settings()
    return settings.jwt_access_token_expire_minutes * 60

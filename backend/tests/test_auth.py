import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.security import ACCESS_TOKEN_TYPE, REFRESH_TOKEN_TYPE, ALGORITHM, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import User

pytestmark = pytest.mark.asyncio


async def database_available() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except OperationalError:
        return False
    return True


@pytest_asyncio.fixture(autouse=True)
async def require_database() -> None:
    if not await database_available():
        pytest.skip("PostgreSQL local indisponivel para testes de autenticacao")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4()}@example.com"


async def delete_user(email: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email == email))
        await session.commit()


async def get_user(email: str) -> User | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


async def create_inactive_user(email: str, password: str) -> User:
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            name="Inactive User",
            password_hash=hash_password(password),
            status="DISABLED",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def decode_without_verifying_exp(token: str) -> dict[str, object]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])


async def test_register_creates_user_with_password_hash_and_returns_tokens(
    client: AsyncClient, unique_email: str
) -> None:
    await delete_user(unique_email)

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email.upper(), "name": "Test User", "password": "strong-pass"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 900
    assert "password" not in body
    assert "password_hash" not in body

    user = await get_user(unique_email)
    assert user is not None
    assert user.email == unique_email
    assert user.password_hash != "strong-pass"
    assert user.password_hash.startswith("$2")


async def test_register_rejects_duplicate_email(client: AsyncClient, unique_email: str) -> None:
    await delete_user(unique_email)

    payload = {"email": unique_email, "name": "Test User", "password": "strong-pass"}

    first_response = await client.post("/api/v1/auth/register", json=payload)
    second_response = await client.post("/api/v1/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_login_returns_typed_access_and_refresh_tokens(
    client: AsyncClient, unique_email: str
) -> None:
    await delete_user(unique_email)
    password = "strong-pass"
    await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "name": "Test User", "password": password},
    )

    response = await client.post("/api/v1/auth/login", json={"email": unique_email, "password": password})

    assert response.status_code == 200
    body = response.json()
    access_payload = decode_without_verifying_exp(body["access_token"])
    refresh_payload = decode_without_verifying_exp(body["refresh_token"])
    assert access_payload["type"] == ACCESS_TOKEN_TYPE
    assert refresh_payload["type"] == REFRESH_TOKEN_TYPE
    assert access_payload["sub"] == refresh_payload["sub"]
    assert "exp" in access_payload
    assert "exp" in refresh_payload


async def test_login_rejects_invalid_credentials_without_user_enumeration(
    client: AsyncClient, unique_email: str
) -> None:
    await delete_user(unique_email)
    await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "name": "Test User", "password": "strong-pass"},
    )

    wrong_password_response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "wrong-pass"},
    )
    missing_user_response = await client.post(
        "/api/v1/auth/login",
        json={"email": f"missing-{unique_email}", "password": "wrong-pass"},
    )

    assert wrong_password_response.status_code == 401
    assert missing_user_response.status_code == 401
    assert wrong_password_response.json() == missing_user_response.json()


async def test_me_requires_valid_access_token(client: AsyncClient, unique_email: str) -> None:
    await delete_user(unique_email)
    password = "strong-pass"
    await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "name": "Test User", "password": password},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": password},
    )
    tokens = login_response.json()

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    refresh_as_access_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    missing_token_response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == unique_email
    assert "password_hash" not in response.json()
    assert refresh_as_access_response.status_code == 401
    assert missing_token_response.status_code == 401


async def test_refresh_requires_refresh_token(client: AsyncClient, unique_email: str) -> None:
    await delete_user(unique_email)
    password = "strong-pass"
    await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "name": "Test User", "password": password},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": password},
    )
    tokens = login_response.json()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    access_as_refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]
    assert access_as_refresh_response.status_code == 401


async def test_inactive_user_cannot_login(client: AsyncClient, unique_email: str) -> None:
    await delete_user(unique_email)
    await create_inactive_user(unique_email, "strong-pass")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "strong-pass"},
    )

    assert response.status_code == 403

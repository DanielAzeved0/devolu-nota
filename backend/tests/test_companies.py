import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import CompanyUser

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
        pytest.skip("PostgreSQL local indisponivel para testes de empresas")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


async def register_user(client: AsyncClient) -> dict[str, object]:
    email = f"user-{uuid.uuid4()}@example.com"
    password = "strong-pass"
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Test User", "password": password},
    )
    assert register_response.status_code == 201
    tokens = register_response.json()
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    return {
        "email": email,
        "password": password,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "user": me_response.json(),
    }


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def create_company(client: AsyncClient, access_token: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/companies",
        headers=auth_headers(access_token),
        json={
            "legal_name": f"Empresa {uuid.uuid4()}",
            "trade_name": "Loja Teste",
            "document": f"DOC{uuid.uuid4().hex[:20]}",
        },
    )
    assert response.status_code == 201
    return response.json()


async def get_membership(company_id: str, user_id: str) -> CompanyUser | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == uuid.UUID(company_id),
                CompanyUser.user_id == uuid.UUID(user_id),
            )
        )
        return result.scalar_one_or_none()


async def disable_membership(company_id: str, user_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(CompanyUser)
            .where(
                CompanyUser.company_id == uuid.UUID(company_id),
                CompanyUser.user_id == uuid.UUID(user_id),
            )
            .values(status="DISABLED")
        )
        await session.commit()


async def test_create_company_links_current_user_as_owner(client: AsyncClient) -> None:
    owner = await register_user(client)

    company = await create_company(client, str(owner["access_token"]))

    membership = await get_membership(str(company["id"]), str(owner["user"]["id"]))
    assert membership is not None
    assert membership.role == "OWNER"
    assert membership.status == "ACTIVE"
    assert company["status"] == "ACTIVE"
    assert "password_hash" not in str(company)


async def test_list_and_get_companies_are_scoped_to_current_user(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    owner_list_response = await client.get(
        "/api/v1/companies",
        headers=auth_headers(str(owner["access_token"])),
    )
    outsider_list_response = await client.get(
        "/api/v1/companies",
        headers=auth_headers(str(outsider["access_token"])),
    )
    owner_get_response = await client.get(
        f"/api/v1/companies/{company['id']}",
        headers=auth_headers(str(owner["access_token"])),
    )
    outsider_get_response = await client.get(
        f"/api/v1/companies/{company['id']}",
        headers=auth_headers(str(outsider["access_token"])),
    )

    assert owner_get_response.status_code == 200
    assert owner_get_response.json()["id"] == company["id"]
    assert company["id"] in [item["id"] for item in owner_list_response.json()]
    assert company["id"] not in [item["id"] for item in outsider_list_response.json()]
    assert outsider_get_response.status_code == 404


async def test_create_company_rejects_duplicate_document(client: AsyncClient) -> None:
    first_user = await register_user(client)
    second_user = await register_user(client)
    document = f"DOC{uuid.uuid4().hex[:20]}"
    payload = {"legal_name": "Empresa Duplicada", "trade_name": None, "document": document}

    first_response = await client.post(
        "/api/v1/companies",
        headers=auth_headers(str(first_user["access_token"])),
        json=payload,
    )
    second_response = await client.post(
        "/api/v1/companies",
        headers=auth_headers(str(second_user["access_token"])),
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_add_and_list_company_users(client: AsyncClient) -> None:
    owner = await register_user(client)
    target = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    add_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json={"user_id": target["user"]["id"], "role": "OPERATOR"},
    )
    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
    )

    assert add_response.status_code == 201
    assert add_response.json()["user_id"] == target["user"]["id"]
    assert add_response.json()["role"] == "OPERATOR"
    assert "password_hash" not in str(add_response.json())
    listed_user_ids = [item["user_id"] for item in list_response.json()]
    assert target["user"]["id"] in listed_user_ids
    assert owner["user"]["id"] in listed_user_ids


async def test_add_company_user_requires_admin_role(client: AsyncClient) -> None:
    owner = await register_user(client)
    admin = await register_user(client)
    viewer = await register_user(client)
    target = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    admin_add_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json={"user_id": admin["user"]["id"], "role": "ADMIN"},
    )
    viewer_add_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json={"user_id": viewer["user"]["id"], "role": "VIEWER"},
    )
    admin_adds_target_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(admin["access_token"])),
        json={"user_id": target["user"]["id"], "role": "OPERATOR"},
    )
    viewer_adds_target_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(viewer["access_token"])),
        json={"user_id": target["user"]["id"], "role": "VIEWER"},
    )

    assert admin_add_response.status_code == 201
    assert viewer_add_response.status_code == 201
    assert admin_adds_target_response.status_code == 201
    assert viewer_adds_target_response.status_code == 403


async def test_add_company_user_rejects_duplicate_and_missing_user(client: AsyncClient) -> None:
    owner = await register_user(client)
    target = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    payload = {"user_id": target["user"]["id"], "role": "VIEWER"}

    first_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json=payload,
    )
    duplicate_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json=payload,
    )
    missing_user_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json={"user_id": str(uuid.uuid4()), "role": "VIEWER"},
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert missing_user_response.status_code == 404


async def test_company_user_routes_deny_cross_tenant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    target = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(outsider["access_token"])),
    )
    add_response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(outsider["access_token"])),
        json={"user_id": target["user"]["id"], "role": "VIEWER"},
    )

    assert list_response.status_code == 404
    assert add_response.status_code == 404


async def test_inactive_company_membership_does_not_grant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    await disable_membership(str(company["id"]), str(owner["user"]["id"]))

    list_response = await client.get(
        "/api/v1/companies",
        headers=auth_headers(str(owner["access_token"])),
    )
    get_response = await client.get(
        f"/api/v1/companies/{company['id']}",
        headers=auth_headers(str(owner["access_token"])),
    )
    users_response = await client.get(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
    )

    assert company["id"] not in [item["id"] for item in list_response.json()]
    assert get_response.status_code == 404
    assert users_response.status_code == 404


async def test_company_routes_require_access_token_not_refresh_token(client: AsyncClient) -> None:
    user = await register_user(client)

    missing_token_response = await client.get("/api/v1/companies")
    refresh_token_response = await client.get(
        "/api/v1/companies",
        headers=auth_headers(str(user["refresh_token"])),
    )

    assert missing_token_response.status_code == 401
    assert refresh_token_response.status_code == 401


async def test_add_company_user_rejects_invalid_role(client: AsyncClient) -> None:
    owner = await register_user(client)
    target = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    response = await client.post(
        f"/api/v1/companies/{company['id']}/users",
        headers=auth_headers(str(owner["access_token"])),
        json={"user_id": target["user"]["id"], "role": "INVALID"},
    )

    assert response.status_code == 422

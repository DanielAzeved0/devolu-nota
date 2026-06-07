import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import ReturnOrder

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
        pytest.skip("PostgreSQL local indisponivel para testes de return orders")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


async def register_user(client: AsyncClient) -> dict[str, object]:
    email = f"user-{uuid.uuid4()}@example.com"
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Test User", "password": "strong-pass"},
    )
    assert register_response.status_code == 201
    tokens = register_response.json()
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    return {**tokens, "user": me_response.json()}


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


async def add_company_user(
    client: AsyncClient,
    *,
    owner_access_token: str,
    company_id: str,
    user_id: str,
    role: str,
) -> None:
    response = await client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=auth_headers(owner_access_token),
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201


async def list_return_orders(company_id: str) -> list[ReturnOrder]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ReturnOrder).where(ReturnOrder.company_id == uuid.UUID(company_id))
        )
        return list(result.scalars().all())


async def set_original_nfe_key(return_order_id: str, original_nfe_key: str) -> None:
    async with AsyncSessionLocal() as session:
        return_order = await session.get(ReturnOrder, uuid.UUID(return_order_id))
        assert return_order is not None
        return_order.original_nfe_key = original_nfe_key
        await session.commit()


def assert_payload_has_no_secrets(payload: object) -> None:
    serialized = str(payload)
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "api_token" not in serialized
    assert "client_secret" not in serialized
    assert "encrypted_credentials" not in serialized


async def sync_mock_returns(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    marketplace: str,
    scenario: str = "success",
) -> object:
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/mock-sync",
        headers=auth_headers(access_token),
        json={"marketplace": marketplace, "scenario": scenario},
    )
    return response


async def test_sync_mercado_livre_mock_returns_persists_return_order(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["company_id"] == company["id"]
    assert payload["marketplace"] == "MERCADO_LIVRE"
    assert payload["created"] == 1
    assert payload["updated"] == 0
    assert payload["skipped"] == 0
    assert payload["items"][0]["marketplace"] == "MERCADO_LIVRE"
    assert payload["items"][0]["external_order_id"] == "ML-RETURN-1001"
    assert payload["items"][0]["status"] == "OPEN"
    assert payload["items"][0]["payload"]["status"] == "RETURNED"
    assert_payload_has_no_secrets(payload)

    stored_return_orders = await list_return_orders(str(company["id"]))
    assert len(stored_return_orders) == 1
    assert stored_return_orders[0].company_id == uuid.UUID(str(company["id"]))
    assert stored_return_orders[0].marketplace == "MERCADO_LIVRE"
    assert stored_return_orders[0].external_order_id == "ML-RETURN-1001"


async def test_sync_shopee_mock_returns_persists_return_order(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] == 1
    assert payload["items"][0]["marketplace"] == "SHOPEE"
    assert payload["items"][0]["external_order_id"] == "SHP-RETURN-2001"
    assert_payload_has_no_secrets(payload)

    stored_return_orders = await list_return_orders(str(company["id"]))
    assert len(stored_return_orders) == 1
    assert stored_return_orders[0].marketplace == "SHOPEE"


async def test_sync_mock_returns_is_idempotent(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    first_response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    second_response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["created"] == 1
    assert second_response.json()["created"] == 0
    assert second_response.json()["updated"] == 0
    assert second_response.json()["skipped"] == 1
    stored_return_orders = await list_return_orders(str(company["id"]))
    assert len(stored_return_orders) == 1


async def test_sync_mock_returns_preserves_existing_original_nfe_key(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    original_nfe_key = "35260612345678000199550010000010011000010010"
    await set_original_nfe_key(response.json()["items"][0]["id"], original_nfe_key)

    second_response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    assert second_response.status_code == 200
    stored_return_orders = await list_return_orders(str(company["id"]))
    assert len(stored_return_orders) == 1
    assert stored_return_orders[0].original_nfe_key == original_nfe_key


async def test_sync_mock_returns_denies_cross_tenant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    response = await sync_mock_returns(
        client,
        access_token=str(outsider["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    assert response.status_code == 404
    assert await list_return_orders(str(company["id"])) == []


async def test_sync_mock_returns_requires_operator_role(client: AsyncClient) -> None:
    owner = await register_user(client)
    operator = await register_user(client)
    viewer = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    await add_company_user(
        client,
        owner_access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        user_id=str(operator["user"]["id"]),
        role="OPERATOR",
    )
    await add_company_user(
        client,
        owner_access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        user_id=str(viewer["user"]["id"]),
        role="VIEWER",
    )

    operator_response = await sync_mock_returns(
        client,
        access_token=str(operator["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    viewer_response = await sync_mock_returns(
        client,
        access_token=str(viewer["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )

    assert operator_response.status_code == 200
    assert viewer_response.status_code == 403
    stored_return_orders = await list_return_orders(str(company["id"]))
    assert len(stored_return_orders) == 1
    assert stored_return_orders[0].marketplace == "MERCADO_LIVRE"


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_code", "retryable"),
    [
        ("invalid_token", 502, "MOCK_INVALID_TOKEN", False),
        ("timeout", 503, "MOCK_TIMEOUT", True),
        ("external_error", 503, "MOCK_EXTERNAL_ERROR", True),
    ],
)
async def test_sync_mock_returns_provider_errors_are_controlled(
    client: AsyncClient,
    scenario: str,
    expected_status: int,
    expected_code: str,
    retryable: bool,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    response = await sync_mock_returns(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
        scenario=scenario,
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["provider"] == "MERCADO_LIVRE"
    assert response.json()["detail"]["retryable"] is retryable
    assert_payload_has_no_secrets(response.json())
    assert await list_return_orders(str(company["id"])) == []


async def test_sync_mock_returns_validates_auth_and_marketplace(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    missing_token_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-orders/mock-sync",
        json={"marketplace": "MERCADO_LIVRE"},
    )
    refresh_token_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-orders/mock-sync",
        headers=auth_headers(str(user["refresh_token"])),
        json={"marketplace": "MERCADO_LIVRE"},
    )
    invalid_marketplace_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-orders/mock-sync",
        headers=auth_headers(str(user["access_token"])),
        json={"marketplace": "INVALID"},
    )

    assert missing_token_response.status_code == 401
    assert refresh_token_response.status_code == 401
    assert invalid_marketplace_response.status_code == 422
    assert_payload_has_no_secrets(invalid_marketplace_response.json())

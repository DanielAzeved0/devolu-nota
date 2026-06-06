import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import engine
from app.main import app

pytestmark = pytest.mark.asyncio


async def database_available() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except (OperationalError, OSError):
        return False
    return True


@pytest_asyncio.fixture(autouse=True)
async def require_database() -> None:
    if not await database_available():
        pytest.skip("PostgreSQL local indisponivel para testes de consultas persistidas")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


async def register_user(client: AsyncClient) -> dict[str, object]:
    email = f"user-{uuid.uuid4()}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Test User", "password": "strong-pass"},
    )
    assert response.status_code == 201
    return response.json()


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


async def sync_return_order(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    marketplace: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/mock-sync",
        headers=auth_headers(access_token),
        json={"marketplace": marketplace},
    )
    assert response.status_code == 200
    return response.json()["items"][0]


async def create_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    return_order_id: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/{return_order_id}/return-notes/mock",
        headers=auth_headers(access_token),
        json={},
    )
    assert response.status_code == 201
    return response.json()


async def test_list_and_get_return_orders_from_persistent_store(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    mercado_livre_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )

    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-orders",
        headers=auth_headers(str(user["access_token"])),
        params={"marketplace": "MERCADO_LIVRE", "limit": 1, "offset": 0},
    )
    get_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-orders/{mercado_livre_order['id']}",
        headers=auth_headers(str(user["access_token"])),
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == mercado_livre_order["id"]
    assert payload["items"][0]["marketplace"] == "MERCADO_LIVRE"
    assert "marketplace_account_id" in payload["items"][0]
    assert get_response.status_code == 200
    assert get_response.json()["id"] == mercado_livre_order["id"]


async def test_list_and_get_return_notes_from_persistent_store(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes",
        headers=auth_headers(str(user["access_token"])),
        params={"status": "DRAFT", "return_order_id": return_order["id"], "limit": 50, "offset": 0},
    )
    get_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}",
        headers=auth_headers(str(user["access_token"])),
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == return_note["id"]
    assert payload["items"][0]["status"] == "DRAFT"
    assert get_response.status_code == 200
    assert get_response.json()["id"] == return_note["id"]


async def test_return_queries_deny_cross_tenant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    return_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    orders_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-orders",
        headers=auth_headers(str(outsider["access_token"])),
    )
    order_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-orders/{return_order['id']}",
        headers=auth_headers(str(outsider["access_token"])),
    )
    notes_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes",
        headers=auth_headers(str(outsider["access_token"])),
    )
    note_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}",
        headers=auth_headers(str(outsider["access_token"])),
    )

    assert orders_response.status_code == 404
    assert order_response.status_code == 404
    assert notes_response.status_code == 404
    assert note_response.status_code == 404


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/return-orders", {"status": "INVALID"}),
        ("/return-orders", {"marketplace": "INVALID"}),
        ("/return-orders", {"limit": 101}),
        ("/return-orders", {"offset": -1}),
        ("/return-notes", {"status": "INVALID"}),
        ("/return-notes", {"limit": 0}),
        ("/return-notes", {"offset": -1}),
    ],
)
async def test_return_queries_validate_filters(
    client: AsyncClient,
    path: str,
    params: dict[str, object],
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    response = await client.get(
        f"/api/v1/companies/{company['id']}{path}",
        headers=auth_headers(str(user["access_token"])),
        params=params,
    )

    assert response.status_code == 422
    assert "input" not in str(response.json())

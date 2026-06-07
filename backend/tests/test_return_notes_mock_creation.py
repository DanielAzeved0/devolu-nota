import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import ReturnNote, ReturnOrder

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
        pytest.skip("PostgreSQL local indisponivel para testes de return notes")


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


async def create_mock_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    return_order_id: str,
    scenario: str = "success",
) -> object:
    return await client.post(
        f"/api/v1/companies/{company_id}/return-orders/{return_order_id}/return-notes/mock",
        headers=auth_headers(access_token),
        json={"scenario": scenario},
    )


async def list_return_notes(company_id: str) -> list[ReturnNote]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ReturnNote).where(ReturnNote.company_id == uuid.UUID(company_id))
        )
        return list(result.scalars().all())


async def get_return_order(return_order_id: str) -> ReturnOrder | None:
    async with AsyncSessionLocal() as session:
        return await session.get(ReturnOrder, uuid.UUID(return_order_id))


async def replace_return_order_external_id(return_order_id: str, external_order_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ReturnOrder)
            .where(ReturnOrder.id == uuid.UUID(return_order_id))
            .values(external_order_id=external_order_id)
        )
        await session.commit()


def assert_payload_has_no_secrets(payload: object) -> None:
    serialized = str(payload)
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "api_token" not in serialized
    assert "client_secret" not in serialized
    assert "encrypted_credentials" not in serialized


async def test_create_mock_return_note_for_mercado_livre_return_order(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["company_id"] == company["id"]
    assert payload["return_order_id"] == return_order["id"]
    assert payload["status"] == "DRAFT"
    assert len(payload["original_nfe_key"]) == 44
    assert payload["return_nfe_key"] is None
    assert payload["issued_at"] is None
    assert_payload_has_no_secrets(payload)

    stored_notes = await list_return_notes(str(company["id"]))
    assert len(stored_notes) == 1
    assert stored_notes[0].status == "DRAFT"
    assert stored_notes[0].original_nfe_key == payload["original_nfe_key"]
    stored_return_order = await get_return_order(str(return_order["id"]))
    assert stored_return_order is not None
    assert stored_return_order.status == "LINKED_TO_NFE"
    assert stored_return_order.original_nfe_key == payload["original_nfe_key"]


async def test_create_mock_return_note_for_shopee_return_order(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )

    response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    assert response.status_code == 201
    assert response.json()["return_order_id"] == return_order["id"]
    assert response.json()["status"] == "DRAFT"
    assert len(response.json()["original_nfe_key"]) == 44
    assert_payload_has_no_secrets(response.json())


async def test_create_mock_return_note_rejects_duplicate_active_note(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    first_response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )
    duplicate_response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Return note already exists"
    assert len(await list_return_notes(str(company["id"]))) == 1


async def test_create_mock_return_note_denies_cross_tenant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    response = await create_mock_return_note(
        client,
        access_token=str(outsider["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    assert response.status_code == 404
    assert await list_return_notes(str(company["id"])) == []


async def test_create_mock_return_note_requires_operator_role(client: AsyncClient) -> None:
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
    first_return_order = await sync_return_order(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    second_return_order = await sync_return_order(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )

    operator_response = await create_mock_return_note(
        client,
        access_token=str(operator["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(first_return_order["id"]),
    )
    viewer_response = await create_mock_return_note(
        client,
        access_token=str(viewer["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(second_return_order["id"]),
    )

    assert operator_response.status_code == 201
    assert viewer_response.status_code == 403
    assert len(await list_return_notes(str(company["id"]))) == 1


async def test_create_mock_return_note_rejects_missing_return_order(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert await list_return_notes(str(company["id"])) == []


async def test_create_mock_return_note_handles_tiny_not_found(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    await replace_return_order_external_id(str(return_order["id"]), "UNKNOWN")

    response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "MOCK_NOT_FOUND"
    assert response.json()["detail"]["provider"] == "TINY"
    assert response.json()["detail"]["retryable"] is False
    assert_payload_has_no_secrets(response.json())
    assert await list_return_notes(str(company["id"])) == []


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_code", "retryable"),
    [
        ("invalid_token", 502, "MOCK_INVALID_TOKEN", False),
        ("timeout", 503, "MOCK_TIMEOUT", True),
        ("external_error", 503, "MOCK_EXTERNAL_ERROR", True),
    ],
)
async def test_create_mock_return_note_provider_errors_are_controlled(
    client: AsyncClient,
    scenario: str,
    expected_status: int,
    expected_code: str,
    retryable: bool,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    response = await create_mock_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_order_id=str(return_order["id"]),
        scenario=scenario,
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["provider"] == "TINY"
    assert response.json()["detail"]["retryable"] is retryable
    assert_payload_has_no_secrets(response.json())
    assert await list_return_notes(str(company["id"])) == []


async def test_create_mock_return_note_validates_auth_and_scenario(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_order = await sync_return_order(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    missing_token_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-orders/{return_order['id']}/return-notes/mock",
        json={},
    )
    refresh_token_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-orders/{return_order['id']}/return-notes/mock",
        headers=auth_headers(str(user["refresh_token"])),
        json={},
    )
    invalid_scenario_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-orders/{return_order['id']}/return-notes/mock",
        headers=auth_headers(str(user["access_token"])),
        json={"scenario": "invalid"},
    )

    assert missing_token_response.status_code == 401
    assert refresh_token_response.status_code == 401
    assert invalid_scenario_response.status_code == 422
    assert_payload_has_no_secrets(invalid_scenario_response.json())

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import AuditLog, Integration
from app.services.integration_credentials import decrypt_integration_credentials

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
        pytest.skip("PostgreSQL local indisponivel para testes de integracoes")


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
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
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


async def create_integration(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    provider: str = "TINY",
    credentials: dict[str, str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": provider,
        "settings": {"sync_interval_minutes": 30},
    }
    if credentials is not None:
        payload["credentials"] = credentials

    response = await client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=auth_headers(access_token),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


async def get_integration_from_db(integration_id: str) -> Integration | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Integration).where(Integration.id == uuid.UUID(integration_id))
        )
        return result.scalar_one_or_none()


async def count_integrations_for_company(company_id: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Integration).where(Integration.company_id == uuid.UUID(company_id))
        )
        return len(result.scalars().all())


async def list_audit_logs(company_id: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.company_id == uuid.UUID(company_id))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        return list(result.scalars().all())


def assert_public_response_has_no_secrets(payload: object, *secrets: str) -> None:
    serialized = str(payload)
    assert "encrypted_credentials" not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "api_token" not in serialized
    assert "client_secret" not in serialized
    for secret in secrets:
        assert secret not in serialized


async def test_create_integration_with_credentials_encrypts_values(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    access_token = "tiny-access-token"
    refresh_token = "tiny-refresh-token"

    integration = await create_integration(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        credentials={"access_token": access_token, "refresh_token": refresh_token},
    )

    assert integration["status"] == "ACTIVE"
    assert_public_response_has_no_secrets(integration, access_token, refresh_token)

    stored_integration = await get_integration_from_db(str(integration["id"]))
    assert stored_integration is not None
    assert str(stored_integration.company_id) == company["id"]
    assert stored_integration.provider == "TINY"
    assert stored_integration.status == "ACTIVE"
    assert stored_integration.settings == {"sync_interval_minutes": 30}
    assert stored_integration.encrypted_credentials is not None
    assert stored_integration.encrypted_credentials["access_token"] != access_token
    assert stored_integration.encrypted_credentials["refresh_token"] != refresh_token
    assert access_token not in str(stored_integration.encrypted_credentials)
    assert refresh_token not in str(stored_integration.encrypted_credentials)
    decrypted_credentials = decrypt_integration_credentials(stored_integration.encrypted_credentials)
    assert decrypted_credentials["access_token"] == access_token
    assert decrypted_credentials["refresh_token"] == refresh_token

    logs = await list_audit_logs(str(company["id"]))
    create_logs = [log for log in logs if log.action == "INTEGRATION_CREATED"]
    assert len(create_logs) == 1
    assert create_logs[0].metadata_ == {
        "provider": "TINY",
        "status": "ACTIVE",
        "has_credentials": True,
    }
    assert_public_response_has_no_secrets([log.metadata_ for log in logs], access_token, refresh_token)


async def test_create_list_and_get_integration_without_credentials(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    integration = await create_integration(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        provider="SHOPEE",
    )
    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/integrations",
        headers=auth_headers(str(user["access_token"])),
    )
    get_response = await client.get(
        f"/api/v1/companies/{company['id']}/integrations/{integration['id']}",
        headers=auth_headers(str(user["access_token"])),
    )

    assert integration["status"] == "DISCONNECTED"
    assert list_response.status_code == 200
    assert integration["id"] in [item["id"] for item in list_response.json()]
    assert get_response.status_code == 200
    assert get_response.json()["provider"] == "SHOPEE"
    assert_public_response_has_no_secrets(get_response.json())


async def test_update_integration_status_settings_and_credentials(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    integration = await create_integration(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    api_token = "tiny-api-token"

    update_response = await client.patch(
        f"/api/v1/companies/{company['id']}/integrations/{integration['id']}",
        headers=auth_headers(str(user["access_token"])),
        json={"status": "ERROR", "settings": {"sync_interval_minutes": 60}},
    )
    credentials_response = await client.put(
        f"/api/v1/companies/{company['id']}/integrations/{integration['id']}/credentials",
        headers=auth_headers(str(user["access_token"])),
        json={"api_token": api_token},
    )

    assert update_response.status_code == 200
    assert update_response.json()["status"] == "ERROR"
    assert update_response.json()["settings"] == {"sync_interval_minutes": 60}
    assert credentials_response.status_code == 200
    assert credentials_response.json()["status"] == "ACTIVE"
    assert_public_response_has_no_secrets(credentials_response.json(), api_token)

    stored_integration = await get_integration_from_db(str(integration["id"]))
    assert stored_integration is not None
    assert stored_integration.status == "ACTIVE"
    assert stored_integration.settings == {"sync_interval_minutes": 60}
    assert stored_integration.encrypted_credentials is not None
    assert set(stored_integration.encrypted_credentials.keys()) == {"api_token"}
    assert api_token not in str(stored_integration.encrypted_credentials)
    decrypted_credentials = decrypt_integration_credentials(stored_integration.encrypted_credentials)
    assert decrypted_credentials["api_token"] == api_token

    logs = await list_audit_logs(str(company["id"]))
    update_logs = [log for log in logs if log.action == "INTEGRATION_UPDATED"]
    credentials_logs = [log for log in logs if log.action == "INTEGRATION_CREDENTIALS_REPLACED"]
    assert len(update_logs) == 1
    assert update_logs[0].metadata_ == {
        "provider": "TINY",
        "previous_status": "DISCONNECTED",
        "new_status": "ERROR",
        "settings_updated": True,
    }
    assert len(credentials_logs) == 1
    assert credentials_logs[0].metadata_ == {
        "provider": "TINY",
        "previous_status": "ERROR",
        "new_status": "ACTIVE",
        "credentials_replaced": True,
    }
    assert_public_response_has_no_secrets([log.metadata_ for log in logs], api_token)


async def test_integration_routes_deny_cross_tenant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    owner_company = await create_company(client, str(owner["access_token"]))
    outsider_company = await create_company(client, str(outsider["access_token"]))
    integration = await create_integration(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
    )

    outsider_list_response = await client.get(
        f"/api/v1/companies/{owner_company['id']}/integrations",
        headers=auth_headers(str(outsider["access_token"])),
    )
    wrong_company_response = await client.get(
        f"/api/v1/companies/{outsider_company['id']}/integrations/{integration['id']}",
        headers=auth_headers(str(outsider["access_token"])),
    )
    outsider_update_response = await client.patch(
        f"/api/v1/companies/{owner_company['id']}/integrations/{integration['id']}",
        headers=auth_headers(str(outsider["access_token"])),
        json={"status": "ERROR"},
    )

    assert outsider_list_response.status_code == 404
    assert wrong_company_response.status_code == 404
    assert outsider_update_response.status_code == 404
    assert await count_integrations_for_company(str(owner_company["id"])) == 1
    assert await count_integrations_for_company(str(outsider_company["id"])) == 0


async def test_integration_routes_reject_sensitive_settings(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    integration = await create_integration(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    create_response = await client.post(
        f"/api/v1/companies/{company['id']}/integrations",
        headers=auth_headers(str(user["access_token"])),
        json={"provider": "TINY", "settings": {"access_token": "plain-token"}},
    )
    update_response = await client.patch(
        f"/api/v1/companies/{company['id']}/integrations/{integration['id']}",
        headers=auth_headers(str(user["access_token"])),
        json={"settings": {"client_secret": "plain-secret"}},
    )

    assert create_response.status_code == 422
    assert update_response.status_code == 422
    assert "plain-token" not in str(create_response.json())
    assert "plain-secret" not in str(update_response.json())
    stored_integration = await get_integration_from_db(str(integration["id"]))
    assert stored_integration is not None
    assert stored_integration.settings == {"sync_interval_minutes": 30}


async def test_integration_routes_validate_auth_provider_status_and_credentials(
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    integration = await create_integration(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    missing_token_response = await client.get(f"/api/v1/companies/{company['id']}/integrations")
    refresh_token_response = await client.get(
        f"/api/v1/companies/{company['id']}/integrations",
        headers=auth_headers(str(user["refresh_token"])),
    )
    invalid_provider_response = await client.post(
        f"/api/v1/companies/{company['id']}/integrations",
        headers=auth_headers(str(user["access_token"])),
        json={"provider": "INVALID"},
    )
    invalid_status_response = await client.patch(
        f"/api/v1/companies/{company['id']}/integrations/{integration['id']}",
        headers=auth_headers(str(user["access_token"])),
        json={"status": "INVALID"},
    )
    empty_credentials_response = await client.put(
        f"/api/v1/companies/{company['id']}/integrations/{integration['id']}/credentials",
        headers=auth_headers(str(user["access_token"])),
        json={},
    )

    assert missing_token_response.status_code == 401
    assert refresh_token_response.status_code == 401
    assert invalid_provider_response.status_code == 422
    assert invalid_status_response.status_code == 422
    assert empty_credentials_response.status_code == 422

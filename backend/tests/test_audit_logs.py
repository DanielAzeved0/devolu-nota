import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import AuditLog
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.emissions import EmissionRepository
from app.services.audit_logs import AuditLogService, SensitiveAuditMetadataError
from app.services.emissions import EmissionBatchMockProcessor

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
        pytest.skip("PostgreSQL local indisponivel para testes de audit logs")


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
    return register_response.json()


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


async def create_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    marketplace: str,
) -> dict[str, object]:
    sync_response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/mock-sync",
        headers=auth_headers(access_token),
        json={"marketplace": marketplace},
    )
    assert sync_response.status_code == 200
    return_order = sync_response.json()["items"][0]
    note_response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/{return_order['id']}/return-notes/mock",
        headers=auth_headers(access_token),
        json={},
    )
    assert note_response.status_code == 201
    return note_response.json()


async def create_emission_batch(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    return_note_ids: list[str],
    scenario: str = "success",
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/companies/{company_id}/emission-batches/mock",
        headers=auth_headers(access_token),
        json={"return_note_ids": return_note_ids, "scenario": scenario},
    )
    assert response.status_code == 201
    return response.json()


async def process_batch(*, company_id: str, batch_id: str, scenario: str = "success") -> None:
    async with AsyncSessionLocal() as session:
        processor = EmissionBatchMockProcessor(
            emissions=EmissionRepository(session),
            audit_logs=AuditLogRepository(session),
        )
        await processor.process_batch(
            company_id=uuid.UUID(company_id),
            batch_id=uuid.UUID(batch_id),
            scenario=scenario,  # type: ignore[arg-type]
        )
        await session.commit()


async def list_company_logs(company_id: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.company_id == uuid.UUID(company_id))
        )
        return list(result.scalars().all())


def assert_payload_has_no_secrets(payload: object) -> None:
    serialized = str(payload)
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "api_token" not in serialized
    assert "client_secret" not in serialized
    assert "encrypted_credentials" not in serialized


async def test_create_emission_batch_writes_creation_audit_logs(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    batch = await create_emission_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )

    logs = await list_company_logs(str(company["id"]))
    actions = {log.action for log in logs}
    assert "EMISSION_BATCH_CREATED" in actions
    assert "EMISSION_JOB_CREATED" in actions
    assert "RETURN_NOTE_QUEUED" in actions
    batch_log = next(log for log in logs if log.action == "EMISSION_BATCH_CREATED")
    assert batch_log.entity_type == "emission_batch"
    assert str(batch_log.entity_id) == batch["id"]
    assert batch_log.user_id is not None
    assert batch_log.metadata_ is not None
    assert batch_log.metadata_["jobs_count"] == 1
    assert_payload_has_no_secrets([log.metadata_ for log in logs])


async def test_process_emission_batch_success_writes_operational_audit_logs(
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    batch = await create_emission_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )

    await process_batch(company_id=str(company["id"]), batch_id=str(batch["id"]))

    logs = await list_company_logs(str(company["id"]))
    actions = {log.action for log in logs}
    assert "EMISSION_BATCH_STARTED" in actions
    assert "EMISSION_JOB_STARTED" in actions
    assert "EMISSION_JOB_SUCCEEDED" in actions
    assert "RETURN_NOTE_ISSUED" in actions
    assert "EMISSION_BATCH_COMPLETED" in actions
    processor_logs = [
        log
        for log in logs
        if log.action
        in {
            "EMISSION_BATCH_STARTED",
            "EMISSION_JOB_STARTED",
            "EMISSION_JOB_SUCCEEDED",
            "RETURN_NOTE_ISSUED",
            "EMISSION_BATCH_COMPLETED",
        }
    ]
    assert all(log.user_id is None for log in processor_logs)
    assert_payload_has_no_secrets([log.metadata_ for log in logs])


async def test_process_emission_batch_failure_writes_failed_audit_logs(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    batch = await create_emission_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
        scenario="failure",
    )

    await process_batch(company_id=str(company["id"]), batch_id=str(batch["id"]), scenario="failure")

    logs = await list_company_logs(str(company["id"]))
    actions = {log.action for log in logs}
    assert "EMISSION_JOB_FAILED" in actions
    assert "RETURN_NOTE_FAILED" in actions
    assert "EMISSION_BATCH_FAILED" in actions
    failed_job_log = next(log for log in logs if log.action == "EMISSION_JOB_FAILED")
    assert failed_job_log.metadata_ is not None
    assert failed_job_log.metadata_["error_message"] == "Mock emission failed"
    assert_payload_has_no_secrets(failed_job_log.metadata_)


async def test_list_audit_logs_filters_paginates_and_orders_results(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    first_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    second_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )
    batch = await create_emission_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(first_note["id"]), str(second_note["id"])],
        scenario="partial_failure",
    )
    await process_batch(
        company_id=str(company["id"]),
        batch_id=str(batch["id"]),
        scenario="partial_failure",
    )

    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"limit": 5, "offset": 0},
    )
    batch_filter_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"entity_type": "emission_batch"},
    )
    action_filter_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"action": "EMISSION_BATCH_FAILED"},
    )
    entity_filter_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"entity_id": str(batch["id"])},
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["limit"] == 5
    assert payload["offset"] == 0
    assert len(payload["items"]) == 5
    assert payload["items"] == sorted(
        payload["items"],
        key=lambda item: item["created_at"],
        reverse=True,
    )
    assert all(item["entity_type"] == "emission_batch" for item in batch_filter_response.json()["items"])
    assert all(item["action"] == "EMISSION_BATCH_FAILED" for item in action_filter_response.json()["items"])
    assert all(item["entity_id"] == batch["id"] for item in entity_filter_response.json()["items"])
    assert_payload_has_no_secrets(payload)


async def test_list_audit_logs_respects_auth_and_tenant_boundary(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    await create_emission_batch(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )

    missing_token_response = await client.get(f"/api/v1/companies/{company['id']}/audit-logs")
    refresh_token_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(owner["refresh_token"])),
    )
    outsider_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(outsider["access_token"])),
    )

    assert missing_token_response.status_code == 401
    assert refresh_token_response.status_code == 401
    assert outsider_response.status_code == 404


async def test_list_audit_logs_validates_query_params(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    invalid_limit_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"limit": 101},
    )
    invalid_offset_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"offset": -1},
    )
    invalid_entity_id_response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
        params={"entity_id": "invalid"},
    )

    assert invalid_limit_response.status_code == 422
    assert invalid_offset_response.status_code == 422
    assert invalid_entity_id_response.status_code == 422
    assert_payload_has_no_secrets(invalid_limit_response.json())


async def test_empty_audit_log_list_returns_empty_items(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    response = await client.get(
        f"/api/v1/companies/{company['id']}/audit-logs",
        headers=auth_headers(str(user["access_token"])),
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 50, "offset": 0}


async def test_audit_log_service_rejects_sensitive_metadata() -> None:
    async with AsyncSessionLocal() as session:
        service = AuditLogService(audit_logs=AuditLogRepository(session))
        with pytest.raises(SensitiveAuditMetadataError):
            await service.create_log(
                company_id=uuid.uuid4(),
                user_id=None,
                action="TEST",
                entity_type="test",
                entity_id=uuid.uuid4(),
                metadata={"nested": {"access_token": "secret"}},
            )

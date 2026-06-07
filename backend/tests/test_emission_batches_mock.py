import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import EmissionBatch, EmissionJob, ReturnNote
from app.repositories.emissions import EmissionRepository
from app.services.emissions import EmissionBatchInvalidStateError, EmissionBatchMockProcessor

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
        pytest.skip("PostgreSQL local indisponivel para testes de emission batches")


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


async def create_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    marketplace: str,
) -> dict[str, object]:
    return_order = await sync_return_order(
        client,
        access_token=access_token,
        company_id=company_id,
        marketplace=marketplace,
    )
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/{return_order['id']}/return-notes/mock",
        headers=auth_headers(access_token),
        json={},
    )
    assert response.status_code == 201
    return response.json()


async def create_mock_batch(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    return_note_ids: list[str],
    scenario: str = "success",
) -> object:
    return await client.post(
        f"/api/v1/companies/{company_id}/emission-batches/mock",
        headers=auth_headers(access_token),
        json={"return_note_ids": return_note_ids, "scenario": scenario},
    )


async def get_return_note(return_note_id: str) -> ReturnNote | None:
    async with AsyncSessionLocal() as session:
        return await session.get(ReturnNote, uuid.UUID(return_note_id))


async def get_batch(batch_id: str) -> EmissionBatch | None:
    async with AsyncSessionLocal() as session:
        return await session.get(EmissionBatch, uuid.UUID(batch_id))


async def list_jobs(batch_id: str) -> list[EmissionJob]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EmissionJob).where(EmissionJob.batch_id == uuid.UUID(batch_id))
        )
        return list(result.scalars().all())


async def process_batch(*, company_id: str, batch_id: str, scenario: str = "success") -> None:
    async with AsyncSessionLocal() as session:
        processor = EmissionBatchMockProcessor(emissions=EmissionRepository(session))
        await processor.process_batch(
            company_id=uuid.UUID(company_id),
            batch_id=uuid.UUID(batch_id),
            scenario=scenario,  # type: ignore[arg-type]
        )
        await session.commit()


def assert_payload_has_no_secrets(payload: object) -> None:
    serialized = str(payload)
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "api_token" not in serialized
    assert "client_secret" not in serialized
    assert "encrypted_credentials" not in serialized


async def test_create_mock_emission_batch_creates_jobs_and_queues_notes(
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

    response = await create_mock_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["company_id"] == company["id"]
    assert payload["requested_by_user_id"] is not None
    assert payload["status"] == "PENDING"
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["return_note_id"] == note["id"]
    assert payload["jobs"][0]["status"] == "PENDING"
    assert_payload_has_no_secrets(payload)

    stored_note = await get_return_note(str(note["id"]))
    assert stored_note is not None
    assert stored_note.status == "QUEUED"


async def test_create_mock_emission_batch_requires_operator_role(client: AsyncClient) -> None:
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
    first_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    second_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="SHOPEE",
    )

    operator_response = await create_mock_batch(
        client,
        access_token=str(operator["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(first_note["id"])],
    )
    viewer_response = await create_mock_batch(
        client,
        access_token=str(viewer["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(second_note["id"])],
    )

    assert operator_response.status_code == 201
    assert viewer_response.status_code == 403


async def test_get_batch_and_list_jobs_respect_tenant_boundary(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    batch_response = await create_mock_batch(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )
    batch_id = batch_response.json()["id"]

    owner_get_response = await client.get(
        f"/api/v1/companies/{company['id']}/emission-batches/{batch_id}",
        headers=auth_headers(str(owner["access_token"])),
    )
    owner_jobs_response = await client.get(
        f"/api/v1/companies/{company['id']}/emission-batches/{batch_id}/jobs",
        headers=auth_headers(str(owner["access_token"])),
    )
    outsider_get_response = await client.get(
        f"/api/v1/companies/{company['id']}/emission-batches/{batch_id}",
        headers=auth_headers(str(outsider["access_token"])),
    )
    outsider_jobs_response = await client.get(
        f"/api/v1/companies/{company['id']}/emission-batches/{batch_id}/jobs",
        headers=auth_headers(str(outsider["access_token"])),
    )

    assert owner_get_response.status_code == 200
    assert owner_jobs_response.status_code == 200
    assert len(owner_jobs_response.json()["items"]) == 1
    assert outsider_get_response.status_code == 404
    assert outsider_jobs_response.status_code == 404


async def test_create_mock_emission_batch_rejects_invalid_inputs(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    missing_token_response = await client.post(
        f"/api/v1/companies/{company['id']}/emission-batches/mock",
        json={"return_note_ids": [note["id"]]},
    )
    refresh_token_response = await create_mock_batch(
        client,
        access_token=str(user["refresh_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )
    duplicate_ids_response = await create_mock_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"]), str(note["id"])],
    )
    invalid_scenario_response = await client.post(
        f"/api/v1/companies/{company['id']}/emission-batches/mock",
        headers=auth_headers(str(user["access_token"])),
        json={"return_note_ids": [note["id"]], "scenario": "invalid"},
    )

    assert missing_token_response.status_code == 401
    assert refresh_token_response.status_code == 401
    assert duplicate_ids_response.status_code == 422
    assert invalid_scenario_response.status_code == 422
    assert_payload_has_no_secrets(invalid_scenario_response.json())


async def test_create_mock_emission_batch_rejects_cross_tenant_and_non_eligible_notes(
    client: AsyncClient,
) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    owner_company = await create_company(client, str(owner["access_token"]))
    outsider_company = await create_company(client, str(outsider["access_token"]))
    owner_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    outsider_note = await create_return_note(
        client,
        access_token=str(outsider["access_token"]),
        company_id=str(outsider_company["id"]),
        marketplace="MERCADO_LIVRE",
    )

    cross_tenant_response = await create_mock_batch(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
        return_note_ids=[str(outsider_note["id"])],
    )
    first_batch_response = await create_mock_batch(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
        return_note_ids=[str(owner_note["id"])],
    )
    queued_note_response = await create_mock_batch(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
        return_note_ids=[str(owner_note["id"])],
    )

    assert cross_tenant_response.status_code == 409
    assert first_batch_response.status_code == 201
    assert queued_note_response.status_code == 409


async def test_process_mock_emission_batch_success_issues_notes(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    batch_response = await create_mock_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )

    await process_batch(company_id=str(company["id"]), batch_id=str(batch_response.json()["id"]))

    stored_batch = await get_batch(str(batch_response.json()["id"]))
    stored_note = await get_return_note(str(note["id"]))
    jobs = await list_jobs(str(batch_response.json()["id"]))
    assert stored_batch is not None
    assert stored_batch.status == "COMPLETED"
    assert stored_note is not None
    assert stored_note.status == "ISSUED"
    assert stored_note.return_nfe_key is not None
    assert len(stored_note.return_nfe_key) == 44
    assert stored_note.issued_at is not None
    assert jobs[0].status == "SUCCESS"


async def test_process_mock_emission_batch_failure_marks_jobs_and_notes_failed(
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
    batch_response = await create_mock_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
        scenario="failure",
    )

    await process_batch(
        company_id=str(company["id"]),
        batch_id=str(batch_response.json()["id"]),
        scenario="failure",
    )

    stored_batch = await get_batch(str(batch_response.json()["id"]))
    stored_note = await get_return_note(str(note["id"]))
    jobs = await list_jobs(str(batch_response.json()["id"]))
    assert stored_batch is not None
    assert stored_batch.status == "FAILED"
    assert stored_note is not None
    assert stored_note.status == "FAILED"
    assert stored_note.error_message == "Mock emission failed"
    assert jobs[0].status == "FAILED"
    assert jobs[0].last_error == "Mock emission failed"
    assert_payload_has_no_secrets(jobs[0].last_error)


async def test_process_mock_emission_batch_partial_failure_mixes_results(
    client: AsyncClient,
) -> None:
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
    batch_response = await create_mock_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(first_note["id"]), str(second_note["id"])],
        scenario="partial_failure",
    )

    await process_batch(
        company_id=str(company["id"]),
        batch_id=str(batch_response.json()["id"]),
        scenario="partial_failure",
    )

    stored_batch = await get_batch(str(batch_response.json()["id"]))
    first_stored_note = await get_return_note(str(first_note["id"]))
    second_stored_note = await get_return_note(str(second_note["id"]))
    jobs = await list_jobs(str(batch_response.json()["id"]))
    assert stored_batch is not None
    assert stored_batch.status == "FAILED"
    assert first_stored_note is not None
    assert second_stored_note is not None
    assert {first_stored_note.status, second_stored_note.status} == {"ISSUED", "FAILED"}
    assert {job.status for job in jobs} == {"SUCCESS", "FAILED"}


async def test_process_mock_emission_batch_rejects_finalized_reprocessing(
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
    batch_response = await create_mock_batch(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_ids=[str(note["id"])],
    )
    await process_batch(company_id=str(company["id"]), batch_id=str(batch_response.json()["id"]))

    async with AsyncSessionLocal() as session:
        processor = EmissionBatchMockProcessor(emissions=EmissionRepository(session))
        with pytest.raises(EmissionBatchInvalidStateError):
            await processor.process_batch(
                company_id=uuid.UUID(str(company["id"])),
                batch_id=uuid.UUID(str(batch_response.json()["id"])),
            )

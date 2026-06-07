import uuid
from datetime import datetime
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.jobs import scheduler
from app.models import RetentionJob
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.services.fiscal_documents import FiscalDocumentStorageService
from app.storage.local import LocalStorageProvider
from app.main import app

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
        pytest.skip("PostgreSQL local indisponivel para testes de scheduler")


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


async def create_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
) -> dict[str, object]:
    sync_response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/mock-sync",
        headers=auth_headers(access_token),
        json={"marketplace": "MERCADO_LIVRE"},
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


async def store_archive(
    *,
    company_id: str,
    return_note_id: str,
    issued_at: datetime,
    tmp_path,
) -> None:
    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )
        await service.store_document(
            company_id=uuid.UUID(company_id),
            return_note_id=uuid.UUID(return_note_id),
            document_type="NFE_XML",
            content_bytes=f"<nfe>{uuid.uuid4()}</nfe>".encode(),
            content_type="application/xml",
            issued_at=issued_at,
        )
        await session.commit()


async def get_latest_retention_job(company_id: str) -> RetentionJob | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RetentionJob)
            .where(RetentionJob.company_id == uuid.UUID(company_id))
            .order_by(RetentionJob.created_at.desc(), RetentionJob.id.desc())
        )
        return result.scalars().first()


async def test_build_scheduler_registers_retention_job() -> None:
    scheduler_instance = scheduler.build_scheduler()
    job = scheduler_instance.get_job(scheduler.RETENTION_JOB_ID)

    assert job is not None
    assert job.func == scheduler.run_retention_cycle_job
    assert job.trigger.interval.total_seconds() == scheduler.RETENTION_INTERVAL_MINUTES * 60
    assert str(scheduler_instance.timezone) == scheduler.RETENTION_TIMEZONE


async def test_run_retention_cycle_processes_each_company_and_continues_on_error() -> None:
    company_ids = [uuid.uuid4(), uuid.uuid4()]
    calls: list[UUID] = []

    async def fake_processor(company_id: uuid.UUID, now: datetime) -> bool:
        calls.append(company_id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return True

    processed = await scheduler.run_retention_cycle(
        company_ids=company_ids,
        now=datetime(2026, 1, 1),
        processor=fake_processor,
    )

    assert processed == 2
    assert calls == company_ids


async def test_process_company_retention_marks_job_completed_and_updates_archive(
    client: AsyncClient,
    tmp_path,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    await store_archive(
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
        issued_at=datetime(2020, 1, 1),
        tmp_path=tmp_path,
    )

    result = await scheduler._process_company_retention(
        uuid.UUID(str(company["id"])),
        datetime(2026, 1, 1),
    )

    job = await get_latest_retention_job(str(company["id"]))
    assert result is True
    assert job is not None
    assert job.status == "COMPLETED"
    assert job.processed_at is not None


async def test_process_company_retention_marks_job_failed_on_error(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))

    class BrokenRetentionService:
        def __init__(self, *, retention, audit_logs) -> None:  # noqa: ANN001
            self.retention = retention
            self.audit_logs = audit_logs

        async def apply_company_retention(self, *, company_id, now) -> None:  # noqa: ANN001
            raise RuntimeError("retention failed")

    monkeypatch.setattr(scheduler, "RetentionService", BrokenRetentionService)

    result = await scheduler._process_company_retention(
        uuid.UUID(str(company["id"])),
        datetime(2026, 1, 1),
    )

    job = await get_latest_retention_job(str(company["id"]))
    assert result is False
    assert job is not None
    assert job.status == "FAILED"
    assert job.error_message == "retention failed"

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.models import AuditLog, StorageArchive
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.retention import RetentionRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.services.audit_logs import AuditLogService
from app.services.fiscal_documents import FiscalDocumentStorageService
from app.services.retention import RetentionPolicy, RetentionPolicyError, RetentionService
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
        pytest.skip("PostgreSQL local indisponivel para testes de retencao")


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


async def store_archive(
    *,
    company_id: str,
    return_note_id: str,
    issued_at: datetime,
    tmp_path,
) -> str:
    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )
        stored = await service.store_document(
            company_id=uuid.UUID(company_id),
            return_note_id=uuid.UUID(return_note_id),
            document_type="NFE_XML",
            content_bytes=f"<nfe>{uuid.uuid4()}</nfe>".encode(),
            content_type="application/xml",
            issued_at=issued_at,
        )
        await session.commit()
        return str(stored.storage_archive.id)


async def get_archive(archive_id: str) -> StorageArchive | None:
    async with AsyncSessionLocal() as session:
        return await session.get(StorageArchive, uuid.UUID(archive_id))


async def list_company_logs(company_id: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.company_id == uuid.UUID(company_id))
        )
        return list(result.scalars().all())


async def apply_retention(company_id: str, now: datetime) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        service = RetentionService(
            retention=RetentionRepository(session),
            audit_logs=AuditLogService(audit_logs=AuditLogRepository(session)),
        )
        result = await service.apply_company_retention(company_id=uuid.UUID(company_id), now=now)
        await session.commit()
        return result.moved_to_cold, result.moved_to_deleted


async def test_retention_moves_six_year_document_to_cold(client: AsyncClient, tmp_path) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    archive_id = await store_archive(
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
        issued_at=datetime(2020, 1, 1),
        tmp_path=tmp_path,
    )

    moved_to_cold, moved_to_deleted = await apply_retention(
        str(company["id"]),
        now=datetime(2026, 1, 1),
    )

    archive = await get_archive(archive_id)
    assert archive is not None
    assert archive.status == "COLD"
    assert moved_to_cold == 1
    assert moved_to_deleted == 0
    logs = await list_company_logs(str(company["id"]))
    assert len(logs) == 1
    assert logs[0].action == "STORAGE_ARCHIVE_MOVED_TO_COLD"
    assert logs[0].entity_type == "storage_archive"
    assert logs[0].metadata_ is not None
    assert logs[0].metadata_["previous_status"] == "ACTIVE"
    assert logs[0].metadata_["new_status"] == "COLD"
    assert logs[0].metadata_["policy"]["cold_after_years"] == 5


async def test_retention_moves_twelve_year_document_to_deleted(client: AsyncClient, tmp_path) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    archive_id = await store_archive(
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
        issued_at=datetime(2014, 1, 1),
        tmp_path=tmp_path,
    )

    moved_to_cold, moved_to_deleted = await apply_retention(
        str(company["id"]),
        now=datetime(2026, 1, 1),
    )

    archive = await get_archive(archive_id)
    assert archive is not None
    assert archive.status == "DELETED"
    assert moved_to_cold == 0
    assert moved_to_deleted == 1
    logs = await list_company_logs(str(company["id"]))
    assert len(logs) == 1
    assert logs[0].action == "STORAGE_ARCHIVE_DELETED_BY_RETENTION"
    assert logs[0].metadata_ is not None
    assert logs[0].metadata_["new_status"] == "DELETED"


async def test_retention_keeps_recent_document_active(client: AsyncClient, tmp_path) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        marketplace="MERCADO_LIVRE",
    )
    archive_id = await store_archive(
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
        issued_at=datetime(2024, 1, 1),
        tmp_path=tmp_path,
    )

    moved_to_cold, moved_to_deleted = await apply_retention(
        str(company["id"]),
        now=datetime(2026, 1, 1),
    )

    archive = await get_archive(archive_id)
    assert archive is not None
    assert archive.status == "ACTIVE"
    assert moved_to_cold == 0
    assert moved_to_deleted == 0


async def test_retention_is_company_scoped_and_idempotent(client: AsyncClient, tmp_path) -> None:
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
    owner_archive_id = await store_archive(
        company_id=str(owner_company["id"]),
        return_note_id=str(owner_note["id"]),
        issued_at=datetime(2020, 1, 1),
        tmp_path=tmp_path,
    )
    outsider_archive_id = await store_archive(
        company_id=str(outsider_company["id"]),
        return_note_id=str(outsider_note["id"]),
        issued_at=datetime(2020, 1, 1),
        tmp_path=tmp_path,
    )

    first_result = await apply_retention(str(owner_company["id"]), now=datetime(2026, 1, 1))
    second_result = await apply_retention(str(owner_company["id"]), now=datetime(2026, 1, 1))

    owner_archive = await get_archive(owner_archive_id)
    outsider_archive = await get_archive(outsider_archive_id)
    assert owner_archive is not None
    assert outsider_archive is not None
    assert owner_archive.status == "COLD"
    assert outsider_archive.status == "ACTIVE"
    assert first_result == (1, 0)
    assert second_result == (0, 0)
    logs = await list_company_logs(str(owner_company["id"]))
    assert len(logs) == 1
    assert logs[0].action == "STORAGE_ARCHIVE_MOVED_TO_COLD"


async def test_retention_policy_rejects_invalid_years() -> None:
    with pytest.raises(RetentionPolicyError):
        RetentionPolicy(cold_after_years=0, delete_after_years=10)
    with pytest.raises(RetentionPolicyError):
        RetentionPolicy(cold_after_years=5, delete_after_years=5)

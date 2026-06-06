from datetime import UTC, datetime, timedelta
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import AuditLog, FiscalDocument, StorageArchive

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
        pytest.skip("PostgreSQL local indisponivel para testes de retencao")


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


async def create_fiscal_document(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    return_note_id: str,
    document_type: str = "NFE_XML",
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-notes/{return_note_id}/fiscal-documents/mock",
        headers=auth_headers(access_token),
        json={
            "document_type": document_type,
            "content_type": "application/xml",
            "content": f"<doc>{uuid.uuid4()}</doc>",
        },
    )
    assert response.status_code == 201
    return response.json()


async def set_archive_age(storage_archive_id: str, *, days_old: int) -> None:
    created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_old)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(StorageArchive)
            .where(StorageArchive.id == uuid.UUID(storage_archive_id))
            .values(created_at=created_at, updated_at=created_at)
        )
        await session.commit()


async def get_archive(storage_archive_id: str) -> StorageArchive | None:
    async with AsyncSessionLocal() as session:
        return await session.get(StorageArchive, uuid.UUID(storage_archive_id))


async def get_document(fiscal_document_id: str) -> FiscalDocument | None:
    async with AsyncSessionLocal() as session:
        return await session.get(FiscalDocument, uuid.UUID(fiscal_document_id))


async def list_audit_logs(company_id: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.company_id == uuid.UUID(company_id),
                AuditLog.action.in_(("RETENTION_ARCHIVE_COLD", "RETENTION_DELETE_MARKED")),
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        return list(result.scalars().all())


async def test_mock_retention_ignores_recent_archives(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    document = await create_fiscal_document(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
    )

    response = await client.post(
        f"/api/v1/companies/{company['id']}/retention-jobs/mock-run",
        headers=auth_headers(str(user["access_token"])),
    )

    assert response.status_code == 200
    assert response.json()["archived_count"] == 0
    assert response.json()["deleted_count"] == 0
    assert response.json()["skipped_count"] == 0
    archive = await get_archive(str(document["storage_archive_id"]))
    assert archive is not None
    assert archive.status == "ACTIVE"


async def test_mock_retention_moves_old_active_archive_to_cold(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    document = await create_fiscal_document(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
    )
    await set_archive_age(str(document["storage_archive_id"]), days_old=365 * 6)

    response = await client.post(
        f"/api/v1/companies/{company['id']}/retention-jobs/mock-run",
        headers=auth_headers(str(user["access_token"])),
    )

    assert response.status_code == 200
    assert response.json()["archived_count"] == 1
    assert response.json()["deleted_count"] == 0
    assert len(response.json()["jobs"]) == 1
    archive = await get_archive(str(document["storage_archive_id"]))
    assert archive is not None
    assert archive.status == "COLD"
    logs = await list_audit_logs(str(company["id"]))
    assert [log.action for log in logs] == ["RETENTION_ARCHIVE_COLD"]


async def test_mock_retention_marks_very_old_archive_deleted(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    document = await create_fiscal_document(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
        return_note_id=str(note["id"]),
        document_type="TINY_JSON",
    )
    await set_archive_age(str(document["storage_archive_id"]), days_old=365 * 12)

    response = await client.post(
        f"/api/v1/companies/{company['id']}/retention-jobs/mock-run",
        headers=auth_headers(str(user["access_token"])),
    )

    assert response.status_code == 200
    assert response.json()["archived_count"] == 0
    assert response.json()["deleted_count"] == 1
    archive = await get_archive(str(document["storage_archive_id"]))
    stored_document = await get_document(str(document["id"]))
    assert archive is not None
    assert archive.status == "DELETED"
    assert stored_document is not None
    assert stored_document.status == "DELETED"
    logs = await list_audit_logs(str(company["id"]))
    assert [log.action for log in logs] == ["RETENTION_DELETE_MARKED"]


async def test_mock_retention_denies_cross_tenant_access(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    response = await client.post(
        f"/api/v1/companies/{company['id']}/retention-jobs/mock-run",
        headers=auth_headers(str(outsider["access_token"])),
    )

    assert response.status_code == 404

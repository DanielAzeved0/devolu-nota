import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
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
        pytest.skip("PostgreSQL local indisponivel para testes de documentos fiscais")


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


async def get_fiscal_document(document_id: str) -> FiscalDocument | None:
    async with AsyncSessionLocal() as session:
        return await session.get(FiscalDocument, uuid.UUID(document_id))


async def get_storage_archive(archive_id: str) -> StorageArchive | None:
    async with AsyncSessionLocal() as session:
        return await session.get(StorageArchive, uuid.UUID(archive_id))


async def list_audit_logs(company_id: str, action: str) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.company_id == uuid.UUID(company_id),
                AuditLog.action == action,
            )
        )
        return list(result.scalars().all())


def assert_payload_has_no_document_content(payload: object) -> None:
    serialized = str(payload)
    assert "<xml>conteudo fiscal</xml>" not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "client_secret" not in serialized


async def test_store_mock_xml_fiscal_document_creates_archive_and_audit_log(
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    response = await client.post(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents/mock",
        headers=auth_headers(str(user["access_token"])),
        json={
            "document_type": "NFE_XML",
            "content_type": "application/xml",
            "content": "<xml>conteudo fiscal</xml>",
            "access_key": return_note["original_nfe_key"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["document_type"] == "NFE_XML"
    assert payload["status"] == "AVAILABLE"
    assert payload["storage_archive_id"] is not None
    assert payload["xml_storage_archive_id"] == payload["storage_archive_id"]
    assert payload["pdf_storage_archive_id"] is None
    assert_payload_has_no_document_content(payload)

    stored_document = await get_fiscal_document(str(payload["id"]))
    assert stored_document is not None
    assert str(stored_document.company_id) == company["id"]
    archive = await get_storage_archive(str(payload["storage_archive_id"]))
    assert archive is not None
    assert archive.storage_provider == "LOCAL"
    assert archive.content_type == "application/xml"
    assert archive.size_bytes == len("<xml>conteudo fiscal</xml>".encode("utf-8"))

    logs = await list_audit_logs(str(company["id"]), "FISCAL_DOCUMENT_STORED")
    assert len(logs) == 1
    assert logs[0].entity_id == stored_document.id
    assert logs[0].metadata_["document_type"] == "NFE_XML"
    assert_payload_has_no_document_content(logs[0].metadata_)


async def test_store_mock_json_fiscal_document_uses_generic_archive_link(
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    response = await client.post(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents/mock",
        headers=auth_headers(str(user["access_token"])),
        json={
            "document_type": "TINY_JSON",
            "content_type": "application/json",
            "content": "{\"status\":\"ok\"}",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["document_type"] == "TINY_JSON"
    assert payload["storage_archive_id"] is not None
    assert payload["xml_storage_archive_id"] is None
    assert payload["pdf_storage_archive_id"] is None


async def test_list_fiscal_documents_and_validate_tenant_boundary(client: AsyncClient) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
    )
    create_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents/mock",
        headers=auth_headers(str(owner["access_token"])),
        json={
            "document_type": "DANFE_PDF",
            "content_type": "application/pdf",
            "content": "mock-pdf",
        },
    )
    assert create_response.status_code == 201

    owner_list_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents",
        headers=auth_headers(str(owner["access_token"])),
    )
    outsider_list_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents",
        headers=auth_headers(str(outsider["access_token"])),
    )

    assert owner_list_response.status_code == 200
    assert owner_list_response.json()["count"] == 1
    assert owner_list_response.json()["items"][0]["document_type"] == "DANFE_PDF"
    assert owner_list_response.json()["items"][0]["pdf_storage_archive_id"] is not None
    assert outsider_list_response.status_code == 404


async def test_fiscal_document_routes_validate_input(client: AsyncClient) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    invalid_document_response = await client.post(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents/mock",
        headers=auth_headers(str(user["access_token"])),
        json={
            "document_type": "INVALID",
            "content_type": "application/xml",
            "content": "<xml />",
        },
    )
    invalid_limit_response = await client.get(
        f"/api/v1/companies/{company['id']}/return-notes/{return_note['id']}/fiscal-documents",
        headers=auth_headers(str(user["access_token"])),
        params={"limit": 101},
    )

    assert invalid_document_response.status_code == 422
    assert invalid_limit_response.status_code == 422

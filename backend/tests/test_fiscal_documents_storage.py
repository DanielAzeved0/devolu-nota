import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import AsyncSessionLocal, engine
from app.api.v1.routes import fiscal_documents as fiscal_document_routes
from app.main import app
from app.models import FiscalDocument, StorageArchive
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.users import UserRepository
from app.services.companies import CompanyService
from app.services.fiscal_documents import (
    FiscalDocumentIntegrityError,
    FiscalDocumentNotFoundError,
    FiscalDocumentStorageService,
    FiscalDocumentUnsupportedTypeError,
    calculate_checksum,
)
from app.storage.local import LocalStorageProvider

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
        pytest.skip("PostgreSQL local indisponivel para testes de documentos fiscais")


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


async def sync_return_order(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/mock-sync",
        headers=auth_headers(access_token),
        json={"marketplace": "MERCADO_LIVRE"},
    )
    assert response.status_code == 200
    return response.json()["items"][0]


async def create_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
) -> dict[str, object]:
    return_order = await sync_return_order(
        client,
        access_token=access_token,
        company_id=company_id,
    )
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/{return_order['id']}/return-notes/mock",
        headers=auth_headers(access_token),
        json={},
    )
    assert response.status_code == 201
    return response.json()


async def get_storage_archive(storage_archive_id: str) -> StorageArchive | None:
    async with AsyncSessionLocal() as session:
        return await session.get(StorageArchive, uuid.UUID(storage_archive_id))


async def get_fiscal_document(fiscal_document_id: str) -> FiscalDocument | None:
    async with AsyncSessionLocal() as session:
        return await session.get(FiscalDocument, uuid.UUID(fiscal_document_id))


def configure_fiscal_document_route_storage(monkeypatch, tmp_path) -> None:
    def build_test_service(session):
        company_service = CompanyService(
            companies=CompanyRepository(session),
            company_users=CompanyUserRepository(session),
            users=UserRepository(session),
        )
        return FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            companies=company_service,
            storage=LocalStorageProvider(root_path=tmp_path),
        )

    monkeypatch.setattr(
        fiscal_document_routes,
        "build_fiscal_document_service",
        build_test_service,
    )


async def test_store_fiscal_document_creates_local_file_and_metadata(
    client: AsyncClient,
    tmp_path,
) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    content = b"<nfe><chave>35260612345678000199550010000010011000010010</chave></nfe>"
    issued_at = datetime(2020, 2, 29, 10, 0, 0)

    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )
        stored = await service.store_document(
            company_id=uuid.UUID(str(company["id"])),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="NFE_XML",
            content_bytes=content,
            content_type="application/xml",
            access_key="35260612345678000199550010000010011000010010",
            issued_at=issued_at,
        )
        await session.commit()
        storage_archive_id = str(stored.storage_archive.id)
        fiscal_document_id = str(stored.fiscal_document.id)

    archive = await get_storage_archive(storage_archive_id)
    document = await get_fiscal_document(fiscal_document_id)
    assert archive is not None
    assert document is not None
    assert archive.company_id == uuid.UUID(str(company["id"]))
    assert archive.storage_provider == "LOCAL"
    assert archive.bucket == "fiscal-documents"
    assert str(company["id"]) in archive.object_key
    assert str(return_note["id"]) in archive.object_key
    assert archive.checksum == calculate_checksum(content)
    assert archive.size_bytes == len(content)
    assert archive.retention_until == datetime(2025, 2, 28, 10, 0, 0)
    assert (tmp_path / archive.bucket / archive.object_key).is_file()
    assert document.company_id == uuid.UUID(str(company["id"]))
    assert document.return_note_id == uuid.UUID(str(return_note["id"]))
    assert document.document_type == "NFE_XML"
    assert document.status == "AVAILABLE"
    assert document.xml_storage_archive_id == archive.id
    assert document.issued_at == issued_at


async def test_read_fiscal_document_returns_original_bytes(client: AsyncClient, tmp_path) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    content = b"%PDF-1.7 mock danfe"

    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )
        stored = await service.store_document(
            company_id=uuid.UUID(str(company["id"])),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="DANFE_PDF",
            content_bytes=content,
            content_type="application/pdf",
        )
        await session.commit()
        fiscal_document_id = stored.fiscal_document.id

        read_content = await service.read_document(
            company_id=uuid.UUID(str(company["id"])),
            fiscal_document_id=fiscal_document_id,
        )

    assert read_content == content


async def test_read_fiscal_document_denies_cross_tenant_company_id(client: AsyncClient, tmp_path) -> None:
    owner = await register_user(client)
    outsider = await register_user(client)
    owner_company = await create_company(client, str(owner["access_token"]))
    outsider_company = await create_company(client, str(outsider["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
    )

    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )
        stored = await service.store_document(
            company_id=uuid.UUID(str(owner_company["id"])),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="NFE_XML",
            content_bytes=b"<nfe />",
            content_type="application/xml",
        )
        await session.commit()

        with pytest.raises(FiscalDocumentNotFoundError):
            await service.read_document(
                company_id=uuid.UUID(str(outsider_company["id"])),
                fiscal_document_id=stored.fiscal_document.id,
            )


async def test_store_fiscal_document_rejects_unsupported_type(client: AsyncClient, tmp_path) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )

        with pytest.raises(FiscalDocumentUnsupportedTypeError):
            await service.store_document(
                company_id=uuid.UUID(str(company["id"])),
                return_note_id=uuid.UUID(str(return_note["id"])),
                document_type="TINY_JSON",
                content_bytes=b"{}",
                content_type="application/json",
            )


async def test_read_fiscal_document_detects_checksum_mismatch(client: AsyncClient, tmp_path) -> None:
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )

    async with AsyncSessionLocal() as session:
        service = FiscalDocumentStorageService(
            fiscal_documents=FiscalDocumentRepository(session),
            return_notes=ReturnNoteRepository(session),
            storage=LocalStorageProvider(root_path=tmp_path),
        )
        stored = await service.store_document(
            company_id=uuid.UUID(str(company["id"])),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="NFE_XML",
            content_bytes=b"<nfe>original</nfe>",
            content_type="application/xml",
        )
        await session.commit()
        archive = stored.storage_archive
        (tmp_path / archive.bucket / archive.object_key).write_bytes(b"<nfe>alterado</nfe>")

        with pytest.raises(FiscalDocumentIntegrityError):
            await service.read_document(
                company_id=uuid.UUID(str(company["id"])),
                fiscal_document_id=stored.fiscal_document.id,
            )


async def test_fiscal_document_routes_list_and_download_document(
    client: AsyncClient,
    tmp_path,
    monkeypatch,
) -> None:
    configure_fiscal_document_route_storage(monkeypatch, tmp_path)
    user = await register_user(client)
    company = await create_company(client, str(user["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(user["access_token"]),
        company_id=str(company["id"]),
    )
    content = b"<nfe>download</nfe>"

    async with AsyncSessionLocal() as session:
        service = fiscal_document_routes.build_fiscal_document_service(session)
        stored = await service.store_document(
            company_id=uuid.UUID(str(company["id"])),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="NFE_XML",
            content_bytes=content,
            content_type="application/xml",
        )
        await session.commit()
        fiscal_document_id = str(stored.fiscal_document.id)

    list_response = await client.get(
        f"/api/v1/companies/{company['id']}/fiscal-documents",
        headers=auth_headers(str(user["access_token"])),
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == fiscal_document_id
    assert "object_key" not in payload["items"][0]

    download_response = await client.get(
        f"/api/v1/companies/{company['id']}/fiscal-documents/{fiscal_document_id}/download",
        headers=auth_headers(str(user["access_token"])),
    )
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/xml"
    assert download_response.content == content


async def test_fiscal_document_download_denies_cross_tenant_access(
    client: AsyncClient,
    tmp_path,
    monkeypatch,
) -> None:
    configure_fiscal_document_route_storage(monkeypatch, tmp_path)
    owner = await register_user(client)
    outsider = await register_user(client)
    owner_company = await create_company(client, str(owner["access_token"]))
    outsider_company = await create_company(client, str(outsider["access_token"]))
    return_note = await create_return_note(
        client,
        access_token=str(owner["access_token"]),
        company_id=str(owner_company["id"]),
    )

    async with AsyncSessionLocal() as session:
        service = fiscal_document_routes.build_fiscal_document_service(session)
        stored = await service.store_document(
            company_id=uuid.UUID(str(owner_company["id"])),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="NFE_XML",
            content_bytes=b"<nfe>tenant</nfe>",
            content_type="application/xml",
        )
        await session.commit()
        fiscal_document_id = str(stored.fiscal_document.id)

    response = await client.get(
        f"/api/v1/companies/{outsider_company['id']}/fiscal-documents/{fiscal_document_id}/download",
        headers=auth_headers(str(outsider["access_token"])),
    )
    assert response.status_code == 404

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, update
from sqlalchemy.exc import OperationalError

from app.api.v1.routes import fiscal_documents as fiscal_document_routes
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import CompanyUser
from app.repositories.companies import CompanyRepository, CompanyUserRepository
from app.repositories.fiscal_documents import FiscalDocumentRepository
from app.repositories.return_notes import ReturnNoteRepository
from app.repositories.users import UserRepository
from app.services.companies import CompanyService
from app.services.fiscal_documents import FiscalDocumentStorageService
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
        pytest.skip("PostgreSQL local indisponivel para testes de autorizacao por role")


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
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/mock-sync",
        headers=auth_headers(access_token),
        json={"marketplace": "MERCADO_LIVRE"},
    )
    return response


async def create_return_note(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
) -> dict[str, object]:
    sync_response = await sync_return_order(
        client,
        access_token=access_token,
        company_id=company_id,
    )
    assert sync_response.status_code == 200
    return_order = sync_response.json()["items"][0]
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
    return_note_id: str,
) -> object:
    return await client.post(
        f"/api/v1/companies/{company_id}/emission-batches/mock",
        headers=auth_headers(access_token),
        json={"return_note_ids": [return_note_id], "scenario": "success"},
    )


async def disable_membership(company_id: str, user_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(CompanyUser)
            .where(
                CompanyUser.company_id == uuid.UUID(company_id),
                CompanyUser.user_id == uuid.UUID(user_id),
            )
            .values(status="DISABLED")
        )
        await session.commit()


def configure_fiscal_document_route_storage(monkeypatch, tmp_path: Path) -> None:
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


async def seed_fiscal_document(
    client: AsyncClient,
    *,
    access_token: str,
    company_id: str,
    tmp_path: Path,
    monkeypatch,
) -> str:
    configure_fiscal_document_route_storage(monkeypatch, tmp_path)
    return_note = await create_return_note(
        client,
        access_token=access_token,
        company_id=company_id,
    )
    content = b"<nfe>viewer-read</nfe>"

    async with AsyncSessionLocal() as session:
        service = fiscal_document_routes.build_fiscal_document_service(session)
        stored = await service.store_document(
            company_id=uuid.UUID(company_id),
            return_note_id=uuid.UUID(str(return_note["id"])),
            document_type="NFE_XML",
            content_bytes=content,
            content_type="application/xml",
        )
        await session.commit()
        return str(stored.fiscal_document.id)


@pytest_asyncio.fixture
async def company_with_roles(client: AsyncClient) -> dict[str, object]:
    owner = await register_user(client)
    admin = await register_user(client)
    operator = await register_user(client)
    viewer = await register_user(client)
    outsider = await register_user(client)
    company = await create_company(client, str(owner["access_token"]))

    await add_company_user(
        client,
        owner_access_token=str(owner["access_token"]),
        company_id=str(company["id"]),
        user_id=str(admin["user"]["id"]),
        role="ADMIN",
    )
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

    return {
        "company": company,
        "owner": owner,
        "admin": admin,
        "operator": operator,
        "viewer": viewer,
        "outsider": outsider,
    }


async def test_viewer_can_read_company_sensitive_data(
    client: AsyncClient,
    company_with_roles: dict[str, object],
    tmp_path,
    monkeypatch,
) -> None:
    company = company_with_roles["company"]
    viewer = company_with_roles["viewer"]
    owner = company_with_roles["owner"]
    company_id = str(company["id"])
    viewer_token = str(viewer["access_token"])
    owner_token = str(owner["access_token"])

    fiscal_document_id = await seed_fiscal_document(
        client,
        access_token=owner_token,
        company_id=company_id,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    note = await create_return_note(client, access_token=owner_token, company_id=company_id)
    batch_response = await create_mock_batch(
        client,
        access_token=owner_token,
        company_id=company_id,
        return_note_id=str(note["id"]),
    )
    assert batch_response.status_code == 201
    batch_id = batch_response.json()["id"]

    users_response = await client.get(
        f"/api/v1/companies/{company_id}/users",
        headers=auth_headers(viewer_token),
    )
    audit_response = await client.get(
        f"/api/v1/companies/{company_id}/audit-logs",
        headers=auth_headers(viewer_token),
    )
    documents_response = await client.get(
        f"/api/v1/companies/{company_id}/fiscal-documents",
        headers=auth_headers(viewer_token),
    )
    download_response = await client.get(
        f"/api/v1/companies/{company_id}/fiscal-documents/{fiscal_document_id}/download",
        headers=auth_headers(viewer_token),
    )
    batch_response = await client.get(
        f"/api/v1/companies/{company_id}/emission-batches/{batch_id}",
        headers=auth_headers(viewer_token),
    )
    jobs_response = await client.get(
        f"/api/v1/companies/{company_id}/emission-batches/{batch_id}/jobs",
        headers=auth_headers(viewer_token),
    )

    assert users_response.status_code == 200
    assert audit_response.status_code == 200
    assert documents_response.status_code == 200
    assert download_response.status_code == 200
    assert batch_response.status_code == 200
    assert jobs_response.status_code == 200


async def test_viewer_blocked_from_operational_mutations(
    client: AsyncClient,
    company_with_roles: dict[str, object],
) -> None:
    company = company_with_roles["company"]
    viewer = company_with_roles["viewer"]
    owner = company_with_roles["owner"]
    company_id = str(company["id"])
    viewer_token = str(viewer["access_token"])
    owner_token = str(owner["access_token"])

    sync_owner_response = await sync_return_order(
        client,
        access_token=owner_token,
        company_id=company_id,
    )
    assert sync_owner_response.status_code == 200
    return_order_id = sync_owner_response.json()["items"][0]["id"]
    note = await create_return_note(client, access_token=owner_token, company_id=company_id)

    sync_response = await sync_return_order(
        client,
        access_token=viewer_token,
        company_id=company_id,
    )
    note_response = await client.post(
        f"/api/v1/companies/{company_id}/return-orders/{return_order_id}/return-notes/mock",
        headers=auth_headers(viewer_token),
        json={},
    )
    batch_response = await create_mock_batch(
        client,
        access_token=viewer_token,
        company_id=company_id,
        return_note_id=str(note["id"]),
    )
    add_user_response = await client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=auth_headers(viewer_token),
        json={"user_id": str(owner["user"]["id"]), "role": "VIEWER"},
    )
    integration_response = await client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=auth_headers(viewer_token),
        json={"provider": "TINY"},
    )
    retention_response = await client.post(
        f"/api/v1/companies/{company_id}/retention/apply",
        headers=auth_headers(viewer_token),
    )

    assert sync_response.status_code == 403
    assert note_response.status_code == 403
    assert batch_response.status_code == 403
    assert add_user_response.status_code == 403
    assert integration_response.status_code == 403
    assert retention_response.status_code == 403


async def test_operator_blocked_from_admin_actions(
    client: AsyncClient,
    company_with_roles: dict[str, object],
) -> None:
    company = company_with_roles["company"]
    admin = company_with_roles["admin"]
    operator = company_with_roles["operator"]
    company_id = str(company["id"])
    operator_token = str(operator["access_token"])
    admin_token = str(admin["access_token"])

    integration_response = await client.post(
        f"/api/v1/companies/{company_id}/integrations",
        headers=auth_headers(admin_token),
        json={"provider": "TINY"},
    )
    assert integration_response.status_code == 201
    integration_id = integration_response.json()["id"]

    credentials_response = await client.put(
        f"/api/v1/companies/{company_id}/integrations/{integration_id}/credentials",
        headers=auth_headers(operator_token),
        json={"api_token": "operator-token"},
    )
    add_user_response = await client.post(
        f"/api/v1/companies/{company_id}/users",
        headers=auth_headers(operator_token),
        json={"user_id": str(operator["user"]["id"]), "role": "VIEWER"},
    )
    retention_response = await client.post(
        f"/api/v1/companies/{company_id}/retention/apply",
        headers=auth_headers(operator_token),
    )

    assert credentials_response.status_code == 403
    assert add_user_response.status_code == 403
    assert retention_response.status_code == 403


async def test_admin_can_apply_retention(
    client: AsyncClient,
    company_with_roles: dict[str, object],
) -> None:
    company = company_with_roles["company"]
    admin = company_with_roles["admin"]
    company_id = str(company["id"])

    response = await client.post(
        f"/api/v1/companies/{company_id}/retention/apply",
        headers=auth_headers(str(admin["access_token"])),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["moved_to_cold"] == 0
    assert payload["moved_to_deleted"] == 0
    assert payload["skipped"] == 0


async def test_sensitive_routes_deny_cross_tenant_access(
    client: AsyncClient,
    company_with_roles: dict[str, object],
    tmp_path,
    monkeypatch,
) -> None:
    company = company_with_roles["company"]
    outsider = company_with_roles["outsider"]
    owner = company_with_roles["owner"]
    company_id = str(company["id"])
    outsider_token = str(outsider["access_token"])
    owner_token = str(owner["access_token"])

    fiscal_document_id = await seed_fiscal_document(
        client,
        access_token=owner_token,
        company_id=company_id,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    users_response = await client.get(
        f"/api/v1/companies/{company_id}/users",
        headers=auth_headers(outsider_token),
    )
    audit_response = await client.get(
        f"/api/v1/companies/{company_id}/audit-logs",
        headers=auth_headers(outsider_token),
    )
    documents_response = await client.get(
        f"/api/v1/companies/{company_id}/fiscal-documents",
        headers=auth_headers(outsider_token),
    )
    download_response = await client.get(
        f"/api/v1/companies/{company_id}/fiscal-documents/{fiscal_document_id}/download",
        headers=auth_headers(outsider_token),
    )
    retention_response = await client.post(
        f"/api/v1/companies/{company_id}/retention/apply",
        headers=auth_headers(outsider_token),
    )

    assert users_response.status_code == 404
    assert audit_response.status_code == 404
    assert documents_response.status_code == 404
    assert download_response.status_code == 404
    assert retention_response.status_code == 404


async def test_inactive_membership_denies_company_access(
    client: AsyncClient,
    company_with_roles: dict[str, object],
) -> None:
    company = company_with_roles["company"]
    viewer = company_with_roles["viewer"]
    company_id = str(company["id"])
    viewer_token = str(viewer["access_token"])

    await disable_membership(company_id, str(viewer["user"]["id"]))

    users_response = await client.get(
        f"/api/v1/companies/{company_id}/users",
        headers=auth_headers(viewer_token),
    )
    retention_response = await client.post(
        f"/api/v1/companies/{company_id}/retention/apply",
        headers=auth_headers(viewer_token),
    )

    assert users_response.status_code == 404
    assert retention_response.status_code == 404

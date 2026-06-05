from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from app.models import AuditLog, User
from app.repositories.audit_logs import AuditLogRepository
from app.services.companies import CompanyService

SENSITIVE_AUDIT_KEYS = {
    "access_token",
    "refresh_token",
    "api_token",
    "client_secret",
    "encrypted_credentials",
    "password",
    "password_hash",
    "secret",
}


class SensitiveAuditMetadataError(ValueError):
    pass


class AuditLogService:
    def __init__(
        self,
        *,
        audit_logs: AuditLogRepository,
        companies: CompanyService | None = None,
    ) -> None:
        self.audit_logs = audit_logs
        self.companies = companies

    async def create_log(
        self,
        *,
        company_id: UUID,
        user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        safe_metadata = sanitize_audit_metadata(metadata)
        return await self.audit_logs.create(
            company_id=company_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=safe_metadata,
        )

    async def list_company_logs(
        self,
        *,
        company_id: UUID,
        current_user: User,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        action: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        if self.companies is None:
            raise RuntimeError("CompanyService is required to list audit logs")
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        return await self.audit_logs.list_for_company(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
            offset=offset,
        )


def sanitize_audit_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    assert_no_sensitive_keys(metadata)
    return metadata


def assert_no_sensitive_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            normalized_key = str(key).lower()
            if normalized_key in SENSITIVE_AUDIT_KEYS:
                raise SensitiveAuditMetadataError("Audit metadata contains sensitive keys")
            assert_no_sensitive_keys(nested_value)
        return

    if isinstance(value, list):
        for item in value:
            assert_no_sensitive_keys(item)

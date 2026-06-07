from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.repositories.retention import RetentionRepository
from app.services.fiscal_documents import add_years
from app.services.audit_logs import AuditLogService


class RetentionPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class RetentionPolicy:
    cold_after_years: int = 5
    delete_after_years: int = 10

    def __post_init__(self) -> None:
        if self.cold_after_years <= 0:
            raise RetentionPolicyError("cold_after_years must be greater than zero")
        if self.delete_after_years <= self.cold_after_years:
            raise RetentionPolicyError("delete_after_years must be greater than cold_after_years")


@dataclass(frozen=True)
class RetentionResult:
    moved_to_cold: int
    moved_to_deleted: int
    skipped: int


class RetentionService:
    def __init__(
        self,
        *,
        retention: RetentionRepository,
        audit_logs: AuditLogService | None = None,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self.retention = retention
        self.audit_logs = audit_logs
        self.policy = policy or RetentionPolicy()

    async def apply_company_retention(
        self,
        *,
        company_id: UUID,
        now: datetime | None = None,
    ) -> RetentionResult:
        current_time = now or utcnow()
        delete_retention_cutoff = add_years(
            current_time,
            -(self.policy.delete_after_years - self.policy.cold_after_years),
        )

        delete_archives = await self.retention.list_archives_for_deletion(
            company_id=company_id,
            delete_retention_cutoff=delete_retention_cutoff,
        )
        for archive in delete_archives:
            previous_status = archive.status
            archive.status = "DELETED"
            await self._audit_transition(
                company_id=company_id,
                archive_id=archive.id,
                previous_status=previous_status,
                new_status="DELETED",
                reason="retention_policy_deleted",
                retention_until=archive.retention_until,
                cutoff=delete_retention_cutoff,
            )

        deleted_ids = {archive.id for archive in delete_archives}
        cold_archives = await self.retention.list_archives_for_cold_storage(
            company_id=company_id,
            cold_cutoff=current_time,
        )
        moved_to_cold = 0
        for archive in cold_archives:
            if archive.id in deleted_ids:
                continue
            previous_status = archive.status
            archive.status = "COLD"
            await self._audit_transition(
                company_id=company_id,
                archive_id=archive.id,
                previous_status=previous_status,
                new_status="COLD",
                reason="retention_policy_cold",
                retention_until=archive.retention_until,
                cutoff=current_time,
            )
            moved_to_cold += 1

        return RetentionResult(
            moved_to_cold=moved_to_cold,
            moved_to_deleted=len(delete_archives),
            skipped=0,
        )

    async def _audit_transition(
        self,
        *,
        company_id: UUID,
        archive_id: UUID,
        previous_status: str,
        new_status: str,
        reason: str,
        retention_until: datetime | None,
        cutoff: datetime,
    ) -> None:
        if self.audit_logs is None:
            return
        await self.audit_logs.create_log(
            company_id=company_id,
            user_id=None,
            action=(
                "STORAGE_ARCHIVE_DELETED_BY_RETENTION"
                if new_status == "DELETED"
                else "STORAGE_ARCHIVE_MOVED_TO_COLD"
            ),
            entity_type="storage_archive",
            entity_id=archive_id,
            metadata={
                "previous_status": previous_status,
                "new_status": new_status,
                "reason": reason,
                "retention_until": retention_until.isoformat() if retention_until is not None else None,
                "cutoff": cutoff.isoformat(),
                "policy": {
                    "cold_after_years": self.policy.cold_after_years,
                    "delete_after_years": self.policy.delete_after_years,
                },
            },
        )


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

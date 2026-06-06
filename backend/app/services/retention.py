from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models import RetentionJob, User
from app.repositories.retention import RetentionRepository
from app.services.companies import CompanyService

COLD_STORAGE_AFTER_DAYS = 365 * 5
DELETE_AFTER_DAYS = 365 * 11
RetentionAction = str


class RetentionMockService:
    def __init__(
        self,
        *,
        companies: CompanyService,
        retention: RetentionRepository,
    ) -> None:
        self.companies = companies
        self.retention = retention

    async def run_company_retention(
        self,
        *,
        company_id: UUID,
        current_user: User,
        now: datetime | None = None,
    ) -> tuple[int, int, int, list[tuple[RetentionJob, RetentionAction]]]:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        current_time = now or utcnow()
        cold_cutoff = current_time - timedelta(days=COLD_STORAGE_AFTER_DAYS)
        delete_cutoff = current_time - timedelta(days=DELETE_AFTER_DAYS)
        archives = await self.retention.list_archives_created_before(
            company_id=company_id,
            cutoff=cold_cutoff,
        )

        archived_count = 0
        deleted_count = 0
        skipped_count = 0
        jobs: list[tuple[RetentionJob, RetentionAction]] = []

        for archive in archives:
            if archive.created_at <= delete_cutoff:
                archive.status = "DELETED"
                await self.retention.mark_documents_deleted_for_archive(
                    company_id=company_id,
                    storage_archive_id=archive.id,
                )
                job = await self.retention.create_job(
                    company_id=company_id,
                    storage_archive_id=archive.id,
                    status="COMPLETED",
                    processed_at=current_time,
                )
                jobs.append((job, "RETENTION_DELETE_MARKED"))
                deleted_count += 1
                continue

            if archive.status == "ACTIVE":
                archive.status = "COLD"
                job = await self.retention.create_job(
                    company_id=company_id,
                    storage_archive_id=archive.id,
                    status="COMPLETED",
                    processed_at=current_time,
                )
                jobs.append((job, "RETENTION_ARCHIVE_COLD"))
                archived_count += 1
                continue

            skipped_count += 1

        return archived_count, deleted_count, skipped_count, jobs


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

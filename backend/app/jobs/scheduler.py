import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import AsyncSessionLocal
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.companies import CompanyRepository
from app.repositories.retention import RetentionRepository
from app.repositories.retention_jobs import RetentionJobRepository
from app.services.audit_logs import AuditLogService
from app.services.retention import RetentionService

RETENTION_JOB_ID = "retention_scheduler"
RETENTION_INTERVAL_MINUTES = 5
RETENTION_TIMEZONE = "America/Sao_Paulo"


async def run_retention_cycle(
    *,
    company_ids: Sequence[UUID] | None = None,
    now: datetime | None = None,
    processor: Callable[[UUID, datetime], Awaitable[bool]] | None = None,
) -> int:
    current_time = now or utcnow()
    active_company_ids = list(company_ids) if company_ids is not None else await list_active_company_ids()
    processed_count = 0
    processor_fn = processor or _process_company_retention

    for company_id in active_company_ids:
        try:
            await processor_fn(company_id, current_time)
        except Exception:  # pragma: no cover - safety net for runtime failures
            pass
        processed_count += 1

    return processed_count


async def list_active_company_ids() -> list[UUID]:
    async with AsyncSessionLocal() as session:
        return await CompanyRepository(session).list_active_company_ids()


async def _process_company_retention(company_id: UUID, now: datetime) -> bool:
    async with AsyncSessionLocal() as session:
        retention_jobs = RetentionJobRepository(session)
        job = await retention_jobs.create(company_id=company_id, scheduled_for=now)
        await session.commit()

        try:
            service = RetentionService(
                retention=RetentionRepository(session),
                audit_logs=AuditLogService(audit_logs=AuditLogRepository(session)),
            )
            await service.apply_company_retention(company_id=company_id, now=now)
            await retention_jobs.mark_completed(job_id=job.id, processed_at=now)
            await session.commit()
            return True
        except Exception as exc:  # pragma: no cover - safety net for runtime failures
            await session.rollback()
            await retention_jobs.mark_failed(
                job_id=job.id,
                processed_at=now,
                error_message=str(exc),
            )
            await session.commit()
            return False


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=RETENTION_TIMEZONE)
    scheduler.add_job(
        run_retention_cycle_job,
        "interval",
        minutes=RETENTION_INTERVAL_MINUTES,
        id=RETENTION_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    return scheduler


def run_retention_cycle_job() -> None:
    asyncio.run(run_retention_cycle())


def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


if __name__ == "__main__":
    main()

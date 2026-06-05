import asyncio
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.emissions import EmissionRepository
from app.schemas.emissions import MockEmissionScenario
from app.services.emissions import EmissionBatchMockProcessor
from app.workers.celery_app import celery_app


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="emissions.process_mock_batch")
def process_mock_emission_batch(
    *,
    company_id: str,
    batch_id: str,
    scenario: MockEmissionScenario = "success",
) -> str:
    return asyncio.run(
        _process_mock_emission_batch(
            company_id=UUID(company_id),
            batch_id=UUID(batch_id),
            scenario=scenario,
        )
    )


async def _process_mock_emission_batch(
    *,
    company_id: UUID,
    batch_id: UUID,
    scenario: MockEmissionScenario,
) -> str:
    async with AsyncSessionLocal() as session:
        processor = EmissionBatchMockProcessor(
            emissions=EmissionRepository(session),
            audit_logs=AuditLogRepository(session),
        )
        batch = await processor.process_batch(
            company_id=company_id,
            batch_id=batch_id,
            scenario=scenario,
        )
        await session.commit()
        return str(batch.id)

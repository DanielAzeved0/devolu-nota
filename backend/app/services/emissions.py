from datetime import UTC, datetime
from uuid import UUID

from app.models import EmissionBatch, EmissionJob, User
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.emissions import EmissionRepository
from app.schemas.emissions import EmissionBatchMockCreateRequest, MockEmissionScenario
from app.services.audit_logs import AuditLogService
from app.services.companies import CompanyService

ELIGIBLE_RETURN_NOTE_STATUSES = ("DRAFT", "READY_TO_EMIT")
FINAL_BATCH_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")


class EmissionBatchNotFoundError(ValueError):
    pass


class EmissionBatchInvalidStateError(ValueError):
    pass


class ReturnNoteNotEligibleError(ValueError):
    pass


class ReturnNoteAlreadyQueuedError(ValueError):
    pass


class EmissionBatchMockService:
    def __init__(
        self,
        *,
        companies: CompanyService,
        emissions: EmissionRepository,
        audit_logs: AuditLogRepository | None = None,
    ) -> None:
        self.companies = companies
        self.emissions = emissions
        self.audit_logs = AuditLogService(audit_logs=audit_logs) if audit_logs is not None else None

    async def create_mock_batch(
        self,
        *,
        company_id: UUID,
        payload: EmissionBatchMockCreateRequest,
        current_user: User,
    ) -> tuple[EmissionBatch, list[EmissionJob]]:
        await self.companies.get_company(company_id=company_id, current_user=current_user)

        return_notes = await self.emissions.list_return_notes_for_update(
            company_id=company_id,
            return_note_ids=payload.return_note_ids,
        )
        if len(return_notes) != len(payload.return_note_ids):
            raise ReturnNoteNotEligibleError("Return note is not eligible for emission")

        return_notes_by_id = {return_note.id: return_note for return_note in return_notes}
        ordered_return_notes = [return_notes_by_id[return_note_id] for return_note_id in payload.return_note_ids]
        invalid_statuses = [
            return_note.status
            for return_note in ordered_return_notes
            if return_note.status not in ELIGIBLE_RETURN_NOTE_STATUSES
        ]
        if invalid_statuses:
            raise ReturnNoteNotEligibleError("Return note is not eligible for emission")

        active_jobs = await self.emissions.list_active_jobs_for_return_notes(
            company_id=company_id,
            return_note_ids=payload.return_note_ids,
        )
        if active_jobs:
            raise ReturnNoteAlreadyQueuedError("Return note already has an active emission job")

        batch = await self.emissions.create_batch(
            company_id=company_id,
            requested_by_user_id=current_user.id,
        )
        jobs = [
            await self.emissions.create_job(
                company_id=company_id,
                batch_id=batch.id,
                return_note_id=return_note.id,
            )
            for return_note in ordered_return_notes
        ]
        for return_note in ordered_return_notes:
            previous_status = return_note.status
            return_note.status = "QUEUED"
            await self._audit(
                company_id=company_id,
                user_id=current_user.id,
                action="RETURN_NOTE_QUEUED",
                entity_type="return_note",
                entity_id=return_note.id,
                metadata={
                    "previous_status": previous_status,
                    "new_status": "QUEUED",
                    "batch_id": str(batch.id),
                },
            )

        await self._audit(
            company_id=company_id,
            user_id=current_user.id,
            action="EMISSION_BATCH_CREATED",
            entity_type="emission_batch",
            entity_id=batch.id,
            metadata={
                "status": batch.status,
                "scenario": payload.scenario,
                "jobs_count": len(jobs),
            },
        )
        for job in jobs:
            await self._audit(
                company_id=company_id,
                user_id=current_user.id,
                action="EMISSION_JOB_CREATED",
                entity_type="emission_job",
                entity_id=job.id,
                metadata={
                    "status": job.status,
                    "batch_id": str(batch.id),
                    "return_note_id": str(job.return_note_id),
                },
            )

        return batch, jobs

    async def _audit(
        self,
        *,
        company_id: UUID,
        user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.audit_logs is None:
            return
        await self.audit_logs.create_log(
            company_id=company_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )

    async def get_batch(
        self,
        *,
        company_id: UUID,
        batch_id: UUID,
        current_user: User,
    ) -> EmissionBatch:
        await self.companies.get_company(company_id=company_id, current_user=current_user)
        batch = await self.emissions.get_batch_by_company_id(
            company_id=company_id,
            batch_id=batch_id,
        )
        if batch is None:
            raise EmissionBatchNotFoundError("Emission batch not found")
        return batch

    async def list_jobs(
        self,
        *,
        company_id: UUID,
        batch_id: UUID,
        current_user: User,
    ) -> list[EmissionJob]:
        await self.get_batch(company_id=company_id, batch_id=batch_id, current_user=current_user)
        return await self.emissions.list_jobs_by_batch_id(company_id=company_id, batch_id=batch_id)


class EmissionBatchMockProcessor:
    def __init__(
        self,
        *,
        emissions: EmissionRepository,
        audit_logs: AuditLogRepository | None = None,
    ) -> None:
        self.emissions = emissions
        self.audit_logs = AuditLogService(audit_logs=audit_logs) if audit_logs is not None else None

    async def process_batch(
        self,
        *,
        company_id: UUID,
        batch_id: UUID,
        scenario: MockEmissionScenario = "success",
    ) -> EmissionBatch:
        batch = await self.emissions.get_batch_by_company_id(company_id=company_id, batch_id=batch_id)
        if batch is None:
            raise EmissionBatchNotFoundError("Emission batch not found")
        if batch.status in FINAL_BATCH_STATUSES:
            raise EmissionBatchInvalidStateError("Emission batch already finalized")

        jobs = await self.emissions.list_jobs_by_batch_id(company_id=company_id, batch_id=batch_id)
        return_notes = await self.emissions.list_return_notes_for_update(
            company_id=company_id,
            return_note_ids=[job.return_note_id for job in jobs],
        )
        return_notes_by_id = {return_note.id: return_note for return_note in return_notes}

        now = utcnow()
        previous_batch_status = batch.status
        batch.status = "RUNNING"
        batch.started_at = batch.started_at or now
        await self._audit(
            company_id=company_id,
            action="EMISSION_BATCH_STARTED",
            entity_type="emission_batch",
            entity_id=batch.id,
            metadata={
                "previous_status": previous_batch_status,
                "new_status": "RUNNING",
                "scenario": scenario,
                "jobs_count": len(jobs),
            },
        )

        success_count = 0
        failure_count = 0
        for index, job in enumerate(jobs):
            return_note = return_notes_by_id[job.return_note_id]
            if return_note.status == "ISSUED":
                job.status = "SUCCESS"
                job.finished_at = job.finished_at or utcnow()
                success_count += 1
                continue

            previous_job_status = job.status
            job.status = "RUNNING"
            job.started_at = job.started_at or utcnow()
            job.attempts += 1
            await self._audit(
                company_id=company_id,
                action="EMISSION_JOB_STARTED",
                entity_type="emission_job",
                entity_id=job.id,
                metadata={
                    "previous_status": previous_job_status,
                    "new_status": "RUNNING",
                    "batch_id": str(batch.id),
                    "return_note_id": str(return_note.id),
                    "attempts": job.attempts,
                },
            )

            if should_fail_job(scenario=scenario, index=index):
                previous_note_status = return_note.status
                job.status = "FAILED"
                job.finished_at = utcnow()
                job.last_error = "Mock emission failed"
                return_note.status = "FAILED"
                return_note.error_message = "Mock emission failed"
                await self._audit(
                    company_id=company_id,
                    action="EMISSION_JOB_FAILED",
                    entity_type="emission_job",
                    entity_id=job.id,
                    metadata={
                        "new_status": "FAILED",
                        "batch_id": str(batch.id),
                        "return_note_id": str(return_note.id),
                        "error_message": job.last_error,
                    },
                )
                await self._audit(
                    company_id=company_id,
                    action="RETURN_NOTE_FAILED",
                    entity_type="return_note",
                    entity_id=return_note.id,
                    metadata={
                        "previous_status": previous_note_status,
                        "new_status": "FAILED",
                        "batch_id": str(batch.id),
                        "job_id": str(job.id),
                        "error_message": return_note.error_message,
                    },
                )
                failure_count += 1
                continue

            previous_note_status = return_note.status
            job.status = "SUCCESS"
            job.finished_at = utcnow()
            job.last_error = None
            return_note.status = "ISSUED"
            return_note.return_nfe_key = build_mock_return_nfe_key(return_note.id)
            return_note.issued_at = job.finished_at
            return_note.error_message = None
            await self._audit(
                company_id=company_id,
                action="EMISSION_JOB_SUCCEEDED",
                entity_type="emission_job",
                entity_id=job.id,
                metadata={
                    "new_status": "SUCCESS",
                    "batch_id": str(batch.id),
                    "return_note_id": str(return_note.id),
                },
            )
            await self._audit(
                company_id=company_id,
                action="RETURN_NOTE_ISSUED",
                entity_type="return_note",
                entity_id=return_note.id,
                metadata={
                    "previous_status": previous_note_status,
                    "new_status": "ISSUED",
                    "batch_id": str(batch.id),
                    "job_id": str(job.id),
                },
            )
            success_count += 1

        batch.finished_at = utcnow()
        batch.status = "COMPLETED" if failure_count == 0 and success_count == len(jobs) else "FAILED"
        await self._audit(
            company_id=company_id,
            action="EMISSION_BATCH_COMPLETED" if batch.status == "COMPLETED" else "EMISSION_BATCH_FAILED",
            entity_type="emission_batch",
            entity_id=batch.id,
            metadata={
                "new_status": batch.status,
                "success_count": success_count,
                "failure_count": failure_count,
            },
        )
        return batch

    async def _audit(
        self,
        *,
        company_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.audit_logs is None:
            return
        await self.audit_logs.create_log(
            company_id=company_id,
            user_id=None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )


def should_fail_job(*, scenario: MockEmissionScenario, index: int) -> bool:
    if scenario == "failure":
        return True
    if scenario == "partial_failure":
        return index % 2 == 1
    return False


def build_mock_return_nfe_key(return_note_id: UUID) -> str:
    digits = "".join(str(int(char, 16)) for char in return_note_id.hex)
    return digits[:44].ljust(44, "0")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

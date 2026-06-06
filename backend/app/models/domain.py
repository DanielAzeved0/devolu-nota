from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


def status_check(column: str, values: tuple[str, ...]) -> str:
    allowed = ", ".join(f"'{value}'" for value in values)
    return f"{column} in ({allowed})"


COMPANY_STATUSES = ("ACTIVE", "SUSPENDED", "INACTIVE")
USER_STATUSES = ("ACTIVE", "INVITED", "DISABLED")
MEMBERSHIP_ROLES = ("OWNER", "ADMIN", "OPERATOR", "VIEWER")
MEMBERSHIP_STATUSES = ("ACTIVE", "INVITED", "DISABLED")
INTEGRATION_PROVIDERS = ("TINY", "MERCADO_LIVRE", "SHOPEE")
INTEGRATION_STATUSES = ("ACTIVE", "INVALID_TOKEN", "EXPIRED", "DISCONNECTED", "ERROR")
MARKETPLACES = ("MERCADO_LIVRE", "SHOPEE")
RETURN_ORDER_STATUSES = ("OPEN", "READY_TO_REVIEW", "LINKED_TO_NFE", "CANCELLED", "ARCHIVED")
RETURN_NOTE_STATUSES = (
    "DRAFT",
    "READY_TO_EMIT",
    "QUEUED",
    "PROCESSING",
    "ISSUED",
    "FAILED",
    "CANCELLED",
    "ARCHIVED",
    "DELETED_BY_RETENTION",
)
EMISSION_BATCH_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
EMISSION_JOB_STATUSES = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "RETRYING")
FISCAL_DOCUMENT_TYPES = ("NFE_XML", "DANFE_PDF", "TINY_JSON", "SEFAZ_EVENT")
FISCAL_DOCUMENT_STATUSES = ("PENDING", "AVAILABLE", "ARCHIVED", "DELETED", "ERROR")
STORAGE_PROVIDERS = ("S3", "R2", "B2", "WASABI", "LOCAL")
STORAGE_ARCHIVE_STATUSES = ("ACTIVE", "COLD", "DELETED", "ERROR")
RETENTION_JOB_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(status_check("status", COMPANY_STATUSES), name="ck_companies_status"),
        Index("ix_companies_status", "status"),
        Index("ix_companies_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255))
    document: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    deleted_at: Mapped[datetime | None] = mapped_column()

    users: Mapped[list[CompanyUser]] = relationship(back_populates="company")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(status_check("status", USER_STATUSES), name="ck_users_status"),
        Index("ix_users_status", "status"),
        Index("ix_users_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    deleted_at: Mapped[datetime | None] = mapped_column()

    companies: Mapped[list[CompanyUser]] = relationship(back_populates="user")


class CompanyUser(TimestampMixin, Base):
    __tablename__ = "company_users"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_users_company_user"),
        CheckConstraint(status_check("role", MEMBERSHIP_ROLES), name="ck_company_users_role"),
        CheckConstraint(status_check("status", MEMBERSHIP_STATUSES), name="ck_company_users_status"),
        Index("ix_company_users_company_id", "company_id"),
        Index("ix_company_users_user_id", "user_id"),
        Index("ix_company_users_status", "status"),
        Index("ix_company_users_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")

    company: Mapped[Company] = relationship(back_populates="users")
    user: Mapped[User] = relationship(back_populates="companies")


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint(status_check("provider", INTEGRATION_PROVIDERS), name="ck_integrations_provider"),
        CheckConstraint(status_check("status", INTEGRATION_STATUSES), name="ck_integrations_status"),
        Index("ix_integrations_company_id", "company_id"),
        Index("ix_integrations_status", "status"),
        Index("ix_integrations_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCONNECTED")
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    encrypted_credentials: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_sync_at: Mapped[datetime | None] = mapped_column()


class MarketplaceAccount(TimestampMixin, Base):
    __tablename__ = "marketplace_accounts"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "marketplace",
            "external_account_id",
            name="uq_marketplace_accounts_company_marketplace_external",
        ),
        CheckConstraint(status_check("marketplace", MARKETPLACES), name="ck_marketplace_accounts_marketplace"),
        CheckConstraint(status_check("status", INTEGRATION_STATUSES), name="ck_marketplace_accounts_status"),
        Index("ix_marketplace_accounts_company_id", "company_id"),
        Index("ix_marketplace_accounts_integration_id", "integration_id"),
        Index("ix_marketplace_accounts_marketplace", "marketplace"),
        Index("ix_marketplace_accounts_status", "status"),
        Index("ix_marketplace_accounts_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCONNECTED")


class ReturnOrder(TimestampMixin, Base):
    __tablename__ = "return_orders"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "marketplace",
            "external_order_id",
            name="uq_return_orders_company_marketplace_external_order",
        ),
        CheckConstraint(status_check("marketplace", MARKETPLACES), name="ck_return_orders_marketplace"),
        CheckConstraint(status_check("status", RETURN_ORDER_STATUSES), name="ck_return_orders_status"),
        Index("ix_return_orders_company_id", "company_id"),
        Index("ix_return_orders_marketplace_account_id", "marketplace_account_id"),
        Index("ix_return_orders_marketplace", "marketplace"),
        Index("ix_return_orders_external_order_id", "external_order_id"),
        Index("ix_return_orders_original_nfe_key", "original_nfe_key"),
        Index("ix_return_orders_status", "status"),
        Index("ix_return_orders_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    marketplace_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("marketplace_accounts.id"), nullable=False
    )
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    external_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    original_nfe_key: Mapped[str | None] = mapped_column(String(44))
    customer_document: Mapped[str | None] = mapped_column(String(32))
    customer_name: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ReturnNote(TimestampMixin, Base):
    __tablename__ = "return_notes"
    __table_args__ = (
        CheckConstraint(status_check("status", RETURN_NOTE_STATUSES), name="ck_return_notes_status"),
        Index("ix_return_notes_company_id", "company_id"),
        Index("ix_return_notes_return_order_id", "return_order_id"),
        Index("ix_return_notes_status", "status"),
        Index("ix_return_notes_created_at", "created_at"),
        Index("ix_return_notes_original_nfe_key", "original_nfe_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    return_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("return_orders.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    original_nfe_key: Mapped[str | None] = mapped_column(String(44))
    return_nfe_key: Mapped[str | None] = mapped_column(String(44))
    number: Mapped[str | None] = mapped_column(String(32))
    series: Mapped[str | None] = mapped_column(String(16))
    issued_at: Mapped[datetime | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)


class EmissionBatch(TimestampMixin, Base):
    __tablename__ = "emission_batches"
    __table_args__ = (
        CheckConstraint(status_check("status", EMISSION_BATCH_STATUSES), name="ck_emission_batches_status"),
        Index("ix_emission_batches_company_id", "company_id"),
        Index("ix_emission_batches_requested_by_user_id", "requested_by_user_id"),
        Index("ix_emission_batches_status", "status"),
        Index("ix_emission_batches_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class EmissionJob(TimestampMixin, Base):
    __tablename__ = "emission_jobs"
    __table_args__ = (
        CheckConstraint(status_check("status", EMISSION_JOB_STATUSES), name="ck_emission_jobs_status"),
        Index("ix_emission_jobs_company_id", "company_id"),
        Index("ix_emission_jobs_batch_id", "batch_id"),
        Index("ix_emission_jobs_return_note_id", "return_note_id"),
        Index("ix_emission_jobs_status", "status"),
        Index("ix_emission_jobs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emission_batches.id"), nullable=False)
    return_note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("return_notes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    scheduled_at: Mapped[datetime | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(Text)


class StorageArchive(TimestampMixin, Base):
    __tablename__ = "storage_archives"
    __table_args__ = (
        CheckConstraint(
            status_check("storage_provider", STORAGE_PROVIDERS),
            name="ck_storage_archives_storage_provider",
        ),
        CheckConstraint(status_check("status", STORAGE_ARCHIVE_STATUSES), name="ck_storage_archives_status"),
        Index("ix_storage_archives_company_id", "company_id"),
        Index("ix_storage_archives_status", "status"),
        Index("ix_storage_archives_created_at", "created_at"),
        Index("ix_storage_archives_retention_until", "retention_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    checksum: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    retention_until: Mapped[datetime | None] = mapped_column()


class FiscalDocument(TimestampMixin, Base):
    __tablename__ = "fiscal_documents"
    __table_args__ = (
        CheckConstraint(
            status_check("document_type", FISCAL_DOCUMENT_TYPES),
            name="ck_fiscal_documents_document_type",
        ),
        CheckConstraint(
            status_check("status", FISCAL_DOCUMENT_STATUSES),
            name="ck_fiscal_documents_status",
        ),
        Index("ix_fiscal_documents_company_id", "company_id"),
        Index("ix_fiscal_documents_return_note_id", "return_note_id"),
        Index("ix_fiscal_documents_status", "status"),
        Index("ix_fiscal_documents_created_at", "created_at"),
        Index("ix_fiscal_documents_access_key", "access_key"),
        Index("ix_fiscal_documents_storage_archive_id", "storage_archive_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    return_note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("return_notes.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    access_key: Mapped[str | None] = mapped_column(String(44))
    storage_archive_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_archives.id"))
    xml_storage_archive_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_archives.id"))
    pdf_storage_archive_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_archives.id"))
    issued_at: Mapped[datetime | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_company_id", "company_id"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())


class RetentionJob(TimestampMixin, Base):
    __tablename__ = "retention_jobs"
    __table_args__ = (
        CheckConstraint(status_check("status", RETENTION_JOB_STATUSES), name="ck_retention_jobs_status"),
        Index("ix_retention_jobs_company_id", "company_id"),
        Index("ix_retention_jobs_storage_archive_id", "storage_archive_id"),
        Index("ix_retention_jobs_status", "status"),
        Index("ix_retention_jobs_created_at", "created_at"),
        Index("ix_retention_jobs_scheduled_for", "scheduled_for"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    storage_archive_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("storage_archives.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    scheduled_for: Mapped[datetime | None] = mapped_column()
    processed_at: Mapped[datetime | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)

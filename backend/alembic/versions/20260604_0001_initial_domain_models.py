"""initial domain models

Revision ID: 20260604_0001
Revises:
Create Date: 2026-06-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260604_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "companies",
        uuid_pk(),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("trade_name", sa.String(length=255), nullable=True),
        sa.Column("document", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('ACTIVE', 'SUSPENDED', 'INACTIVE')", name="ck_companies_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document"),
    )
    op.create_index("ix_companies_created_at", "companies", ["created_at"])
    op.create_index("ix_companies_status", "companies", ["status"])

    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('ACTIVE', 'INVITED', 'DISABLED')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "company_users",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "role in ('OWNER', 'ADMIN', 'OPERATOR', 'VIEWER')",
            name="ck_company_users_role",
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'INVITED', 'DISABLED')",
            name="ck_company_users_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_users_company_user"),
    )
    op.create_index("ix_company_users_company_id", "company_users", ["company_id"])
    op.create_index("ix_company_users_created_at", "company_users", ["created_at"])
    op.create_index("ix_company_users_status", "company_users", ["status"])
    op.create_index("ix_company_users_user_id", "company_users", ["user_id"])

    op.create_table(
        "integrations",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "provider in ('TINY', 'MERCADO_LIVRE', 'SHOPEE')",
            name="ck_integrations_provider",
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'INVALID_TOKEN', 'EXPIRED', 'DISCONNECTED', 'ERROR')",
            name="ck_integrations_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integrations_company_id", "integrations", ["company_id"])
    op.create_index("ix_integrations_created_at", "integrations", ["created_at"])
    op.create_index("ix_integrations_status", "integrations", ["status"])

    op.create_table(
        "marketplace_accounts",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("external_account_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "marketplace in ('MERCADO_LIVRE', 'SHOPEE')",
            name="ck_marketplace_accounts_marketplace",
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'INVALID_TOKEN', 'EXPIRED', 'DISCONNECTED', 'ERROR')",
            name="ck_marketplace_accounts_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "marketplace",
            "external_account_id",
            name="uq_marketplace_accounts_company_marketplace_external",
        ),
    )
    op.create_index("ix_marketplace_accounts_company_id", "marketplace_accounts", ["company_id"])
    op.create_index("ix_marketplace_accounts_created_at", "marketplace_accounts", ["created_at"])
    op.create_index("ix_marketplace_accounts_integration_id", "marketplace_accounts", ["integration_id"])
    op.create_index("ix_marketplace_accounts_marketplace", "marketplace_accounts", ["marketplace"])
    op.create_index("ix_marketplace_accounts_status", "marketplace_accounts", ["status"])

    op.create_table(
        "return_orders",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marketplace_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("external_order_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_nfe_key", sa.String(length=44), nullable=True),
        sa.Column("customer_document", sa.String(length=32), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *timestamps(),
        sa.CheckConstraint("marketplace in ('MERCADO_LIVRE', 'SHOPEE')", name="ck_return_orders_marketplace"),
        sa.CheckConstraint(
            "status in ('OPEN', 'READY_TO_REVIEW', 'LINKED_TO_NFE', 'CANCELLED', 'ARCHIVED')",
            name="ck_return_orders_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["marketplace_account_id"], ["marketplace_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "marketplace",
            "external_order_id",
            name="uq_return_orders_company_marketplace_external_order",
        ),
    )
    op.create_index("ix_return_orders_company_id", "return_orders", ["company_id"])
    op.create_index("ix_return_orders_created_at", "return_orders", ["created_at"])
    op.create_index("ix_return_orders_external_order_id", "return_orders", ["external_order_id"])
    op.create_index("ix_return_orders_marketplace", "return_orders", ["marketplace"])
    op.create_index("ix_return_orders_marketplace_account_id", "return_orders", ["marketplace_account_id"])
    op.create_index("ix_return_orders_original_nfe_key", "return_orders", ["original_nfe_key"])
    op.create_index("ix_return_orders_status", "return_orders", ["status"])

    op.create_table(
        "return_notes",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("return_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_nfe_key", sa.String(length=44), nullable=True),
        sa.Column("return_nfe_key", sa.String(length=44), nullable=True),
        sa.Column("number", sa.String(length=32), nullable=True),
        sa.Column("series", sa.String(length=16), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status in ('DRAFT', 'READY_TO_EMIT', 'QUEUED', 'PROCESSING', 'ISSUED', 'FAILED', "
            "'CANCELLED', 'ARCHIVED', 'DELETED_BY_RETENTION')",
            name="ck_return_notes_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["return_order_id"], ["return_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_return_notes_company_id", "return_notes", ["company_id"])
    op.create_index("ix_return_notes_created_at", "return_notes", ["created_at"])
    op.create_index("ix_return_notes_original_nfe_key", "return_notes", ["original_nfe_key"])
    op.create_index("ix_return_notes_return_order_id", "return_notes", ["return_order_id"])
    op.create_index("ix_return_notes_status", "return_notes", ["status"])

    op.create_table(
        "emission_batches",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_emission_batches_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_emission_batches_company_id", "emission_batches", ["company_id"])
    op.create_index("ix_emission_batches_created_at", "emission_batches", ["created_at"])
    op.create_index("ix_emission_batches_requested_by_user_id", "emission_batches", ["requested_by_user_id"])
    op.create_index("ix_emission_batches_status", "emission_batches", ["status"])

    op.create_table(
        "emission_jobs",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("return_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status in ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'RETRYING')",
            name="ck_emission_jobs_status",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["emission_batches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["return_note_id"], ["return_notes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_emission_jobs_batch_id", "emission_jobs", ["batch_id"])
    op.create_index("ix_emission_jobs_company_id", "emission_jobs", ["company_id"])
    op.create_index("ix_emission_jobs_created_at", "emission_jobs", ["created_at"])
    op.create_index("ix_emission_jobs_return_note_id", "emission_jobs", ["return_note_id"])
    op.create_index("ix_emission_jobs_status", "emission_jobs", ["status"])

    op.create_table(
        "storage_archives",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_provider", sa.String(length=32), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("retention_until", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "storage_provider in ('S3', 'R2', 'B2', 'WASABI', 'LOCAL')",
            name="ck_storage_archives_storage_provider",
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'COLD', 'DELETED', 'ERROR')",
            name="ck_storage_archives_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storage_archives_company_id", "storage_archives", ["company_id"])
    op.create_index("ix_storage_archives_created_at", "storage_archives", ["created_at"])
    op.create_index("ix_storage_archives_retention_until", "storage_archives", ["retention_until"])
    op.create_index("ix_storage_archives_status", "storage_archives", ["status"])

    op.create_table(
        "fiscal_documents",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("return_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("access_key", sa.String(length=44), nullable=True),
        sa.Column("xml_storage_archive_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pdf_storage_archive_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "document_type in ('NFE_XML', 'DANFE_PDF', 'TINY_JSON', 'SEFAZ_EVENT')",
            name="ck_fiscal_documents_document_type",
        ),
        sa.CheckConstraint(
            "status in ('PENDING', 'AVAILABLE', 'ARCHIVED', 'DELETED', 'ERROR')",
            name="ck_fiscal_documents_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["pdf_storage_archive_id"], ["storage_archives.id"]),
        sa.ForeignKeyConstraint(["return_note_id"], ["return_notes.id"]),
        sa.ForeignKeyConstraint(["xml_storage_archive_id"], ["storage_archives.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fiscal_documents_access_key", "fiscal_documents", ["access_key"])
    op.create_index("ix_fiscal_documents_company_id", "fiscal_documents", ["company_id"])
    op.create_index("ix_fiscal_documents_created_at", "fiscal_documents", ["created_at"])
    op.create_index("ix_fiscal_documents_return_note_id", "fiscal_documents", ["return_note_id"])
    op.create_index("ix_fiscal_documents_status", "fiscal_documents", ["status"])

    op.create_table(
        "audit_logs",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_company_id", "audit_logs", ["company_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    op.create_table(
        "retention_jobs",
        uuid_pk(),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_archive_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_retention_jobs_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["storage_archive_id"], ["storage_archives.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_jobs_company_id", "retention_jobs", ["company_id"])
    op.create_index("ix_retention_jobs_created_at", "retention_jobs", ["created_at"])
    op.create_index("ix_retention_jobs_scheduled_for", "retention_jobs", ["scheduled_for"])
    op.create_index("ix_retention_jobs_status", "retention_jobs", ["status"])
    op.create_index("ix_retention_jobs_storage_archive_id", "retention_jobs", ["storage_archive_id"])


def downgrade() -> None:
    for table_name in (
        "retention_jobs",
        "audit_logs",
        "fiscal_documents",
        "storage_archives",
        "emission_jobs",
        "emission_batches",
        "return_notes",
        "return_orders",
        "marketplace_accounts",
        "integrations",
        "company_users",
        "users",
        "companies",
    ):
        op.drop_table(table_name)

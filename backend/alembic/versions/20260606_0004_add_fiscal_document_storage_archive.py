"""add generic fiscal document storage archive

Revision ID: 20260606_0004
Revises: 20260604_0003
Create Date: 2026-06-06 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260606_0004"
down_revision: str | None = "20260604_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fiscal_documents",
        sa.Column("storage_archive_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fiscal_documents_storage_archive_id_storage_archives",
        "fiscal_documents",
        "storage_archives",
        ["storage_archive_id"],
        ["id"],
    )
    op.create_index(
        "ix_fiscal_documents_storage_archive_id",
        "fiscal_documents",
        ["storage_archive_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fiscal_documents_storage_archive_id", table_name="fiscal_documents")
    op.drop_constraint(
        "fk_fiscal_documents_storage_archive_id_storage_archives",
        "fiscal_documents",
        type_="foreignkey",
    )
    op.drop_column("fiscal_documents", "storage_archive_id")

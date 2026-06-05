from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from app.db.base import Base


EXPECTED_TABLES = {
    "companies",
    "users",
    "company_users",
    "integrations",
    "marketplace_accounts",
    "return_orders",
    "return_notes",
    "emission_batches",
    "emission_jobs",
    "fiscal_documents",
    "audit_logs",
    "storage_archives",
    "retention_jobs",
}

TENANT_TABLES = EXPECTED_TABLES - {"users", "companies"}


def constraint_names(table_name: str, constraint_type: type) -> set[str | None]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, constraint_type)
    }


def index_names(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {index.name for index in table.indexes if isinstance(index, Index)}


def foreign_key_targets(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    targets: set[str] = set()
    for constraint in table.constraints:
        if isinstance(constraint, ForeignKeyConstraint):
            targets.update(element.column.table.name for element in constraint.elements)
    return targets


def test_domain_tables_are_registered_in_metadata() -> None:
    assert EXPECTED_TABLES.issubset(Base.metadata.tables.keys())


def test_operational_tables_are_tenant_scoped() -> None:
    for table_name in TENANT_TABLES:
        assert "company_id" in Base.metadata.tables[table_name].columns
        assert f"ix_{table_name}_company_id" in index_names(table_name)
        assert "companies" in foreign_key_targets(table_name)


def test_critical_unique_constraints_preserve_multi_tenant_boundaries() -> None:
    assert "uq_company_users_company_user" in constraint_names("company_users", UniqueConstraint)
    assert "uq_marketplace_accounts_company_marketplace_external" in constraint_names(
        "marketplace_accounts", UniqueConstraint
    )
    assert "uq_return_orders_company_marketplace_external_order" in constraint_names(
        "return_orders", UniqueConstraint
    )


def test_high_volume_lookup_indexes_exist() -> None:
    expected_indexes = {
        "return_orders": {
            "ix_return_orders_company_id",
            "ix_return_orders_status",
            "ix_return_orders_created_at",
            "ix_return_orders_marketplace",
            "ix_return_orders_external_order_id",
            "ix_return_orders_original_nfe_key",
        },
        "return_notes": {
            "ix_return_notes_company_id",
            "ix_return_notes_status",
            "ix_return_notes_created_at",
            "ix_return_notes_original_nfe_key",
        },
        "emission_jobs": {
            "ix_emission_jobs_company_id",
            "ix_emission_jobs_status",
            "ix_emission_jobs_created_at",
        },
        "fiscal_documents": {
            "ix_fiscal_documents_company_id",
            "ix_fiscal_documents_status",
            "ix_fiscal_documents_created_at",
            "ix_fiscal_documents_access_key",
        },
        "audit_logs": {
            "ix_audit_logs_company_id",
            "ix_audit_logs_created_at",
            "ix_audit_logs_entity",
        },
    }

    for table_name, names in expected_indexes.items():
        assert names.issubset(index_names(table_name))


def test_integration_credentials_are_stored_separately_from_settings() -> None:
    integration_columns = Base.metadata.tables["integrations"].columns

    assert "settings" in integration_columns
    assert "encrypted_credentials" in integration_columns


def test_status_fields_are_guarded_by_check_constraints() -> None:
    guarded_tables = EXPECTED_TABLES - {"audit_logs"}

    for table_name in guarded_tables:
        checks = constraint_names(table_name, CheckConstraint)
        assert any(name is not None and name.startswith(f"ck_{table_name}") for name in checks)


def test_required_relationships_are_explicit_foreign_keys() -> None:
    expected_targets = {
        "return_notes": {"companies", "return_orders"},
        "emission_jobs": {"companies", "emission_batches", "return_notes"},
        "fiscal_documents": {"companies", "return_notes", "storage_archives"},
        "retention_jobs": {"companies", "storage_archives"},
    }

    for table_name, targets in expected_targets.items():
        assert targets.issubset(foreign_key_targets(table_name))

import importlib.util
import io
from datetime import date, datetime, timezone

import pytest

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, insert, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from migration_profile_env import _authorize_verified_connection
from migration_legacy_schema import (
    LEGACY_SCHEMA,
    LegacySchemaError,
    validate_legacy_schema,
)
from migration_runner import PROFILE_DIR, _profile_config
from server import db


def test_fresh_profile_builds_current_schema_on_in_memory_sqlite():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            config = _profile_config("fresh")
            _authorize_verified_connection(
                config,
                connection=connection,
                profile="fresh",
                url_database="isolated_sqlite_fresh_test",
                confirmed_database="isolated_sqlite_fresh_test",
                verified_database="isolated_sqlite_fresh_test",
            )

            command.upgrade(config, "head")

            inspector = inspect(connection)
            actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
            assert actual_tables == set(db.metadata.tables)
            migration_context = MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            assert migration_context.get_current_revision() == "fresh_20261102_01"
            assert compare_metadata(migration_context, db.metadata) == []

            for table_name, model_table in db.metadata.tables.items():
                actual_columns = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                assert actual_columns == set(model_table.columns.keys())

                actual_primary_key = inspector.get_pk_constraint(table_name)
                expected_primary_key = [
                    column.name for column in model_table.primary_key.columns
                ]
                assert actual_primary_key["constrained_columns"] == expected_primary_key

                actual_foreign_keys = {
                    (
                        tuple(foreign_key["constrained_columns"]),
                        foreign_key["referred_table"],
                        tuple(foreign_key["referred_columns"]),
                    )
                    for foreign_key in inspector.get_foreign_keys(table_name)
                }
                expected_foreign_keys = {
                    (
                        tuple(foreign_key.parent.name for foreign_key in constraint.elements),
                        constraint.elements[0].column.table.name,
                        tuple(foreign_key.column.name for foreign_key in constraint.elements),
                    )
                    for constraint in model_table.foreign_key_constraints
                }
                assert actual_foreign_keys == expected_foreign_keys

                actual_index_names = {
                    index["name"] for index in inspector.get_indexes(table_name)
                }
                expected_index_names = {
                    index.name
                    for index in model_table.indexes
                    if index.name is not None
                }
                assert actual_index_names == expected_index_names
    finally:
        engine.dispose()


def test_fresh_revision_is_independent_and_has_one_head():
    config = _profile_config("fresh")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["fresh_20261102_01"]
    revision_ids = {revision.revision for revision in script.walk_revisions()}
    assert "179ec90c3365" not in revision_ids


def test_fresh_model_ddl_compiles_for_postgresql():
    dialect = postgresql.dialect()
    for table in db.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=dialect))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=dialect))


def test_fresh_migration_compiles_postgresql_ddl_without_connecting():
    migration_path = (
        PROFILE_DIR
        / "fresh"
        / "versions"
        / "fresh_20261102_01_initial_schema.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fresh_baseline_postgresql_compile", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    output = io.StringIO()
    migration_context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(migration_context):
        migration.upgrade()

    ddl = output.getvalue()
    assert "CREATE TABLE users" in ddl
    assert "CREATE TABLE applications" in ddl
    assert "CREATE TABLE payments" in ddl


def test_legacy_profile_has_an_independent_adoption_chain():
    config = _profile_config("legacy")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["legacy_20261102_02"]
    revisions = {
        revision.revision: revision.down_revision
        for revision in script.walk_revisions()
    }
    assert revisions == {
        "legacy_20261102_02": "legacy_20261102_01",
        "legacy_20261102_01": None,
    }
    assert "179ec90c3365" not in revisions


def test_legacy_fingerprint_accepts_duplicate_approved_rows_and_nullable_tenants():
    engine = create_engine("sqlite:///:memory:")
    try:
        created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        with engine.begin() as connection:
            LEGACY_SCHEMA.create_all(connection)
            connection.execute(
                insert(LEGACY_SCHEMA.tables["users"]),
                {
                    "id": 1,
                    "name": "Legacy landlord",
                    "email": "legacy@example.test",
                    "password_hash": "preserved-hash",
                    "role": "landlord",
                    "created_at": created_at,
                },
            )
            connection.execute(
                insert(LEGACY_SCHEMA.tables["properties"]),
                {
                    "id": 1,
                    "owner_id": 1,
                    "name": "Legacy property",
                    "address": "Old address",
                    "city": "Nairobi",
                    "state": "Nairobi County",
                    "zip_code": "00100",
                    "created_at": created_at,
                },
            )
            connection.execute(
                insert(LEGACY_SCHEMA.tables["units"]),
                {
                    "id": 1,
                    "property_id": 1,
                    "unit_number": "A1",
                    "created_at": created_at,
                },
            )
            connection.execute(
                insert(LEGACY_SCHEMA.tables["tenants"]),
                {
                    "id": 1,
                    "landlord_id": 1,
                    "user_id": None,
                    "name": "Legacy tenant",
                    "email": "tenant@example.test",
                    "created_at": created_at,
                },
            )
            connection.execute(
                insert(LEGACY_SCHEMA.tables["applications"]),
                [
                    {
                        "id": 1,
                        "unit_id": 1,
                        "applicant_user_id": 1,
                        "move_in_date": date(2026, 11, 1),
                        "status": "approved",
                        "created_at": created_at,
                    },
                    {
                        "id": 2,
                        "unit_id": 1,
                        "applicant_user_id": 1,
                        "move_in_date": date(2026, 11, 2),
                        "status": "approved",
                        "created_at": created_at.replace(day=2),
                    },
                ],
            )
            validate_legacy_schema(connection)

            assert connection.execute(
                text("SELECT user_id FROM tenants WHERE id = 1")
            ).scalar_one() is None
            assert connection.execute(
                text("SELECT count(*) FROM applications WHERE unit_id = 1 AND status = 'approved'")
            ).scalar_one() == 2
    finally:
        engine.dispose()


def test_legacy_fingerprint_rejects_an_extra_table():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            LEGACY_SCHEMA.create_all(connection)
            connection.exec_driver_sql("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
            with pytest.raises(LegacySchemaError, match="exactly the seven"):
                validate_legacy_schema(connection)
    finally:
        engine.dispose()

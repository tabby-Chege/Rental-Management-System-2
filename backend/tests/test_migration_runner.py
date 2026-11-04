import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from migration_legacy_schema import LegacySchemaError
import migration_runner
import migration_profile_env


class FakeConnection:
    def __init__(
        self,
        identity,
        version_table="public.alembic_version",
        applied_revisions=None,
        schema_tables=None,
        schema_columns=None,
        schema_sequences=None,
    ):
        self.identity = identity
        self.dialect = postgresql.dialect()
        self.version_table = version_table
        self.applied_revisions = (
            ["abc123"] if applied_revisions is None else applied_revisions
        )
        self.schema_tables = schema_tables if schema_tables is not None else {
            "users",
            "properties",
            "units",
            "tenants",
            "applications",
            "leases",
            "payments",
        }
        self.schema_columns = schema_columns if schema_columns is not None else {
            ("users", "id"),
            ("users", "email"),
            ("properties", "id"),
            ("properties", "owner_id"),
            ("units", "id"),
            ("units", "property_id"),
            ("tenants", "id"),
            ("tenants", "landlord_id"),
            ("applications", "id"),
            ("applications", "unit_id"),
            ("applications", "status"),
            ("leases", "id"),
            ("leases", "unit_id"),
            ("leases", "tenant_id"),
            ("payments", "id"),
            ("payments", "lease_id"),
        }
        self.schema_sequences = schema_sequences if schema_sequences is not None else set()
        self.queries = []
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def exec_driver_sql(self, statement):
        self.queries.append(statement)
        if statement.startswith("SELECT current_database"):
            return SimpleNamespace(one=lambda: self.identity)
        if statement.startswith("SELECT to_regclass"):
            return SimpleNamespace(scalar_one=lambda: self.version_table)
        if statement.startswith("SELECT version_num"):
            return SimpleNamespace(
                all=lambda: [(revision,) for revision in self.applied_revisions]
            )
        if statement.startswith("SELECT table_name, column_name"):
            return SimpleNamespace(all=lambda: list(self.schema_columns))
        if statement.startswith("SELECT table_name"):
            return SimpleNamespace(all=lambda: [(table,) for table in self.schema_tables])
        if statement.startswith("SELECT sequence_name"):
            return SimpleNamespace(
                all=lambda: [(sequence,) for sequence in self.schema_sequences]
            )
        return SimpleNamespace()

    def in_transaction(self):
        return False

    def rollback(self):
        self.rollback_count += 1


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self):
        self.disposed = True


class FakeScript:
    def __init__(self, heads, revisions=None):
        self.heads = heads
        self.revisions = revisions or heads

    def get_heads(self):
        return self.heads

    def get_revision(self, revision):
        return SimpleNamespace(revision=revision) if revision == "abc123" else None

    def walk_revisions(self):
        return [SimpleNamespace(revision=revision) for revision in self.revisions]


def test_invalid_profile_is_rejected_before_database_connection(monkeypatch):
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("database connection must not open"),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="exactly one"):
        migration_runner.run_upgrade(
            profile="automatic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )


def test_repeated_profile_selection_is_rejected():
    with pytest.raises(SystemExit):
        migration_runner._build_parser().parse_args(
            [
                "--profile",
                "fresh",
                "--profile",
                "legacy",
                "--confirm-database",
                "isolated_db",
                "upgrade",
            ]
        )


def test_protected_database_is_rejected_before_database_connection(monkeypatch):
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("protected target must not connect"),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="protected"):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="rental_management",
            database_url="postgresql://localhost/rental_management",
        )


def test_legacy_profile_rejects_an_unrecognized_unversioned_schema(
    monkeypatch,
):
    connection = FakeConnection(
        ("isolated_db", "127.0.0.1", 5432),
        version_table=None,
    )
    engine = FakeEngine(connection)
    upgrades = []
    monkeypatch.setattr(
        migration_runner,
        "ScriptDirectory",
        SimpleNamespace(from_config=lambda _config: FakeScript(["legacy_head"])),
    )
    monkeypatch.setattr(migration_runner, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(
        migration_runner,
        "validate_legacy_schema",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(LegacySchemaError()),
    )
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda *_args, **_kwargs: upgrades.append(True),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="starting fingerprint"):
        migration_runner.run_upgrade(
            profile="legacy",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )

    assert upgrades == []
    assert connection.rollback_count == 1
    assert engine.disposed


def test_legacy_unversioned_database_runs_only_after_fingerprint_validation(
    monkeypatch,
):
    connection = FakeConnection(
        ("isolated_db", "127.0.0.1", 5432),
        version_table=None,
    )
    engine = FakeEngine(connection)
    verified = []
    invoked = []
    revisions = ["legacy_20261102_01", "legacy_20261102_02"]
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["legacy_20261102_02"], revisions),
    )
    monkeypatch.setattr(migration_runner, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(
        migration_runner,
        "validate_legacy_schema",
        lambda candidate: verified.append(candidate),
    )

    def upgrade(config, revision):
        invoked.append((config.attributes["connection"], revision))

    monkeypatch.setattr(migration_runner.command, "upgrade", upgrade)
    migration_runner.run_upgrade(
        profile="legacy",
        confirmation="isolated_db",
        database_url="postgresql://localhost/isolated_db",
    )

    assert verified == [connection]
    assert invoked == [(connection, "head")]
    assert connection.rollback_count == 1
    assert engine.disposed

def test_fresh_profile_allows_only_an_empty_unversioned_baseline(monkeypatch):
    connection = FakeConnection(
        ("isolated_db", "127.0.0.1", 5432),
        version_table=None,
        schema_tables=set(),
        schema_columns=set(),
        schema_sequences=set(),
    )
    identity = migration_runner._verify_connection(
        connection,
        "fresh",
        "isolated_db",
        "isolated_db",
        {"fresh_20261102_01"},
    )
    assert identity == ("isolated_db", "127.0.0.1", 5432)
    assert connection.rollback_count == 1


def test_fresh_profile_rejects_schema_drift_against_model_metadata(monkeypatch):
    from server import db

    connection = FakeConnection(("isolated_db", "127.0.0.1", 5432))
    connection.schema_tables = set(db.metadata.tables)
    connection.schema_columns = {
        (table.name, column.name)
        for table in db.metadata.tables.values()
        for column in table.columns
    }
    monkeypatch.setattr(
        migration_runner,
        "compare_metadata",
        lambda *_args, **_kwargs: [("remove_constraint", "unexpected drift")],
    )
    with pytest.raises(migration_runner.MigrationSafetyError, match="differs"):
        migration_runner._verify_connection(
            connection,
            "fresh",
            "isolated_db",
            "isolated_db",
            {"abc123"},
        )
    assert connection.rollback_count == 1


@pytest.mark.parametrize(
    "schema_tables, schema_columns, schema_sequences",
    [
        ({"leftover"}, set(), set()),
        (set(), {("orphaned", "id")}, set()),
        (set(), set(), {"leftover_id_seq"}),
    ],
)
def test_fresh_profile_rejects_nonempty_unversioned_schema(
    schema_tables, schema_columns, schema_sequences
):
    connection = FakeConnection(
        ("isolated_db", "127.0.0.1", 5432),
        version_table=None,
        schema_tables=schema_tables,
        schema_columns=schema_columns,
        schema_sequences=schema_sequences,
    )
    with pytest.raises(migration_runner.MigrationSafetyError, match="empty schema"):
        migration_runner._verify_connection(
            connection,
            "fresh",
            "isolated_db",
            "isolated_db",
            {"fresh_20261102_01"},
        )
    assert connection.rollback_count == 1


def test_ambiguous_revision_graph_is_rejected_before_connection(monkeypatch):
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["head_a", "head_b"]),
    )
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("ambiguous profile must not connect"),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="exactly one"):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )


@pytest.mark.parametrize("revision", ["heads", "abc123,def456"])
def test_multiple_head_targets_are_rejected_before_connection(monkeypatch, revision):
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"]),
    )
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("multiple-head target must not connect"),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="Multiple-head"):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            revision=revision,
            database_url="postgresql://localhost/isolated_db",
        )


def test_connected_protected_database_is_rejected_before_upgrade(monkeypatch):
    connection = FakeConnection(("rental_management", "127.0.0.1", 5432))
    engine = FakeEngine(connection)
    upgrades = []
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"]),
    )
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: engine,
    )
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda *_args, **_kwargs: upgrades.append(True),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="protected"):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )

    assert upgrades == []
    assert connection.queries[0] == "SET TRANSACTION READ ONLY"
    assert connection.rollback_count == 1
    assert engine.disposed


@pytest.mark.parametrize(
    "applied_revisions, message",
    [
        (["abc123", "def456"], "multiple applied migration heads"),
        (["other_profile_revision"], "does not belong to the selected profile"),
    ],
)
def test_ambiguous_or_foreign_database_revision_is_rejected(
    monkeypatch, applied_revisions, message
):
    class VersionedConnection(FakeConnection):
        def exec_driver_sql(self, statement):
            self.queries.append(statement)
            if statement.startswith("SELECT current_database"):
                return SimpleNamespace(one=lambda: self.identity)
            if statement.startswith("SELECT to_regclass"):
                return SimpleNamespace(
                    scalar_one=lambda: "public.alembic_version"
                )
            if statement.startswith("SELECT version_num"):
                return SimpleNamespace(
                    all=lambda: [(revision,) for revision in applied_revisions]
                )
            return SimpleNamespace()

    connection = VersionedConnection(("isolated_db", "127.0.0.1", 5432))
    engine = FakeEngine(connection)
    upgrades = []
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"], ["abc123"]),
    )
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: engine,
    )
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda *_args, **_kwargs: upgrades.append(True),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match=message):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )

    assert upgrades == []
    assert connection.rollback_count == 1


@pytest.mark.parametrize(
    "version_table, applied_revisions, message",
    [
        (None, [], "unversioned"),
        ("public.alembic_version", [], "version table is empty"),
        ("public.alembic_version", ["not_a_revision"], "does not belong"),
        ("public.alembic_version", ["abc123", "def456"], "multiple applied"),
    ],
)
def test_unsafe_version_states_are_rejected_before_upgrade(
    monkeypatch, version_table, applied_revisions, message
):
    connection = FakeConnection(
        ("isolated_db", "127.0.0.1", 5432),
        version_table=version_table,
        applied_revisions=applied_revisions,
    )
    engine = FakeEngine(connection)
    upgrades = []
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"], ["abc123"]),
    )
    monkeypatch.setattr(migration_runner, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda *_args, **_kwargs: upgrades.append(True),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match=message):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )

    assert upgrades == []
    assert connection.rollback_count == 1
    assert engine.disposed


def test_schema_preflight_failure_is_rejected_before_upgrade(monkeypatch):
    connection = FakeConnection(
        ("isolated_db", "127.0.0.1", 5432),
        schema_tables={"users"},
        schema_columns={("users", "id"), ("users", "email")},
    )
    engine = FakeEngine(connection)
    upgrades = []
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"], ["abc123"]),
    )
    monkeypatch.setattr(migration_runner, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda *_args, **_kwargs: upgrades.append(True),
    )

    with pytest.raises(
        migration_runner.MigrationSafetyError, match="schema preflight failed"
    ):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )

    assert upgrades == []
    assert connection.rollback_count == 1


def test_wrong_database_confirmation_is_rejected_before_connection(monkeypatch):
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("database connection must not open"),
    )
    with pytest.raises(migration_runner.MigrationSafetyError, match="confirmation"):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="another_db",
            database_url="postgresql://localhost/isolated_db",
        )


def test_url_and_live_database_mismatch_is_rejected_before_upgrade(monkeypatch):
    connection = FakeConnection(("other_db", "127.0.0.1", 5432))
    engine = FakeEngine(connection)
    upgrades = []
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"]),
    )
    monkeypatch.setattr(migration_runner, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda *_args, **_kwargs: upgrades.append(True),
    )

    with pytest.raises(migration_runner.MigrationSafetyError, match="does not match"):
        migration_runner.run_upgrade(
            profile="historic",
            confirmation="isolated_db",
            database_url="postgresql://localhost/isolated_db",
        )

    assert upgrades == []
    assert connection.rollback_count == 1
    assert engine.disposed


def test_confirmed_identity_runs_only_selected_profile_on_verified_connection(
    monkeypatch,
):
    connection = FakeConnection(("isolated_db", "127.0.0.1", 5432))
    engine = FakeEngine(connection)
    invoked = []
    monkeypatch.setattr(
        migration_runner.ScriptDirectory,
        "from_config",
        lambda _config: FakeScript(["abc123"]),
    )
    monkeypatch.setattr(
        migration_runner,
        "create_engine",
        lambda *_args, **_kwargs: engine,
    )

    def upgrade(config, revision):
        attributes = config.attributes
        invoked.append(
            (
                attributes["connection"],
                revision,
                attributes["migration_profile"],
                attributes["migration_url_database"],
                attributes["migration_confirmed_database"],
                attributes["migration_verified_database"],
                attributes["rental_migration_runner_authorization"],
            )
        )

    monkeypatch.setattr(migration_runner.command, "upgrade", upgrade)

    identity = migration_runner.run_upgrade(
        profile="historic",
        confirmation="isolated_db",
        database_url="postgresql://localhost/isolated_db",
    )

    assert identity == ("isolated_db", "127.0.0.1", 5432)
    assert invoked[0][:6] == (
        connection,
        "head",
        "historic",
        "isolated_db",
        "isolated_db",
        "isolated_db",
    )
    assert invoked[0][6] is not None
    assert connection.rollback_count == 1
    assert engine.disposed


def test_flask_migrate_environment_rejects_unverified_execution():
    config = SimpleNamespace(attributes={})
    with pytest.raises(RuntimeError, match="approved migration runner"):
        migration_profile_env.require_runner_authorization(config, "historic")


def test_original_flask_migrate_alembic_environment_rejects_bypass(monkeypatch):
    monkeypatch.setattr(
        migration_profile_env.context,
        "config",
        SimpleNamespace(attributes={}),
        raising=False,
    )
    historic_environment = (
        Path(migration_runner.BACKEND_DIR) / "migrations" / "alembic" / "env.py"
    )
    with pytest.raises(RuntimeError, match="approved migration runner"):
        runpy.run_path(str(historic_environment))


def test_profile_environment_refuses_unverified_connection(monkeypatch):
    monkeypatch.setattr(
        migration_profile_env.context,
        "config",
        SimpleNamespace(attributes={"connection": FakeConnection(("isolated_db", None, None))}),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="approved migration runner"):
        migration_profile_env.run_migrations("historic")


def test_importing_runner_has_no_database_side_effects():
    backend_dir = Path(migration_runner.__file__).resolve().parent
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("SQLALCHEMY_DATABASE_URI", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sqlalchemy; "
            "sqlalchemy.create_engine = lambda *a, **k: (_ for _ in ()).throw("
            "AssertionError('engine creation during import')); "
            "import migration_runner",
        ],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

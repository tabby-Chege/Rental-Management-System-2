"""Explicit, safety-gated entry point for the three Alembic profiles."""

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from migration_legacy_schema import LegacySchemaError, validate_legacy_schema
from migration_profile_env import _authorize_verified_connection


BACKEND_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BACKEND_DIR / "migrations" / "profiles"
HISTORIC_VERSIONS = BACKEND_DIR / "migrations" / "alembic" / "versions"
PROFILES = frozenset({"historic", "fresh", "legacy"})
PROTECTED_DATABASE_NAMES = frozenset({"rental_management"})
PROFILE_PREFLIGHT_REQUIREMENTS = {
    "historic": {
        "users": {"id", "email"},
        "properties": {"id", "owner_id"},
        "units": {"id", "property_id"},
        "tenants": {"id", "landlord_id"},
        "applications": {"id", "unit_id", "status"},
        "leases": {"id", "unit_id", "tenant_id"},
        "payments": {"id", "lease_id"},
    }
}


class MigrationSafetyError(Exception):
    """Raised when a migration request cannot be proven safe to run."""


def _profile_config(profile: str) -> Config:
    if profile not in PROFILES:
        raise MigrationSafetyError(
            "Choose exactly one migration profile: historic, fresh, or legacy."
        )

    profile_directory = PROFILE_DIR / profile
    version_directory = (
        HISTORIC_VERSIONS
        if profile == "historic"
        else profile_directory / "versions"
    )
    if not (profile_directory / "env.py").is_file():
        raise MigrationSafetyError(f"The {profile} profile is not configured.")
    if not version_directory.is_dir():
        raise MigrationSafetyError(f"The {profile} profile has no versions directory.")

    config = Config()
    config.set_main_option("script_location", str(profile_directory).replace("%", "%%"))
    config.set_main_option("version_locations", str(version_directory).replace("%", "%%"))
    config.set_main_option("path_separator", "os")
    return config


def _validate_revision(script: ScriptDirectory, revision: str) -> None:
    heads = script.get_heads()
    if len(heads) != 1:
        raise MigrationSafetyError(
            "The selected profile must have exactly one migration head; "
            f"found {len(heads)}. No database connection was opened."
        )
    if revision == "heads" or "," in revision:
        raise MigrationSafetyError(
            "Multiple-head upgrades are disabled; choose one profile and one revision."
        )
    if revision != "head":
        try:
            known_revision = script.get_revision(revision)
        except CommandError:
            known_revision = None
        if known_revision is None:
            raise MigrationSafetyError(
                f"Revision {revision!r} does not belong to the selected profile."
            )


def _known_revisions(script: ScriptDirectory) -> set[str]:
    return {revision.revision for revision in script.walk_revisions()}


def _profile_preflight_requirements(profile: str) -> dict[str, set[str]]:
    requirements = PROFILE_PREFLIGHT_REQUIREMENTS.get(profile)
    if profile in {"fresh", "legacy"}:
        from server import db

        return {
            table.name: {column.name for column in table.columns}
            for table in db.metadata.sorted_tables
        }
    if requirements is None:
        raise MigrationSafetyError(
            f"The {profile} profile has no reviewed schema preflight and is unavailable."
        )
    return requirements


def _parse_database_target(database_url: str, confirmation: str) -> tuple:
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise MigrationSafetyError(
            "The configured database URL is invalid; no migration was run."
        ) from None

    if url.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise MigrationSafetyError(
            "Migrations require an explicitly configured PostgreSQL database."
        )
    database_name = url.database
    if not database_name:
        raise MigrationSafetyError(
            "The configured database URL does not identify a database."
        )
    if database_name.casefold() in PROTECTED_DATABASE_NAMES:
        raise MigrationSafetyError(
            "The protected rental_management database is never a migration target."
        )
    if confirmation != database_name:
        raise MigrationSafetyError(
            "The confirmation name must exactly match the database in the configured URL."
        )
    return url, database_name


def _verify_connection(
    connection: Connection,
    profile: str,
    expected_database: str,
    confirmation: str,
    known_revisions: set[str],
) -> tuple:
    requirements = _profile_preflight_requirements(profile)
    try:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        actual_database, server_address, server_port = connection.exec_driver_sql(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
        ).one()
        if actual_database.casefold() in PROTECTED_DATABASE_NAMES:
            raise MigrationSafetyError(
                "The connected target is the protected rental_management database."
            )
        if actual_database != expected_database or actual_database != confirmation:
            raise MigrationSafetyError(
                "The connected database does not match the confirmed target name."
            )
        version_table_exists = connection.exec_driver_sql(
            "SELECT to_regclass('alembic_version')"
        ).scalar_one()
        fresh_baseline = profile == "fresh" and not version_table_exists
        legacy_baseline = profile == "legacy" and not version_table_exists
        if not version_table_exists:
            if not fresh_baseline and not legacy_baseline:
                raise MigrationSafetyError(
                    "The database is unversioned; it cannot be used as an upgrade target."
                )
            if legacy_baseline:
                try:
                    validate_legacy_schema(connection)
                except LegacySchemaError:
                    raise MigrationSafetyError(
                        "The unversioned Legacy schema does not match the reviewed "
                        "starting fingerprint; no migration was run."
                    ) from None
            current_revisions = []
        else:
            current_revisions = [
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version"
                ).all()
            ]
            if not current_revisions:
                raise MigrationSafetyError(
                    "The Alembic version table is empty; refusing an ambiguous database state."
                )
            if len(current_revisions) > 1:
                raise MigrationSafetyError(
                    "The database has multiple applied migration heads; no upgrade was run."
                )
            if any(revision not in known_revisions for revision in current_revisions):
                raise MigrationSafetyError(
                    "The database revision does not belong to the selected profile."
                )

        schema_tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
            ).all()
        }
        schema_columns = {
            (row[0], row[1])
            for row in connection.exec_driver_sql(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema()"
            ).all()
        }
        schema_sequences = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = current_schema()"
            ).all()
        }
        schema_differences = []
        if profile == "fresh" and not fresh_baseline:
            from server import db

            schema_differences = compare_metadata(
                MigrationContext.configure(
                    connection,
                    opts={"compare_type": True},
                ),
                db.metadata,
            )
    except MigrationSafetyError:
        raise
    except SQLAlchemyError:
        raise MigrationSafetyError(
            "Could not verify the PostgreSQL target identity and schema; "
            "no migration was run."
        ) from None
    finally:
        connection.rollback()

    missing_schema = {}
    if fresh_baseline:
        if schema_tables or schema_columns or schema_sequences:
            raise MigrationSafetyError(
                "The fresh baseline requires an empty schema with no existing "
                "tables, columns, or sequences."
            )
    elif not legacy_baseline:
        for table, required_columns in requirements.items():
            present_columns = {
                column
                for column_table, column in schema_columns
                if column_table == table
            }
            missing_columns = required_columns - present_columns
            if table not in schema_tables or missing_columns:
                missing_schema[table] = sorted(missing_columns)
    if missing_schema:
        missing_summary = ", ".join(
            f"{table} ({', '.join(columns)})" if columns else table
            for table, columns in sorted(missing_schema.items())
        )
        raise MigrationSafetyError(
            f"The {profile} schema preflight failed; missing required tables or "
            f"columns: {missing_summary}."
        )
    if schema_differences:
        raise MigrationSafetyError(
            "The fresh schema differs from current SQLAlchemy metadata; refusing "
            "to continue until the schema is reconciled."
        )
    return actual_database, server_address, server_port


class _StoreOnce(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be specified only once")
        setattr(namespace, self.dest, values)


def run_upgrade(
    profile: str,
    confirmation: str,
    revision: str = "head",
    database_url: str | None = None,
) -> tuple:
    config = _profile_config(profile)
    _profile_preflight_requirements(profile)
    script = ScriptDirectory.from_config(config)
    _validate_revision(script, revision)
    known_revisions = _known_revisions(script)

    if database_url is None:
        database_url = (
            os.environ.get("SQLALCHEMY_DATABASE_URI")
            or os.environ.get("DATABASE_URL")
        )
    if not database_url:
        raise MigrationSafetyError(
            "Set SQLALCHEMY_DATABASE_URI or DATABASE_URL before running migrations."
        )

    url, expected_database = _parse_database_target(database_url, confirmation)
    config.set_main_option(
        "sqlalchemy.url",
        url.render_as_string(hide_password=False).replace("%", "%%"),
    )

    engine: Engine | None = None
    try:
        engine = create_engine(url)
        with engine.connect() as connection:
            identity = _verify_connection(
                connection,
                profile,
                expected_database,
                confirmation,
                known_revisions,
            )
            _authorize_verified_connection(
                config,
                connection=connection,
                profile=profile,
                url_database=expected_database,
                confirmed_database=confirmation,
                verified_database=identity[0],
            )
            command.upgrade(config, revision)
            return identity
    except SQLAlchemyError:
        raise MigrationSafetyError(
            "Could not connect to or migrate the verified PostgreSQL target."
        ) from None
    finally:
        if engine is not None:
            engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one explicitly selected, safety-checked migration profile."
    )
    parser.add_argument(
        "--profile",
        required=True,
        action=_StoreOnce,
        choices=sorted(PROFILES),
        help="Required migration track; profiles are never selected automatically.",
    )
    parser.add_argument(
        "--confirm-database",
        required=True,
        action=_StoreOnce,
        help="Exact database name to confirm after read-only server verification.",
    )
    parser.add_argument("action", choices=("upgrade",))
    parser.add_argument("revision", nargs="?", default="head")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(BACKEND_DIR / ".env")
    args = _build_parser().parse_args(argv)
    try:
        database_name, server_address, server_port = run_upgrade(
            profile=args.profile,
            confirmation=args.confirm_database,
            revision=args.revision,
        )
    except MigrationSafetyError as exc:
        print(f"Migration refused: {exc}", file=sys.stderr)
        return 2

    location = (
        f"{server_address}:{server_port}"
        if server_address is not None
        else f"local socket:{server_port}"
    )
    print(
        f"Upgrade complete: profile={args.profile}, "
        f"database={database_name}, server={location}, revision={args.revision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

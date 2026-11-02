"""Shared Alembic environment used only by the safety-gated migration runner."""

from alembic import context


_RUNNER_AUTHORIZATION = object()
_AUTHORIZATION_ATTRIBUTE = "rental_migration_runner_authorization"


def _authorize_verified_connection(
    config,
    *,
    connection,
    profile: str,
    url_database: str,
    confirmed_database: str,
    verified_database: str,
) -> None:
    if (
        connection is None
        or profile not in {"historic", "fresh", "legacy"}
        or not url_database
        or url_database != confirmed_database
        or confirmed_database != verified_database
    ):
        raise RuntimeError("The migration connection has not passed identity verification.")

    config.attributes.update(
        {
            _AUTHORIZATION_ATTRIBUTE: _RUNNER_AUTHORIZATION,
            "connection": connection,
            "migration_profile": profile,
            "migration_url_database": url_database,
            "migration_confirmed_database": confirmed_database,
            "migration_verified_database": verified_database,
        }
    )


def require_runner_authorization(config, expected_profile: str):
    attributes = config.attributes
    connection = attributes.get("connection")
    if (
        attributes.get(_AUTHORIZATION_ATTRIBUTE) is not _RUNNER_AUTHORIZATION
        or connection is None
        or attributes.get("migration_profile") != expected_profile
        or attributes.get("migration_url_database")
        != attributes.get("migration_confirmed_database")
        or attributes.get("migration_confirmed_database")
        != attributes.get("migration_verified_database")
    ):
        raise RuntimeError(
            "Run migrations through the approved migration runner with a verified "
            "connection, explicit profile, and database confirmation."
        )
    return connection


def run_migrations(expected_profile: str) -> None:
    config = context.config
    connection = require_runner_authorization(config, expected_profile)
    from server import db

    context.configure(
        connection=connection,
        target_metadata=db.metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

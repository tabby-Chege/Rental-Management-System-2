"""Adopt the reviewed seven-table Legacy schema without changing its rows."""

from alembic import op

from migration_legacy_schema import validate_legacy_schema


revision = "legacy_20261102_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    validate_legacy_schema(op.get_bind(), allow_alembic_version=True)


def downgrade():
    raise RuntimeError(
        "Legacy adoption is intentionally not reversible. Restore a verified "
        "backup rather than removing migration history from an existing database."
    )

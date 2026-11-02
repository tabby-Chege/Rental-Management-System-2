"""Fingerprint and validate the reviewed unversioned Legacy schema."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
    text,
)


LEGACY_TABLES = frozenset(
    {"applications", "leases", "payments", "properties", "tenants", "units", "users"}
)
LEGACY_SEQUENCES = frozenset(f"{table}_id_seq" for table in LEGACY_TABLES)

LEGACY_SCHEMA = MetaData()

users = Table(
    "users",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("name", String(120), nullable=False),
    Column("email", String(120), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("id", name="users_pkey"),
)
Index("ix_users_email", users.c.email, unique=True)

properties = Table(
    "properties",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("owner_id", Integer, nullable=False),
    Column("name", String(120), nullable=False),
    Column("address", String(255), nullable=False),
    Column("city", String(100), nullable=False),
    Column("state", String(100), nullable=False),
    Column("zip_code", String(20)),
    Column("description", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["owner_id"], ["users.id"], name="properties_owner_id_fkey"
    ),
    PrimaryKeyConstraint("id", name="properties_pkey"),
)
Index("ix_properties_owner_id", properties.c.owner_id)

tenants = Table(
    "tenants",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("landlord_id", Integer, nullable=False),
    Column("user_id", Integer, nullable=True),
    Column("name", String(120), nullable=False),
    Column("email", String(120), nullable=False),
    Column("phone", String(30)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["landlord_id"], ["users.id"], name="tenants_landlord_id_fkey"
    ),
    ForeignKeyConstraint(["user_id"], ["users.id"], name="tenants_user_id_fkey"),
    PrimaryKeyConstraint("id", name="tenants_pkey"),
    UniqueConstraint("user_id", name="tenants_user_id_key"),
    UniqueConstraint("landlord_id", "email", name="uq_tenant_landlord_email"),
)
Index("ix_tenants_landlord_id", tenants.c.landlord_id)

units = Table(
    "units",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("property_id", Integer, nullable=False),
    Column("unit_number", String(50), nullable=False),
    Column("unit_type", String(50)),
    Column("bedrooms", Integer),
    Column("bathrooms", Numeric(3, 1)),
    Column("rent_amount", Numeric(10, 2)),
    Column("description", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["property_id"], ["properties.id"], name="units_property_id_fkey"
    ),
    PrimaryKeyConstraint("id", name="units_pkey"),
    UniqueConstraint(
        "property_id", "unit_number", name="uq_units_property_unit_number"
    ),
)
Index("ix_units_property_id", units.c.property_id)

applications = Table(
    "applications",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("unit_id", Integer, nullable=False),
    Column("applicant_user_id", Integer, nullable=False),
    Column("tenant_id", Integer),
    Column("message", Text),
    Column("move_in_date", Date, nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'approved', 'declined')",
        name="ck_applications_status",
    ),
    ForeignKeyConstraint(
        ["applicant_user_id"],
        ["users.id"],
        name="applications_applicant_user_id_fkey",
    ),
    ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name="applications_tenant_id_fkey"
    ),
    ForeignKeyConstraint(
        ["unit_id"], ["units.id"], name="applications_unit_id_fkey"
    ),
    PrimaryKeyConstraint("id", name="applications_pkey"),
)
Index("ix_applications_applicant_user_id", applications.c.applicant_user_id)
Index("ix_applications_tenant_id", applications.c.tenant_id)
Index("ix_applications_unit_id", applications.c.unit_id)

leases = Table(
    "leases",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("unit_id", Integer, nullable=False),
    Column("tenant_id", Integer, nullable=False),
    Column("start_date", Date, nullable=False),
    Column("end_date", Date, nullable=False),
    Column("monthly_rent", Numeric(10, 2), nullable=False),
    Column("deposit", Numeric(10, 2), nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("end_date >= start_date", name="ck_leases_dates"),
    CheckConstraint(
        "status IN ('active', 'ended', 'terminated')", name="ck_leases_status"
    ),
    ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name="leases_tenant_id_fkey"
    ),
    ForeignKeyConstraint(["unit_id"], ["units.id"], name="leases_unit_id_fkey"),
    PrimaryKeyConstraint("id", name="leases_pkey"),
)
Index("ix_leases_tenant_id", leases.c.tenant_id)
Index("ix_leases_unit_id", leases.c.unit_id)

payments = Table(
    "payments",
    LEGACY_SCHEMA,
    Column("id", Integer, nullable=False),
    Column("lease_id", Integer, nullable=False),
    Column("amount", Float, nullable=False),
    Column("payment_date", DateTime(timezone=True), nullable=False),
    Column("payment_method", String(50), nullable=False),
    Column("status", String(20), nullable=False),
    Column("reference_code", String(100)),
    ForeignKeyConstraint(
        ["lease_id"], ["leases.id"], name="payments_lease_id_fkey"
    ),
    PrimaryKeyConstraint("id", name="payments_pkey"),
    UniqueConstraint("reference_code", name="payments_reference_code_key"),
)


class LegacySchemaError(RuntimeError):
    """Raised when an unversioned database is not the reviewed Legacy schema."""


def validate_legacy_schema(connection, allow_alembic_version=False):
    inspector = inspect(connection)
    schema = "public" if connection.dialect.name == "postgresql" else None
    tables = set(inspector.get_table_names(schema=schema))
    views = set(inspector.get_view_names(schema=schema))
    if allow_alembic_version:
        tables.discard("alembic_version")

    if tables != LEGACY_TABLES or views:
        raise LegacySchemaError(
            "The unversioned Legacy target must contain exactly the seven reviewed "
            "base tables and no views."
        )

    differences = compare_metadata(
        MigrationContext.configure(
            connection,
            opts={"compare_type": True},
        ),
        LEGACY_SCHEMA,
    )
    if differences:
        raise LegacySchemaError(
            "The unversioned Legacy target differs from the reviewed table, column, "
            "constraint, foreign-key, or index signature."
        )

    if connection.dialect.name != "postgresql":
        return

    sequences = set(
        connection.execute(
            text(
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = 'public'"
            )
        ).scalars()
    )
    if sequences != LEGACY_SEQUENCES:
        raise LegacySchemaError(
            "The unversioned Legacy target has unexpected or missing ID sequences."
        )

    for table_name in sorted(LEGACY_TABLES):
        sequence_name = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
            {"table_name": f"public.{table_name}"},
        ).scalar_one()
        if sequence_name != f"public.{table_name}_id_seq":
            raise LegacySchemaError(
                "A Legacy ID column is not owned by its reviewed sequence."
            )

    unvalidated_constraints = connection.execute(
        text(
            "SELECT con.conname FROM pg_constraint AS con "
            "JOIN pg_class AS rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace AS ns ON ns.oid = rel.relnamespace "
            "WHERE ns.nspname = 'public' AND NOT con.convalidated"
        )
    ).scalars().all()
    if unvalidated_constraints:
        raise LegacySchemaError(
            "The unversioned Legacy target contains unvalidated constraints."
        )

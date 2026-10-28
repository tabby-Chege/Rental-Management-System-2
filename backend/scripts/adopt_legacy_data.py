"""Safely copy legacy rental data into a migrated test database.

This script never connects to the original rental_management database.
It refuses to write if the destination already contains core records.
"""
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SOURCE_URL = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
TARGET_NAME = "rental_management_clean_migration_check_20261027"

if not SOURCE_URL:
    sys.exit("STOP: DATABASE_URL is not configured.")

source_url = make_url(SOURCE_URL)
source_name = source_url.database

if source_name != "rental_management_migration_test2":
    sys.exit(
        "STOP: expected the restored test database "
        "'rental_management_migration_test2'. No data was copied."
    )

if source_name == TARGET_NAME:
    sys.exit("STOP: source and destination must be different databases.")

target_url = source_url.set(database=TARGET_NAME)

TABLES = [
    "users",
    "properties",
    "units",
    "tenants",
    "leases",
    "applications",
    "payments",
]

ALIASES = {
    "properties": {
        "address_line": "address",
        "region": "state",
        "postal_code": "zip_code",
    }
}

DEFAULTS = {
    ("properties", "country"): "KE",
    ("properties", "time_zone"): "Africa/Nairobi",
    ("properties", "currency"): "KES",
    ("properties", "rental_type"): "multi_unit",
    ("properties", "subtype"): "apartment_block",
    ("properties", "floors"): 1,
    ("properties", "reservation_hold_hours"): 48,
    ("units", "floor_number"): 1,
    ("units", "furnished"): False,
    ("payments", "currency"): "KES",
    ("payments", "provider"): "manual",
    ("payments", "payment_type"): "rent",
    ("users", "failed_login_attempts"): 0,
    ("users", "totp_enabled"): False,
    ("users", "mfa_phone_verified"): False,
}

source_engine = create_engine(source_url)
target_engine = create_engine(target_url)

try:
    with source_engine.connect() as source, target_engine.begin() as target:
        actual_source = source.execute(
            text("SELECT current_database()")
        ).scalar_one()
        actual_target = target.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if actual_source != source_name or actual_target != TARGET_NAME:
            raise RuntimeError("Database identity check failed.")

        source_inspector = inspect(source)
        target_inspector = inspect(target)

        for table in TABLES:
            if not source_inspector.has_table(table):
                raise RuntimeError(f"Source table missing: {table}")
            if not target_inspector.has_table(table):
                raise RuntimeError(f"Target table missing: {table}")
            count = target.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one()
            if count:
                raise RuntimeError(
                    f"Destination table {table} is not empty; refusing to overwrite."
                )

        source_rows = {}
        for table in TABLES:
            source_rows[table] = source.execute(
                text(f'SELECT * FROM "{table}" ORDER BY id')
            ).mappings().all()

        # Preserve both approved applications if legacy data contains
        # conflicting active reservations for the same unit.
        active_counts = Counter(
            row["unit_id"]
            for row in source_rows["applications"]
            if row["status"] in ("approved", "offered", "paid")
        )
        conflicts = [unit for unit, count in active_counts.items() if count > 1]

        if conflicts:
            target.execute(
                text("DROP INDEX IF EXISTS uq_applications_active_reservation_unit")
            )
            print(
                "NOTICE: preserving conflicting active applications for unit IDs:",
                conflicts,
                file=sys.stderr,
            )
            print(
                "The unique reservation index was omitted on this destination "
                "because existing records conflict with it.",
                file=sys.stderr,
            )

        copied = {}

        for table in TABLES:
            target_columns = target_inspector.get_columns(table)
            source_columns = set(source_rows[table][0].keys()) if source_rows[table] else {
                column["name"] for column in source_inspector.get_columns(table)
            }
            target_names = {column["name"] for column in target_columns}
            aliases = ALIASES.get(table, {})

            prepared = []
            for row in source_rows[table]:
                record = {}
                for column in target_columns:
                    name = column["name"]

                    if name in row:
                        record[name] = row[name]
                        continue

                    old_name = aliases.get(name)
                    if old_name and old_name in row:
                        record[name] = row[old_name]
                        continue

                    key = (table, name)
                    if key in DEFAULTS:
                        record[name] = DEFAULTS[key]
                    elif column.get("default") is not None or column.get("nullable"):
                        # Let the database supply a default, or use NULL.
                        if column.get("default") is None and column.get("nullable"):
                            record[name] = None
                    else:
                        raise RuntimeError(
                            f"Cannot safely populate required column {table}.{name}. "
                            "No source value or approved default exists."
                        )

                prepared.append(record)

            for record in prepared:
                columns = list(record)
                quoted = ", ".join(f'"{name}"' for name in columns)
                placeholders = ", ".join(f":{name}" for name in columns)
                target.execute(
                    text(
                        f'INSERT INTO "{table}" ({quoted}) '
                        f"VALUES ({placeholders})"
                    ),
                    record,
                )

            copied[table] = len(prepared)

        # Advance PostgreSQL sequences so future inserts do not reuse IDs.
        for table in TABLES:
            if "id" not in {
                column["name"] for column in target_inspector.get_columns(table)
            }:
                continue
            target.execute(
                text("""
                    SELECT setval(
                        pg_get_serial_sequence(:table_name, 'id'),
                        COALESCE((SELECT MAX(id) FROM """ + f'"{table}"' + """), 1),
                        EXISTS (SELECT 1 FROM """ + f'"{table}"' + """)
                    )
                """),
                {"table_name": table},
            )

        print("Source database:", actual_source, file=sys.stderr)
        print("Destination database:", actual_target, file=sys.stderr)
        print("Copied row counts:", file=sys.stderr)
        for table, count in copied.items():
            print(f"  {table}: {count}", file=sys.stderr)
        print("Total copied:", sum(copied.values()), file=sys.stderr)
        print("Transaction committed successfully.", file=sys.stderr)

except Exception as exc:
    print(f"STOP — transaction rolled back: {exc}", file=sys.stderr)
    sys.exit(1)
finally:
    source_engine.dispose()
    target_engine.dispose()

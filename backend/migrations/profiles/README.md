# Migration profiles

Migration tracks are independent and are never inferred from the database schema:

- `historic` reads the existing, unchanged revision files in
  `../alembic/versions/`.
- `fresh` creates the current model schema from an empty database with its own
  independent baseline.
- `legacy` adopts the reviewed seven-table schema and applies its own additive
  reconciliation revisions.

The Legacy profile is independent of the Historic chain. Its adoption revision
accepts only the reviewed, unversioned PostgreSQL schema: exactly the seven
existing tables, their known columns/types/nullability, constraints, foreign
keys, indexes, and owned ID sequences. It refuses extra or missing schema
objects. The Fresh baseline is explicit and only applies when there is no
Alembic version table and the target schema contains no tables, columns, or
sequences. It does not stamp an existing database.

## Runner requirements

Run from `backend/` with `SQLALCHEMY_DATABASE_URI` or `DATABASE_URL` configured
in the process environment or `backend/.env`. The URL is not accepted as a
command-line argument, so credentials are not exposed in shell history or the
process list. Both a profile and exact database-name confirmation are required.

```sh
python migration_runner.py --profile fresh --confirm-database rental_fresh_20261102 upgrade head
python migration_runner.py --profile legacy --confirm-database rental_legacy_20261102 upgrade head
python migration_runner.py --profile historic --confirm-database rental_historic_copy_20261102 upgrade head
```

The fresh command is only for a newly created, empty database. The legacy
command is only for the exact reviewed seven-table schema and must be rehearsed
on a disposable restored copy first. The historic chain is preserved as-is and
has known upgrade conflicts; do not replay it on an unversioned schema. Never
use the runner against the original `rental_management` database.

Before any approved Legacy migration, make and verify a restorable backup of
the rehearsal database and rehearse the migration against a disposable copy.
For recovery, restore only into a separately named rehearsal/disposable
database after verifying its target identity; never restore over the original
database. The Fresh baseline is intended for an empty database only. It includes the
active-reservation uniqueness index represented by the current models because
the baseline starts with no application rows. Legacy retains the existing
`properties.address`, `state`, and `zip_code` columns while copying their values
into the current model columns. It keeps `tenants.user_id` nullable and does
not change existing IDs or password hashes. The migration deliberately does
not add the active-reservation unique index: the reviewed Legacy data contains
multiple approved applications for a unit. Those records remain unchanged;
resolving the collision requires an explicit business decision before that
index can be introduced.

The runner checks the selected profile's revision graph before connecting and
requires exactly one head. It rejects `heads`, comma-separated targets,
unknown revisions, missing profiles, non-PostgreSQL URLs, and the protected
database name. Before an upgrade it requires one known revision and the
selected profile's schema preflight. Fresh and Legacy may adopt only their
respective exact unversioned baselines; an empty version table, a foreign
revision, and multiple applied heads are refused. The runner never stamps a
database automatically.

The runner verifies `current_database()` inside a read-only transaction,
checks that the server-reported name matches both the URL and the confirmation,
rolls back the verification transaction, and runs Alembic on that same
connection. Its in-process authorization is bound to the verified connection,
selected profile, URL database, confirmed database, and live database
identity. Ordinary Flask-Migrate/Alembic execution is refused by the historic
environment unless that authorization is present. Application startup and
ordinary database queries remain enabled. Credentials are not printed.

Do not use `flask db upgrade`, `flask db stamp`, direct `alembic upgrade`, or
commands that target all heads. Flask-Migrate remains registered for
compatibility, but its Alembic environment rejects migration execution unless
the approved runner supplied its verified authorization.

## Profile test coverage

The Fresh baseline is tested with an in-memory SQLite database and its model
DDL is compiled for PostgreSQL without opening a PostgreSQL connection. Legacy
fingerprint tests use SQLite; the migration was also exercised on an isolated
disposable PostgreSQL database restored from the reviewed backup. The original
database was not connected to.

## Automated safety tests

Run the database-free migration safety and profile tests:

```sh
cd backend
python -m pytest tests/test_migration_runner.py tests/test_migration_profiles.py -q
```

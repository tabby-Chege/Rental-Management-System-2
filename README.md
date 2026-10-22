# Rental Management System
Property Finder is a full-stack rental portfolio manager built by extending a Phase 1 React application. Landlords can create an account, manage their own properties, search their portfolio, and use related unit, lease, and payment records. Tenants maintain their own profiles and apply for units; landlord-scoped tenant records are created through application approval rather than manual entry. The React client communicates with a custom Flask REST API; PostgreSQL stores persistent data through SQLAlchemy. The app does not verify rental availability or process real payments.

## Features

- Register and log in with JWT-based authentication.
- Create, view, update, and delete property and unit records; tenant records are linked through application approval.
- Store each property's ISO currency, country, region, city, address, postal code, and IANA time zone; format rent and payments in the property's currency.
- Store tenant phone numbers in international E.164 format.
- Create and view leases, update their terms or status, and end them without losing lease history.
- Associate records using relational database keys: users own properties and tenant records; properties have units; units and tenants connect through leases; leases connect to payments.
- Restrict property, tenant, unit, lease, and payment access to the authenticated owner (with explicit role rules for tenant self-access and admins).
- Paginate property, tenant, unit, lease, and payment lists and search properties by name, address, city, state, or postal code.
- Show loading, empty, validation, and failed-request messages in the React UI.
- Keep the Phase 1 React/Vite application and its existing navigation and property-search/detail experience while using the project's API for saved records.

## Technology

- **Frontend:** React 19, Vite, React Router, JavaScript, CSS
- **Backend:** Python 3.12+, Flask, Flask-JWT-Extended, Flask-SQLAlchemy, SQLAlchemy
- **Database:** PostgreSQL (SQLite in automated backend tests)
- **Database driver:** psycopg2

## Requirements

- Node.js 20.19+ and npm
- Python 3.12+ and pip
- PostgreSQL 14+ (or a compatible hosted PostgreSQL database)

## Setup and Run

### 1. Configure PostgreSQL

Create a database named `rental_management` and a database user with permission to use it. Keep credentials out of source control.

### 2. Start the Flask API

In a terminal:

```sh
cd backend
python -m venv .venv
```

Activate the virtual environment, then install dependencies:

```sh
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt

# Windows PowerShell
# .venv\Scripts\Activate.ps1
# pip install -r requirements.txt
```

Create `backend/.env` from `backend/.env.example`, then set:

```env
DATABASE_URL=postgresql+psycopg2://YOUR_USER:YOUR_PASSWORD@localhost:5432/rental_management
JWT_SECRET_KEY=generate-a-random-secret-of-at-least-32-characters
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Run the API from the `backend` directory:

```sh
python run.py
```

The API listens on `http://localhost:5000`. The server refuses to start unless `DATABASE_URL` (or `SQLALCHEMY_DATABASE_URI`) and a random `JWT_SECRET_KEY` of at least 32 characters are configured. `CORS_ORIGINS` is a comma-separated allowlist; replace the local development origins with the exact frontend origin(s) when deploying.

New accounts must use a password of at least 10 characters containing uppercase and lowercase letters, a number, and a symbol; passwords are limited to 72 UTF-8 bytes for bcrypt compatibility. Login is temporarily blocked for 15 minutes after five failed attempts in a 15-minute window. Access tokens expire after 15 minutes and refresh tokens rotate on use, expiring after 30 days.

For a new database, apply the Alembic schema from the `backend` directory:

```sh
flask --app run.py db upgrade
```

This applies the checked-in Flask-Migrate/Alembic revision; the application no longer creates schema tables on startup. For an existing database already upgraded with the historical SQL files in `backend/migrations/`, verify that its schema includes all current fields and then baseline it once with `flask --app run.py db stamp head`. Do not stamp an older schema: back it up, apply the required historical SQL migrations, verify the result, and only then stamp. Keep credentials out of source control.

For a local development secret, generate a value with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set it only in `backend/.env`.

### 3. Start the React app

In a second terminal from the project root:

```sh
npm install
npm run dev
```

Vite proxies `/api` requests to the Flask service at `http://localhost:5000`. Register an account in the app to create a landlord account, then add properties and units. Tenant records appear after an application is approved; landlords cannot create them manually. Do not place database credentials or JWT secrets in frontend environment variables.

## API Overview

Authentication endpoints are `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`, and `POST /api/auth/logout`. Access tokens expire after 15 minutes; refresh tokens expire after 30 days and are rotated on refresh. The frontend automatically refreshes access tokens for protected API requests.

Tenants manage their profile at `GET/PUT /api/tenant-profile/me`. Identity files upload through `POST /api/tenant-profile/me/documents` and are downloaded only through the authorized `GET /api/tenant-documents/<id>` route. Application submissions keep a profile and document-reference snapshot; landlords can read it only for applications on properties they own. A landlord must give a reason when approving or declining.

Configure a private S3-compatible bucket with `S3_BUCKET`, `S3_REGION`, and optionally `S3_ENDPOINT_URL`; credentials must come from the AWS credential chain or deployment secrets. Keep public bucket access blocked. Uploads are limited to 10 MB and PDF/JPEG/PNG/WebP; images are decoded and re-encoded before storage, and S3 server-side encryption defaults to AES256. Set a separate `TENANT_PII_ENCRYPTION_KEY` using `Fernet.generate_key()` to encrypt ID numbers at rest; do not rotate it without re-encrypting the stored IDs.

All API responses are JSON. Protected routes require `Authorization: Bearer <access_token>`. Register and log in at `/api/auth/register` and `/api/auth/login`.

| Resource | Routes | Access |
|---|---|---|
| **Properties** | `GET/POST /api/properties`; `GET/PUT/DELETE /api/properties/<id>`; portfolio counts at `GET /api/properties/summary` | Authenticated users; results and changes are limited to owned records, except admins. Property responses include computed total, occupied, reserved, and vacant unit counts. |
| **Tenants** | `GET /api/tenants`; `GET/PUT/DELETE /api/tenants/<id>` | Landlords manage tenant records linked through applications or leases; linked tenants may view their own record and update permitted contact fields. Manual tenant creation is disabled. |
| **Units** | `GET/POST /api/units`; `GET/PUT/DELETE /api/units/<id>`; `GET/POST /api/properties/<property_id>/units`; bulk create at `POST /api/properties/<property_id>/units/bulk`; `GET/POST /api/units/<unit_id>/rooms`; `PUT/DELETE /api/rooms/<room_id>`; public search at `GET /api/units/public` | Owning landlord or admin manage units and rooms; public search returns vacant units by default and supports location, bedrooms, bathrooms, rent range, unit type, availability, and pagination. Status is computed from active lease dates and approved applications. |
| **Applications** | `GET/POST /api/applications`; `GET/PATCH /api/applications/<id>`; `PATCH /api/applications/<id>/lease-terms`; `POST /api/applications/<id>/confirm-payment` | Tenants submit and view their applications; landlords review applications for owned units, set decisions with a reason, set lease terms, and confirm payment. Approval links the applicant to a tenant record and starts a fixed one-hour reservation. Confirming payment records the payment and creates the lease. |
| **Leases** | `GET/POST /api/leases`; `GET/PUT/DELETE /api/leases/<id>`; tenant views at `/api/leases/mine` and `/api/leases/mine/payments` | Owning landlord or admin; tenants can view only their linked leases and payments; deleting a lease ends it to preserve history. |
| **Payments** | `GET /api/payments` (also `/payments`); `POST /payments` | Landlords see payments for their properties; tenants see payments linked to their own lease. History includes tenant, property, and unit labels but no account credentials. |
| **Notifications** | `GET /api/notifications`; `PATCH /api/notifications/<id>/read` | Tenants view and mark their own reservation and lease notifications as read. |

Collection endpoints for properties, tenants, units, applications, leases, and payments support `page` and `per_page`, defaulting to page 1 and 10 records per page (maximum 100). For example: `GET /api/properties?page=2&per_page=10&q=Oak&city=Nairobi`. Paginated responses include the resource list and metadata (`page`, `per_page`, `total`, `pages`, `has_next`, and `has_prev`). Invalid pagination parameters return HTTP 400. Validation, authorization, missing records, and conflicts return `{"error": "..."}` and an appropriate HTTP status. Unhandled server failures are logged and return a generic JSON error without exposing internals.

Property create/update requests use `address_line`, `country` (ISO 3166-1 alpha-2), optional `region`, `city`, optional `postal_code`, `time_zone` (IANA), and `currency` (ISO 4217). Legacy address keys remain accepted during the transition. Unit, lease, and payment responses include the property's currency; payment amounts are stored as fixed-point decimals and validated against that currency's minor-unit precision. Tenant phone values are E.164 strings (for example, `+254712345678`).

Properties use `rental_type` (`multi_unit` or `whole_property`), a supported `subtype`, and a positive `floors` count. A whole-property create request must include a `whole_unit` object with `bedrooms`, `bathrooms`, and `rent_amount`; the API creates the sole unit as `Entire property`, and its rent/layout/details are updated through `whole_unit` in property updates. Multi-unit property requests create and manage units through the unit endpoints. Unit records support `floor_number`, `layout` (`studio` or a bedroom-plus-living-room value such as `2+1`), `size`, `size_unit` (`sqm` or `sqft`), and `furnished`. A unit can have up to 30 room records, with room type, optional size/unit, and description. Floor numbers cannot exceed the property's floor count; a property's floor count cannot be reduced below an existing unit's floor.

Property responses include an `occupancy_summary` with `total_units`, `occupied_units`, `reserved_units`, and `vacant_units`; `GET /api/properties/summary` returns portfolio-wide counts for the authenticated manager. An active lease makes a unit occupied; otherwise an active approved or offered application makes it reserved, and a unit with neither is vacant. Every approved application and waitlist offer has a fixed one-hour payment deadline; this duration cannot be configured or extended per property. Additional applications for a reserved unit join a FIFO waitlist. If payment is not confirmed before the deadline, the reservation expires and the next eligible applicant is offered the unit with a fresh one-hour deadline. Tenants receive in-app deadline reminders and status notifications. Payment confirmation is a manual landlord action, records a completed payment, and creates the lease with the supplied end date. Bulk unit creation accepts `units_per_floor`, `layout`, and `rent_amount`; it creates all floors atomically, numbering the first five units on floors 1 and 2 as `101`–`105` and `201`–`205`. The request is capped at 500 units and does not overwrite existing units.

Public rental search uses individual unit records, not property-level rent or bedroom estimates. For example, `GET /api/units/public?location=Nairobi&bedrooms=2&min_rent=10000&max_rent=20000&unit_type=two-bedroom&availability=vacant` returns matching unit details with the parent property location. `availability` accepts `vacant`, `reserved`, `occupied`, or `all` and defaults to `vacant`. Tenants may apply to vacant units or join a reserved unit's waitlist; applications to actively occupied units are rejected.

Reservation expiry, waitlist promotion, deadline reminders, and lease-start notifications are processed during relevant API reads. Production deployments must also schedule `flask --app run.py process-reservations` from the `backend/` directory at least once per minute. The scheduler must use the deployed virtual environment and the same production database and secrets as the API; otherwise reservations can remain active and waitlisted applicants will not be promoted while no one is using the app. For example, a Linux cron entry for an installation at `/srv/rental-management` is:

```cron
* * * * * cd /srv/rental-management/backend && /srv/rental-management/backend/.venv/bin/flask --app run.py process-reservations >> /var/log/rental-management/reservations.log 2>&1
```

Configure the cron environment with the same deployment variables used by the API (or ensure the backend's deployment environment file is loaded by Flask). Retain the schedule when scaling the web service; the command is safe to run repeatedly and coordinates expiry through the database. API reads remain an opportunistic fallback, not a replacement for this schedule.

## Testing and Quality Checks

Run frontend checks from the project root:

```sh
npm test
npm run lint
npm run build
```

Run backend tests from `backend` with its virtual environment active:

```sh
pip install -r requirements.txt
pytest
```

Backend tests use an in-memory SQLite database; normal app configuration uses PostgreSQL.

## Project Structure

```text
backend/
├── run.py
├── requirements.txt
├── server/
│   ├── models*.py
│   ├── routes/
│   └── pagination.py
└── tests/
src/
├── api/              # Flask API clients
├── components/       # Shared route and property components
├── pages/            # Search, authentication, property, and tenant views
└── utils/
```

## Security and Limitations

- Store `.env` files locally only; `.gitignore` excludes them. Use a unique, high-entropy `JWT_SECRET_KEY`.
- Public registration creates landlord accounts; role changes and admin provisioning must be performed through a trusted administrative process.
- Lease termination preserves records and payment history; it does not represent a legal lease workflow or send tenant notices.
- Payment records are tracking data only; the app does not connect to a payment provider or move money.
- No deployment is configured. Use HTTPS, managed secrets, database migrations, and a production WSGI server before hosting publicly.

# Rental Management System
Property Finder is a full-stack rental portfolio manager built by extending a Phase 1 React application. Landlords can create an account, manage their own property and tenant records, search their portfolio, and use related unit, lease, and payment records. The React client communicates with a custom Flask REST API; PostgreSQL stores persistent data through SQLAlchemy. The app does not verify rental availability or process real payments.

## Features

- Register and log in with JWT-based authentication.
- Create, view, update, and delete property records.
- Create, view, update, and delete tenant records.
- Associate records using relational database keys: users own properties and tenant records; properties have units; units and tenants connect through leases; leases connect to payments.
- Restrict property and tenant access to the authenticated owner (with explicit role rules for tenant self-access and admins).
- Paginate property and tenant lists and search properties by name, address, city, state, or postal code.
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
JWT_SECRET_KEY=replace-with-a-long-random-secret
```

Run the API from the `backend` directory:

```sh
python run.py
```

The API listens on `http://localhost:5000`. The development app factory creates missing tables; for production, use a migration workflow rather than relying on `create_all`.

### 3. Start the React app

In a second terminal from the project root:

```sh
npm install
npm run dev
```

Vite proxies `/api` requests to the Flask service at `http://localhost:5000`. Register an account in the app to create a landlord account, then add property and tenant records. Do not place database credentials or JWT secrets in frontend environment variables.

## API Overview

All API responses are JSON. Protected routes require `Authorization: Bearer <access_token>`. Register and log in at `/api/auth/register` and `/api/auth/login`.

| Resource | Routes | Access |
|---|---|---|
| **Properties** | `GET/POST /api/properties`; `GET/PUT/DELETE /api/properties/<id>` | Authenticated users; results and changes are limited to owned records, except admins. |
| **Tenants** | `GET/POST /api/tenants`; `GET/PUT/DELETE /api/tenants/<id>` | Landlords manage their own tenant records; linked tenants may view their own record and update permitted contact fields. |
| **Units** | `GET/POST /api/properties/<property_id>/units`; `PUT/DELETE /api/units/<id>` | Owning landlord or admin; deletion is blocked when a unit has lease history. |
| **Applications** | `GET/POST /api/applications`; `GET/PATCH /api/applications/<id>` | Tenants submit and view their own applications; landlords view applications for their units and approve or decline them. Approval links the applicant account to a tenant record and returns lease-form prefill values. |
| **Leases** | `POST /api/leases`; `DELETE /api/leases/<id>` | Owning landlord or admin; ending a lease is represented as deactivation to preserve history. |
| **Payments** | `GET/POST /payments` | Landlords see/manage payments for their properties; tenants can view payments linked to their lease. |

Collection endpoints for properties, tenants, units, applications, and payments support `page` and `per_page`, defaulting to page 1 and 10 records per page (maximum 100). For example: `GET /api/properties?page=2&per_page=10&q=Oak&city=Nairobi`. Paginated responses include the resource list and metadata (`page`, `per_page`, `total`, `pages`, `has_next`, and `has_prev`). Invalid pagination parameters return HTTP 400. Validation, authorization, missing records, and conflicts return an error message and an appropriate HTTP status.

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
- Tenant and lease relationships are stored, but the interface is focused on property and tenant CRUD rather than full leasing operations.
- Payment records are tracking data only; the app does not connect to a payment provider or move money.
- No deployment is configured. Use HTTPS, managed secrets, database migrations, and a production WSGI server before hosting publicly.

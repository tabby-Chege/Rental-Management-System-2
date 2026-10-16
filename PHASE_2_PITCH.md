# Phase 2 Pitch: Property Finder to Rental Management

## Step 1: Business Problem Scenario

**Phase 1 Property Finder** is a React app for searching property records by city, filtering results, and viewing property details. It helps people explore properties but does not help independent landlords and small property managers organize the properties they actually manage. Many track buildings, units, tenants, and lease dates across spreadsheets, messages, and paper records. Information becomes duplicated or outdated, and routine questions—such as which tenant occupies a unit or when a lease ends—take too long to answer.

In Phase 2, I will extend this existing React app into a lightweight rental-management workspace, not start a new frontend. The existing navigation, search, property cards, and detail views will provide the foundation for authenticated, persistent records. A single searchable workspace will reduce repeated data entry and make portfolio information easier to maintain.

**Goal:** Replace the Phase 1 public property-data integration with the app's own Flask API and PostgreSQL database. Let authenticated users manage their properties and tenant records, then connect them to units and leases. This MVP does not claim verified rental availability or provide full accounting.

**User stories**
- As a landlord, I want to create, view, edit, and delete my properties so my portfolio stays accurate.
- As a landlord, I want to create, view, edit, and delete tenant contact records so my rental relationships stay current.
- As a manager, I want to find a property and see its units and related rental records without searching separate files.
- As a landlord, I want tenants and leases linked to the correct units so I can track occupancy and lease dates.
- As a user, I want a clear error and a chance to retry when a request fails so I know whether my changes were saved.

RentCast will no longer supply the app's property records. The MVP will use the project's own database; no external API or AI service is required. This keeps the core workflow dependable and avoids client-side third-party API keys.

## Step 2: Problem-Solving Process

I will use an iterative software development lifecycle: plan, design, build, test with feedback, and document. The high-level flow is **React page → API client (`fetch /api/...` with JWT) → Flask route → SQLAlchemy → PostgreSQL → JSON response → UI success/error state**.

1. **Plan and research:** Review Phase 1 routes and data fields; define user stories, MVP acceptance checks, and API shapes. Research Flask/JWT, SQLAlchemy relationships, PostgreSQL setup, and Vite proxy/CORS where needed.
2. **Design the data and API:** Use PostgreSQL with Flask-SQLAlchemy. Relationships: `User` 1-to-many `Property` (`Property.owner_id`) and `Tenant` (`Tenant.landlord_id`); `Property` 1-to-many `Unit`; `Unit` and `Tenant` connect through `Lease`; `Lease` 1-to-many `Payment`. Foreign keys and validation preserve data integrity. Implement authenticated property and tenant CRUD with owner checks, then connect units and leases.
3. **Build and test the backend:** Implement Flask JSON routes, JWT-protected access, SQLAlchemy persistence, pagination, and consistent error responses. Test successful CRUD, invalid input, missing records, unauthorized access, and relationship rules before integrating the UI.
4. **Extend the existing React app:** Keep React, Vite, and React Router. Retain the app shell, `ProtectedRoute`, `Login`, and `Register`; connect the property search/detail and existing property, tenant, unit, and lease management pages to the Flask API. Keep requests in API-client modules and reuse form and status/error patterns. Use `useState` for form/request state and `useEffect` for loading. Replace RentCast calls with the Flask API. Show loading, empty, validation, and request-failure states, with retry where useful.
5. **Verify and deliver:** Test sign-in and the browser CRUD journey, confirm related records link correctly, request peer critique, and fix the highest-impact issues. Run tests, lint, and production build; document setup, API/models, and limitations in the README; prepare the presentation and reflection.

**Rubric fit:** Full property and tenant CRUD provide two authenticated, owner-scoped relational resources. The `User`–`Property`, `User`–`Tenant`, and property/unit/lease relationships meet the data-model requirements. Preserving and extending the React UI supports a coherent experience. API and browser checks cover failed requests. README, presentation, and reflection document setup, design, and learning. External API integration is optional and intentionally excluded from the MVP.

## Step 3: Timeline and Scope

**Estimated duration: 3 weeks (15 working days).**

| Phase | Time | Work and milestone |
|---|---:|---|
| **Planning and research** | **2 days** | Confirm user stories, MVP fields, acceptance criteria, and API/model outline; research unfamiliar tools. **Milestone:** agreed implementation checklist. |
| **Backend setup and modeling** | **4 days** | Configure Flask, PostgreSQL, SQLAlchemy, and environment variables; implement authentication, ownership, property CRUD, one additional relationship, and route tests. **Milestone:** persistent, tested API. |
| **Frontend structure and styling** | **4 days** | Extend existing React routes; replace RentCast property calls; connect property CRUD forms and states; style the management flow. **Milestone:** end-to-end CRUD in Phase 1 app. |
| **Debugging, testing, and iteration** | **3 days** | Test API and browser success/failure cases; fix integration bugs; get peer critique and apply priority feedback; run project checks. **Milestone:** reliable demo. |
| **README, presentation, reflection** | **2 days** | Document installation, environment/database setup, API, and limitations; prepare demo and reflect on trade-offs and next steps. **Milestone:** reproducible final submission. |

**In scope:** existing Phase 1 React app; Flask; PostgreSQL via SQLAlchemy; authentication and user-owned records; full property and tenant CRUD; related units and leases; replacing the public property API; pagination, validation, and visible request-error handling.

**Out of scope:** payment processing/bookkeeping, maintenance tickets, notifications, AI recommendations, verified availability, and production hosting.

**Risks and open questions:** PostgreSQL configuration, JWT handling across frontend/backend, and authorization through related records may take extra time. Research proxy/CORS and token behavior early; prove one authenticated database round trip before building every screen. Confirm how much tenant/lease functionality the rubric expects. If behind schedule, prioritize secure property CRUD and `User`–`Property` plus `Property`–`Unit` relationships. Reserve the final three days for critique, regression fixes, and testing—not new features. Keep secrets in environment variables, never in the React client or source control.

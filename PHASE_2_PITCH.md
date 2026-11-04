# Phase 2 Pitch: Property Finder to Rental Management

## Step 1: Business Problem Scenario

**Phase 1 Property Finder** is a React app for searching property records by city, filtering results, and viewing property details. It helps people explore properties but does not help independent landlords and small property managers organize the properties they actually manage. Many track buildings, units, tenants, and lease dates across spreadsheets, messages, and paper records. Information becomes duplicated or outdated, and routine questions—such as which tenant occupies a unit or when a lease ends—take too long to answer.

In Phase 2, I will extend this existing React app into a lightweight rental-management workspace, not start a new frontend. The existing navigation, search, property cards, and detail views will provide the foundation for authenticated, persistent records. A single searchable workspace will reduce repeated data entry and make portfolio information easier to maintain.

**Goal:** Extend the Phase 1 property search into an authenticated rental-management product backed by the project's Flask API and PostgreSQL database. Property availability is derived from lease and reservation records; payment-provider integrations default to sandbox and require explicit credentials for live transactions. This is not a full accounting product.

**User stories**
- As a landlord, I want to create, view, edit, and delete my properties so my portfolio stays accurate.
- As a tenant, I want to create and maintain my profile, apply to a unit, and receive a clear approval or decline reason.
- As a landlord, I want to review tenant applications and configure the payment hold for each property.
- As a manager, I want to find a property and see its units, photos, and related rental records without searching separate files.
- As a tenant and landlord, I want to communicate in property-scoped conversations and receive reservation and payment updates.
- As a user, I want a clear error and a chance to retry when a request fails so I know whether my changes were saved.

RentCast will no longer supply the app's property records. The MVP will use the project's own database; no external API or AI service is required. This keeps the core workflow dependable and avoids client-side third-party API keys.

## Step 2: Problem-Solving Process

I will use an iterative software development lifecycle: plan, design, build, test with feedback, and document. The high-level flow is **React page → API client (`fetch /api/...` with JWT) → Flask route → SQLAlchemy → PostgreSQL → JSON response → UI success/error state**.

1. **Plan and research:** Review Phase 1 routes and data fields; define user stories, MVP acceptance checks, and API shapes. Research Flask/JWT, SQLAlchemy relationships, PostgreSQL setup, and Vite proxy/CORS where needed.
2. **Design the data and API:** Use PostgreSQL with Flask-SQLAlchemy. Relationships: `User` 1-to-many `Property` (`Property.owner_id`) and `TenantProfile`; a landlord's `Tenant` record is linked to a user and created through application approval. `Property` has many `Unit` records; `Unit` and `Tenant` connect through `Lease`; `Lease` has many `Payment` records. Foreign keys and validation preserve data integrity. Role- and owner-scoped routes protect property, profile, tenant, unit, and lease records.
3. **Build and test the backend:** Implement Flask JSON routes, JWT-protected access, SQLAlchemy persistence, pagination, and consistent error responses. Test successful CRUD, invalid input, missing records, unauthorized access, and relationship rules before integrating the UI.
4. **Extend the existing React app:** Keep React, Vite, and React Router. Retain the app shell, `ProtectedRoute`, `Login`, and `Register`; connect the property search/detail and existing property, tenant, unit, and lease management pages to the Flask API. Keep requests in API-client modules and reuse form and status/error patterns. Use `useState` for form/request state and `useEffect` for loading. Replace RentCast calls with the Flask API. Show loading, empty, validation, and request-failure states, with retry where useful.
5. **Verify and deliver:** Test authentication, authorization, applications, reservation expiry, payments, and the browser journey; request peer critique and fix the highest-impact issues. Run backend/frontend tests, E2E, lint, and production build; document setup, API/models, migration safety, and limitations; prepare the presentation and reflection.

**Rubric fit:** Property management and role-scoped tenant profiles/records provide authenticated relational workflows. The `User`–`Property`, `User`–`TenantProfile`, `Property`–`Unit`, and unit/tenant/lease/payment relationships support the core data model. Preserving and extending the React UI supports a coherent experience. API and browser checks cover successful, invalid, and unauthorized requests. README, presentation, and reflection document setup, design, limitations, and learning. External property APIs and AI recommendations are intentionally excluded.

## Step 3: Timeline and Scope

**Planning baseline: estimated duration of 3 weeks (15 working days).** The repository records the original estimate and milestones, but not actual calendar dates; do not present planned durations as measured completion dates.

| Phase | Time | Work and milestone |
|---|---:|---|
| **Planning and research** | **2 days** | Confirm user stories, MVP fields, acceptance criteria, and API/model outline; research unfamiliar tools. **Milestone:** agreed implementation checklist. |
| **Backend setup and modeling** | **4 days** | Configure Flask, PostgreSQL, SQLAlchemy, and environment variables; implement authentication, ownership, property CRUD, one additional relationship, and route tests. **Milestone:** persistent, tested API. |
| **Frontend structure and styling** | **4 days** | Extend existing React routes; replace RentCast property calls; connect property CRUD forms and states; style the management flow. **Milestone:** end-to-end CRUD in Phase 1 app. |
| **Debugging, testing, and iteration** | **3 days** | Test API and browser success/failure cases; fix integration bugs; get peer critique and apply priority feedback; run project checks. **Milestone:** reliable demo. |
| **README, presentation, reflection** | **2 days** | Document installation, environment/database setup, API, and limitations; prepare demo and reflect on trade-offs and next steps. **Milestone:** reproducible final submission. |

**In scope:** existing Phase 1 React app; Flask; PostgreSQL via SQLAlchemy; role-based authentication; property, unit, tenant-profile, application, lease, and payment workflows; listing media; messaging and notifications; configurable server-enforced reservations and waitlists; pagination, validation, and visible request-error handling.

**Out of scope:** full accounting, AI recommendations, production hosting, and live payment-provider operation without the required deployment credentials.

**Risks and trade-offs:** Production provider credentials, webhook setup, and the scheduled reservation processor remain deployment responsibilities. Existing databases require schema inspection and a reviewed migration or verified baseline; never assume a legacy database is empty. Keep secrets in environment variables, never in the React client or source control. The system prioritizes auditable reservation/payment transitions and preserved rental records over a full accounting or legal-lease product.

## Step 4: Professionalism and Presentation Quality

The submission should demonstrate a cohesive, accessible product rather than disconnected pages:

- Use consistent role-specific navigation, responsive layouts, labelled forms, loading/empty states, and actionable success/error messages.
- Keep authorization and reservation/payment decisions on the server; do not treat a client countdown as authoritative.
- Use environment-based secrets, private tenant-document storage, input validation, and protected tenant/landlord records.
- Keep setup, data relationships, operational limitations, and safe migration guidance in the README.
- Run backend and frontend tests, Playwright E2E, lint, production build, and CI before submission.

**Demo evidence:** show one landlord listing a photographed unit, one tenant completing a profile and applying, the landlord recording a decision and lease terms, then the tenant starting a bank-transfer checkout and the landlord verifying it. Finish by showing the paid application, created lease, occupied unit, and a responsive layout. Include test/CI output and discuss the sandbox/live-provider and database migration limitations.

| Rubric area | Evidence to present |
|---|---|
| Business Problem – 25 marks | Target landlord/tenant scenario, user stories, and measurable workflow addressed by the application. |
| Problem-Solving Process – 25 marks | Requirements-to-model/API design, validation/security decisions, iterative feedback, tests, and documented trade-offs. |
| Timeline and Scope – 25 marks | The three-week plan and milestones above, with the final demo demonstrating delivered scope and any explicitly deferred work. |
| Professionalism and Presentation Quality – 25 marks | Coherent responsive UI, accessible states, safe configuration, reproducible setup, CI/test evidence, and a concise end-to-end demonstration. |

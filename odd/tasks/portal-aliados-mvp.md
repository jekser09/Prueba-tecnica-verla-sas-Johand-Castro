# Feature: VERLA SAS Commercial Allies Portal MVP (`portal-aliados-mvp`)

- **Repository Locator**: `odd/tasks/portal-aliados-mvp.md`
- **Engram Topic Key**: `odd/portal-aliados-mvp/tasks`
- **TDD Mode**: `enabled` (Source: `GEMINI.md` session config + `AGENTS.md` Section 4; Runner: `uv run python manage.py test`)
- **Delivery Strategy**: `ask-on-risk` (Forecast: ~1,400 authored lines across 5 work units; ~250–350 lines per task)

## Objective & Problem
Build and verify the operational MVP for **Portal de Aliados Comerciales — VERLA SAS** covering the 6 grading dimensions: relational data model with audit trail and optimistic concurrency control, full CRUD for commercial network (`Ciudad`, `Aliado`, `Coordinador`, `Vendedor`), monthly goals vs. actual results (`MetaMensual`), period offers with images (`OfertaPeriodo`), controlled AI integration with Google Gemini (`AIAuditLog`), RBAC & seller state blocking, and automated test suite.

## Authorized Scope & Constraints
- **Currently Authorized Scope**: Task 1 — Domain Data Models (`red_comercial`, `operacion`, `asistente_ia`), Optimistic Concurrency Control (`version`), `AuditLog` helpers, Django Admin registration, SQLite migrations (`db.sqlite3` ready for DBeaver ER diagram extraction), Data Dictionary documentation, and unit tests.
- **Constraints**:
  - Unidirectional app dependency flow: `asistente_ia` -> `operacion` -> `red_comercial`.
  - Every feature must have automated tests passing via `uv run python manage.py test`.
  - Advisory heuristic: ~400 authored changed lines per ODD task (never omit tests or comments for line savings).

## Acceptance Criteria & Applicable Checks
- All models created, migrated cleanly into `db.sqlite3` with SQLite foreign keys intact for DBeaver ER export.
- Optimistic locking (`version` increment and `ConcurrentModificationError` on stale version) and `AuditLog` recording verified via automated tests.
- `uv run python manage.py makemigrations --check --dry-run` and `uv run python manage.py test` pass (`OK`).

## Task Checklist

- [x] **T1: Data Models, Concurrency Primitives, Migrations & Data Dictionary** (Route: `delegated` — Writer trigger: touches `red_comercial/models.py`, `operacion/models.py`, `asistente_ia/models.py`, `admin.py`, `docs/DATA_MODEL.md`, and test files)
  - Implement `VersionedModel` / optimistic locking update helper (`ConcurrentModificationError`), `Ciudad`, `Aliado`, `Coordinador`, `Vendedor` (employee record + M2M cities + `ACTIVO`/`INACTIVO`/`BLOQUEADO` states), and `AuditLog` in `red_comercial`.
  - Implement `MetaMensual` (monthly goals vs. actuals with aggregation helpers by seller, coordinator, and ally) and `OfertaPeriodo` (text + `ImageField` + date range + scope) in `operacion`.
  - Implement `AIAuditLog` in `asistente_ia`.
  - Register models in Django Admin, run `makemigrations` and `migrate` so `db.sqlite3` is populated for DBeaver, document the Data Dictionary in `docs/DATA_MODEL.md`, and pass all model/concurrency/audit unit tests.
  - **Verification**: `uv run python manage.py test -v 2` -> `Ran 12 tests in 2.680s — OK`; `uv run python manage.py makemigrations --check --dry-run` -> `No changes detected`.
- [x] **T1.5: Application & AI Rate Limiting Middleware (`aliados/ratelimit.py`)** (Route: `delegated` — Writer trigger: touches `aliados/ratelimit.py`, `aliados/settings.py`, and `red_comercial/tests.py`)
  - Implement ASGI-compatible (`sync_and_async_middleware`) sliding/fixed-window rate limiter in `aliados/ratelimit.py` backed by Django's cache (`CACHES['default']`), with tiered limits (Global API/Web limit vs. strict `/asistente/` AI limit), returning HTTP `429 Too Many Requests` + `Retry-After` and `X-RateLimit-*` headers.
  - Configure `CACHES` and `RATE_LIMIT_*` settings in `aliados/settings.py` (with Spanish comments) and verify with automated tests.
  - **Verification**: `uv run python manage.py test -v 2` -> `Ran 16 tests in 2.667s — OK`.
- [x] **T2: Base Dark Theme UI (Pico CSS + VERLA Palette), Auth/RBAC & Demo Role Switcher** (Route: `delegated` — Writer trigger: touches `static/css/verla.css`, `templates/base.html`, `templates/core/`, `templates/registration/`, `red_comercial/rbac.py`, `red_comercial/views_core.py`, `aliados/urls.py`, `aliados/settings.py`, and test files)
  - Configure Pico CSS v2 via CDN and VERLA custom dark theme design tokens derived from `Logo verla horizontal.png` (`--verla-brand-indigo`, `--verla-brand-navy`, `--verla-bg-canvas`, `--verla-bg-surface`, `--verla-border`, etc.) in `static/css/verla.css`.
  - Create responsive base layouts (`templates/base.html`, `templates/core/home.html`, `templates/registration/login.html`, `templates/core/acceso_bloqueado.html`) with header logo container and status badges.
  - Implement dynamic Demo Role Switcher toolbar (`/simular-rol/`) allowing seamless evaluation of `ADMIN`, `ALIADO`, `COORDINADOR`, `VENDEDOR (ACTIVO)`, and `VENDEDOR (BLOQUEADO)` without manual credential juggling.
  - Implement RBAC inspection and operational state guard decorator (`requerir_roles`, `verificar_vendedor_operativo`) returning HTTP `403 Forbidden` with blocking reason when sellers are in `BLOQUEADO` or `INACTIVO` state.
  - Wire Django authentication views (`/login/`, `/logout/`) and context processor `portal_context`.
  - **Verification**: `uv run python manage.py test -v 2` -> `Ran 20 tests in 4.942s — OK`; `uv run python manage.py makemigrations --check --dry-run` -> `No changes detected`.
- [x] **T3: Commercial Network CRUD Views, History Audit View & Concurrency (`409 Conflict`) Guards** (Route: `delegated` — Client alerts via SweetAlert2 CDN + Vanilla JS)
  - Integrated SweetAlert2 v11 via CDN with custom Dark Theme styling, prohibiting native `alert()`/`confirm()` across the system.
  - Implemented CRUD forms (`CiudadForm`, `AliadoForm`, `CoordinadorForm`, `VendedorForm`) with optimistic concurrency hidden `version` field and strict business validations (coordinator-ally ownership, required reason for `INACTIVO`/`BLOQUEADO` states).
  - Implemented responsive dark-themed CRUD views and templates for `Ciudad`, `Aliado`, `Coordinador`, and `Vendedor` (with multi-city operations, search filtering, and state badges).
  - Implemented optimistic locking update flow triggering HTTP `409 Conflict` and SweetAlert2 warning reload modal when concurrent modifications occur without data loss.
  - Implemented unified `AuditLog` history view with entity filtering, pagination, and JSON diffs of before/after state transitions.
  - **Verification**: `uv run python manage.py test -v 2` -> `Ran 24 tests in 6.707s — OK`; `uv run python manage.py makemigrations --check --dry-run` -> `No changes detected`.
- [x] **T4: Monthly Goals vs. Actuals Dashboard & Period Offers (with Images & Seller View)** (Route: `delegated` — Writer trigger: touches `operacion/views.py`, `operacion/forms.py`, `operacion/urls.py`, `operacion/models.py`, `templates/operacion/`, and `operacion/tests.py`)
  - Implement operational dashboard view (`operacion_dashboard_view`) with period filtering (`YYYY-MM`), overall goal metrics (total budget, verified sales, percentage with color thresholds), and drill-downs by coordinator and ally.
  - Implement specialized active seller portal view (`mis_metas_y_ofertas_vendedor_view`) showing personal goal fulfillment, historical goals table, and scoped commercial offers (filtered by ally and base/operating cities).
  - Implement CRUD forms and views for `MetaMensual` and `OfertaPeriodo` with image upload support and optimistic concurrency locking (`version`) triggering HTTP `409 Conflict` on race conditions.
  - **Verification**: `uv run python manage.py test -v 2` -> `Ran 27 tests in 9.565s — OK`; `uv run python manage.py makemigrations --check --dry-run` -> `No changes detected`.
- [ ] **T5: Controlled Google Gemini AI Assistant (`async def` + `httpx` + `AIAuditLog`) & Seed Data Command** (Route: `delegated`)
- [ ] **T6: Project Review, Hardening & Free Deployment Platform with Automated SSL** (Route: `delegated` — Writer trigger: deployment configuration, environment checklist, security headers, platform evaluation for Render / Railway / Fly.io with automated HTTPS/SSL, and final smoke test)
  - Perform full project audit (static assets collection, SQLite WAL settings, rate limit quotas, dark theme Pico/SweetAlert2 responsiveness, RBAC guards).
  - Define and document deployment architecture on a platform with a free tier and automated SSL certificate (e.g. Render / Railway) supporting Python 3.14 + Granian ASGI + persistent disk or SQLite storage.
  - Provide production run commands, environment variables reference (`.env.template`), and deployment guide in `docs/DEPLOYMENT.md`.
  - Comprehensive end-to-end test run and verification before handoff.

## Progress & Verification Evidence
- **Bootstrap**: Static/HTML minification pipeline (`aliados/storage.py`) and SQLite WAL configuration verified (`Ran 3 tests in 0.032s — OK`, commit `77804a3`).
- **T1 & T1.5 Completed**: Domain models (`red_comercial`, `operacion`, `asistente_ia`), optimistic concurrency control (`VersionedModel.optimistic_update` + `ConcurrentModificationError`), `AuditLog` before/after diffs, initial migrations on `db.sqlite3`, Data Dictionary (`docs/DATA_MODEL.md`), and dual WSGI/ASGI `RateLimitMiddleware` (`aliados/ratelimit.py`) with 16 automated tests passing (`Ran 16 tests in 2.695s — OK`).
- **T2 Completed**: Base Dark Theme UI (Pico CSS v2 + VERLA dark design tokens), responsive layout (`templates/base.html`, `login.html`, `acceso_bloqueado.html`), RBAC guards (`requerir_roles`, `verificar_vendedor_operativo`), and Demo Role Switcher (`/simular-rol/`) with 20 automated tests passing (`Ran 20 tests in 4.942s — OK`).
- **T3 Completed**: Commercial Network CRUD (`Ciudad`, `Aliado`, `Coordinador`, `Vendedor`), SweetAlert2 notifications & conflict modal, optimistic concurrency HTTP `409 Conflict` guards, and `AuditLog` history viewer with 24 automated tests passing (`Ran 24 tests in 6.707s — OK`).
- **T4 Completed**: Operations Dashboard (`MetaMensual` aggregation by period/ally/coordinator, % threshold indicators), `OfertaPeriodo` image uploads & city/ally scoping, dedicated active seller portal view, and concurrency 409 protection with 27 automated tests passing (`Ran 27 tests in 9.565s — OK`).
- **Next Step**: Execute T5 (Controlled Google Gemini AI Assistant & Seed Data Command).

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
- [ ] **T2: Base Dark Theme UI (Pico CSS + VERLA Palette), Auth/RBAC & Demo Role Switcher** (Route: `delegated`)
- [ ] **T3: Commercial Network CRUD Views, History Audit View & Concurrency (`409 Conflict`) Guards** (Route: `delegated`)
- [ ] **T4: Monthly Goals vs. Actuals Dashboard & Period Offers (with Images & Seller View)** (Route: `delegated`)
- [ ] **T5: Controlled Google Gemini AI Assistant (`async def` + `httpx` + `AIAuditLog`) & Seed Data Command** (Route: `delegated`)

## Progress & Verification Evidence
- **Bootstrap**: Static/HTML minification pipeline (`aliados/storage.py`) and SQLite WAL configuration verified (`Ran 3 tests in 0.032s — OK`, commit `77804a3`).
- **T1 & T1.5 Completed**: Domain models (`red_comercial`, `operacion`, `asistente_ia`), optimistic concurrency control (`VersionedModel.optimistic_update` + `ConcurrentModificationError`), `AuditLog` before/after diffs, initial migrations on `db.sqlite3`, Data Dictionary (`docs/DATA_MODEL.md`), and dual WSGI/ASGI `RateLimitMiddleware` (`aliados/ratelimit.py`) with 16 automated tests passing (`Ran 16 tests in 2.695s — OK`).
- **Next Step**: Execute T2 (Base Dark Theme UI with Pico CSS + VERLA Palette, Auth/RBAC & Demo Role Switcher).

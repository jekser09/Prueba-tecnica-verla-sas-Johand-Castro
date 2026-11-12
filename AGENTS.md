# AGENTS.md — VERLA SAS Commercial Allies Portal

Authoritative technical and architectural contract for AI coding agents working in this repository.

---

## 1. Application Overview & Business Problem

**Portal de Aliados Comerciales — VERLA SAS** is a unified operational MVP platform to configure and govern VERLA SAS's commercial network, monthly sales goals vs. actual results, and active promotional offers per period.

### Core Business Rules
1. **Commercial Hierarchy**:
   - **`Aliado` (Commercial Ally)**: Contract owner responsible for its commercial network.
   - **`Coordinador` (Coordinator)**: Belongs to an `Aliado` and supervises assigned sellers (`Vendedor`).
   - **`Vendedor` (Seller / Employee Record)**: Employee with personal record (`documento`, `contacto`, `cargo`, `ciudad_base`, `estado`, `fecha_ingreso`), assigned to a responsible `Coordinador`, and able to operate across **one or multiple `Ciudad` (cities)**.
2. **Operational States & Blocking Control**:
   - Every `Vendedor` has an explicit state: `ACTIVO`, `INACTIVO`, or `BLOQUEADO`.
   - Sellers in `BLOQUEADO` or `INACTIVO` state must be restricted from active commercial operations and portal views according to role/state guards.
3. **Monthly Goals vs. Actual Results**:
   - Tracked per month (`YYYY-MM`) with aggregation and drill-down by **`Vendedor`**, **`Coordinador`**, and **`Aliado`**.
4. **Period Offers (`OfertaPeriodo`)**:
   - Time-bounded commercial offers containing dynamic text and variable images (`ImageField`), visible to active sellers operating in the target scope.
5. **Audit Trail & Concurrency Control**:
   - **Change History (`AuditLog`)**: Every create, update, and state transition across core entities records actor, timestamp, entity, before/after JSON diff, and resulting version.
   - **Optimistic Concurrency Control (`version`)**: Editable entities carry an integer `version` field. Updates must validate `WHERE id = :id AND version = :expected_version` and atomically increment `version = F("version") + 1`. Stale writes must be rejected with HTTP `409 Conflict`.
6. **Controlled AI Integration (`asistente_ia`)**:
   - Powered by **Google Gemini API (`gemini-2.5-flash`)** over async HTTP (`httpx.AsyncClient`).
   - Operates strictly under **human-in-the-loop** control (drafts commercial offer copy and analyzes monthly goal gaps without mutating domain records directly) and logs latency, token usage, and human verdict (`ACEPTADO`, `EDITADO`, `DESCARTADO`) in `AIAuditLog`.

---

## 2. Architecture & Tech Stack

| Layer | Technology | Rules & Conventions |
| :--- | :--- | :--- |
| **Runtime & Package Manager** | **Python >= 3.14.7** + **`uv`** | Always run commands via `uv run ...` and manage dependencies in `pyproject.toml`. |
| **Web Framework** | **Django 6.x** (`aliados` project) | Use `python-decouple` (`config`, `Csv`) in `aliados/settings.py`. User-facing UI copy is in professional Spanish. |
| **Domain Apps (3-App Screaming Architecture)** | `red_comercial`, `operacion`, `asistente_ia` | Strict unidirectional dependency flow: `asistente_ia` -> `operacion` -> `red_comercial`. Never introduce circular ForeignKeys. |
| **ASGI Server & Static/Media** | **Granian (`--interface asgi`)** | Serve `/static` and `/media` directly from Granian's Rust HTTP layer (`--static-path-route` / `--static-path-mount`). Do not add WhiteNoise. |
| **Asset Serialization & Minification** | Custom `ManifestStaticFilesStorage` + `rjsmin` + `rcssmin` + `django-minify-html` | Minify `.js` and `.css` during `collectstatic` before MD5 filename hashing. Use standard `{% static %}` tags in templates. |
| **Database** | **SQLite 3 in WAL mode** | Configure `transaction_mode="IMMEDIATE"`, `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA busy_timeout=5000;`, and `PRAGMA foreign_keys=ON;`. |

---

## 3. Visual Design System & Dark Theme Palette

The UI uses **Pico CSS (v2 via CDN)** locked to a custom **Dark Theme (`<html lang="es" data-theme="dark">`)** derived directly from the official asset [`Logo verla horizontal.png`](./Logo%20verla%20horizontal.png).

### Extracted Brand & Dark-Mode Color Tokens

| Token | Hex | Role |
| :--- | :--- | :--- |
| `--verla-brand-indigo` | `#3B33BC` | Primary brand color extracted from `"VER"` and play icon circle in `Logo verla horizontal.png`. Used for primary CTAs, active tabs, and highlights. |
| `--verla-brand-indigo-hover` | `#524AE0` | Elevated indigo for `:hover` / `:focus` states and interactive links on dark surfaces. |
| `--verla-brand-navy` | `#070081` | Deep brand navy extracted from `"LA"` and lower arc in `Logo verla horizontal.png`. Used for header accents, badges, and secondary gradients. |
| `--verla-brand-white` | `#FFFFFF` | Pure contrast white (play icon triangle). Used for logo contrast and primary button text. |
| `--verla-bg-canvas` | `#08071A` | Main page background (`--pico-background-color`), deep midnight navy-tinted dark canvas. |
| `--verla-bg-surface` | `#11102E` | Card, modal (`<dialog>`), and table surface (`--pico-card-background-color`). |
| `--verla-bg-elevated` | `#1A1842` | Form inputs, table header rows, and hover states. |
| `--verla-border` | `#2A2768` | Subtle indigo border for cards, tables, and form controls (`--pico-border-color`). |
| `--verla-text-primary` | `#F4F4FB` | Primary readable body text (`--pico-color`). |
| `--verla-text-muted` | `#A09EC7` | Secondary labels, timestamps, and helper copy (`--pico-muted-color`). |
| `--verla-status-active` | `#10B981` | Semantic badge/indicator for `ACTIVO` and goal achievement (`>= 100%`). |
| `--verla-status-inactive` | `#F59E0B` | Semantic badge/indicator for `INACTIVO` and warning thresholds. |
| `--verla-status-blocked` | `#EF4444` | Semantic badge/indicator for `BLOQUEADO` and `409 Conflict` concurrency alerts. |

### UI/UX Guidelines
- Enforce `<html lang="es" data-theme="dark">` in the base layout and map `--pico-*` CSS custom properties to the `--verla-*` palette above.
- Display `Logo verla horizontal.png` in the top navigation bar over a subtle light/glass badge or contrast container so both `#3B33BC` and `#070081` remain crisp against the dark header.
- Prefer semantic HTML elements (`<main>`, `<article>`, `<section>`, `<table role="grid">`, `<dialog>`, `<nav>`) styled cleanly by Pico CSS + custom tokens, avoiding heavy JS frameworks.
- **Client Notifications & Alerts (SweetAlert2 CDN + Vanilla JS)**:
  - **Never use the browser's native `alert()`, `confirm()`, or `prompt()`**.
  - All feedback, operation confirmations (e.g. state changes, deletion, blocking, copy approvals), flash messages, and error notifications (including optimistic concurrency HTTP `409 Conflict` and rate-limit HTTP `429`) must be presented via **SweetAlert2 (v11 via CDN)** with Dark Theme styling integrated with the VERLA palette (`--verla-bg-surface`, `--verla-border`, `--verla-brand-indigo`).
  - Provide a centralized helper in vanilla JS (e.g. `window.VerlaAlert = { success, error, warning, confirm, conflict }`) loaded in `base.html` that automatically bridges Django `messages` into SweetAlert toasts or modals.

---

## 4. Mandatory Testing Contract (Every Feature Must Have Tests)

**Hard Rule**: **Every feature, model rule, view, concurrency guard, permission check, or AI service implemented MUST include its corresponding automated test before the task is considered complete.** No untested functionality is permitted.

### Testing Standards
1. **Test Runner**: Use Django's built-in test suite (`django.test.TestCase`, `TransactionTestCase`, `Client`, and `AsyncClient` based on Python's standard `unittest`) via `uv run python manage.py test` — zero external test dependencies required.
2. **Feature-to-Test Parity**:
   - **`red_comercial`**: Tests for CRUD of `Ciudad`, `Aliado`, `Coordinador`, and `Vendedor`; multi-city assignment; `AuditLog` generation on create/update/state change; RBAC permissions per role; access/operation blocking when `Vendedor.estado` is `BLOQUEADO` or `INACTIVO`; and **Optimistic Concurrency Control** verifying that stale `version` updates fail with HTTP `409 Conflict` without overwriting newer data.
   - **`operacion`**: Tests for monthly goal vs. actual result calculations aggregated by seller, coordinator, and ally; period offer date-range filtering; image upload handling; and visibility rules for active sellers.
   - **`asistente_ia`**: Async tests (`async def test_...` with `unittest.mock.AsyncMock` / `httpx.MockTransport`) verifying structured Gemini response parsing, fallback behavior on network/API failure, human-in-the-loop confirmation flow, and telemetry persistence in `AIAuditLog`.
3. **Verification Command**:
   ```bash
   uv run python manage.py test
   ```
   All tests must pass (`GREEN`) prior to closing any implementation unit or committing changes.

<div align="center">

# ⚡ shortly-url

### Fast, production-ready link shortening with serious click analytics.

**Python 3.12 · FastAPI (async) · PostgreSQL · Redis · React SPA** — fully dockerized, one-click deployable to [Render](https://render.com).

[![CI](https://github.com/Dani-Devlop/shortly-url/actions/workflows/ci.yml/badge.svg)](https://github.com/Dani-Devlop/shortly-url/actions/workflows/ci.yml)
[![Web front-end → GitHub Pages](https://github.com/Dani-Devlop/shortly-url/actions/workflows/pages.yml/badge.svg)](https://github.com/Dani-Devlop/shortly-url/actions/workflows/pages.yml)
![Tests](https://img.shields.io/badge/tests-321%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-informational)
![FastAPI](https://img.shields.io/badge/FastAPI-async-success)
![React](https://img.shields.io/badge/React%20%2B%20Vite-TS%20%2B%20Tailwind-cyan)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

[🌐 Live web app](https://dani-devlop.github.io/shortly-url/) · [📖 Interactive docs](https://shortly-url-api.onrender.com/docs) · [📮 Postman collection](./postman_collection.json) · [🚢 Deploy to Render](#-deploy-to-render)

</div>

---

## 📑 Contents

| | | |
|---|---|---|
| [Screenshots](#-screenshots) | [Live demo](#-live-demo) | [Feature highlights](#-feature-highlights) |
| [Web front-end (SPA)](#-web-front-end-spa) | [API reference](#-api-reference) | [Quickstart](#-quickstart) |
| [Configuration](#%EF%B8%8F-configuration) | [Architecture](#-architecture) | [Deploy to Render](#-deploy-to-render) |
| [Security notes](#-security-notes) | [License](#-license) | |

## 📸 Screenshots

<div align="center">

**Web dashboard — dark theme** (React SPA, GitHub Pages)

<img src="docs/screenshots/dashboard-dark.png" alt="shortly-url web dashboard — dark theme: link table with tags, sparklines, device bars, tag performance" width="820">

**Per-link analytics** &nbsp;·&nbsp; **QR studio**

<img src="docs/screenshots/analytics-modal.png" alt="Per-link analytics modal: totals, daily clicks chart, device mix, traffic sources" width="49%">&nbsp;
<img src="docs/screenshots/qr-studio.png" alt="QR studio: SVG/PNG formats, size, colour presets and pickers" width="49%">

**Fully responsive down to 390 px**

<img src="docs/screenshots/mobile.png" alt="Mobile view of the dashboard" width="30%">

</div>

## 🌐 Live demo

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Dani-Devlop/shortly-url)

> **⚠️ Heads-up:** Render hosts this demo on **your** Render account, so the API URLs below only
> answer **after** you apply the blueprint with the one-click button above (~2 minutes,
> zero configuration — `render.yaml` pre-wires the API, PostgreSQL and Redis together and
> sets `BASE_URL`, `MASTER_API_KEY` and `IP_HASH_SALT` for you).
> Until then Render's edge answers `404 Not Found` (`x-render-routing: no-server`).

Once deployed:

| What | URL |
|---|---|
| Web app (SPA dashboard) | https://dani-devlop.github.io/shortly-url/ |
| API | https://shortly-url-api.onrender.com |
| Dashboard (server-rendered) | https://shortly-url-api.onrender.com/ |
| Interactive docs (Swagger) | https://shortly-url-api.onrender.com/docs |
| Health probe | https://shortly-url-api.onrender.com/health |

> **🔑 Demo API key:** `shortly-demo-key-2024` — pre-set in `render.yaml` as the
> `MASTER_API_KEY` so the demo works out of the box. Rotate it for any serious use.
> Free Render instances sleep when idle — the first request may take ~30 s to wake up.

## ✨ Feature highlights

### 🔗 Core shortening

- **Shorten** any `http(s)` URL — auto-generated 7-char codes or validated custom aliases (`4–16` chars)
- **Bulk shorten** — `POST /api/shorten/bulk` creates up to 25 links per call with per-item `created` / `duplicate` / `error` results
- **Redis-cached redirects** — cache-aside layer over a PostgreSQL source of truth, `X-Cache: HIT|MISS` on every redirect
- **Query-param forwarding** — `/abc?utm_source=twitter` appends the params to the destination (incoming params win; destination UTMs preserved; fragment-safe)
- **UTM campaign templates** — store default UTM params per link (`utm_template`), applied on every redirect with clear precedence: explicit short-URL params > destination params > template (validated & normalised, 512-char cap)

### 📊 Click analytics

- **Totals & unique visitors** — total + distinct (`ip_hash`) clicks per link and across all links
- **Daily aggregation** — rolling windows of 1–90 days, zero-filled series (charts never lie about gaps)
- **Device analytics** — every click classified (`desktop | mobile | tablet | bot | other`); per-link breakdown or global mix in a window, with a **🤖 bots toggle** to drop crawler traffic
- **Referrers × device cross-tab** — top traffic sources in a rolling window, each item carrying clicks per device class for stacked bars
- **7×24 click-hour heatmap** — weekday × hour (UTC) grid with `total` + `peak` over a rolling window
- **Sparklines** — zero-filled daily click series per link, powering per-row trend charts
- **Tag rollups** — clicks / links / unique visitors aggregated per tag, zero-click tags included
- **Link comparison** — two links' totals, uniques and daily series side by side in one grouped query
- **Live activity feed** — the newest clicks across all links (device class, referrer host, truncated IP hash)
- **CSV exports** — all links, a single link's individual clicks, and the tag rollup

### 🗂 Link lifecycle

- **Edit anything** — `PATCH /api/links/{code}` repoints the destination, sets/clears expiry, UTM template or tags (cache-invalidated)
- **Link expiry** — expired codes answer `410 Gone` (enforced on both cache and DB paths; clicks no longer recorded)
- **Archive / restore (soft delete)** — stash a link without losing its history: redirects answer `410 Gone` (`error.code: link_archived`) while stats stay readable; both idempotent and cache-invalidated
- **Bulk actions** — archive / restore / delete up to 100 links per call with per-code `ok` / `not_found` results (unknown or foreign codes never fail the batch)
- **Paginated listing** — `GET /api/links` with `{items, total, limit, offset, status}`, filter by tag and by `active | archived | all`

### 🏷 Tags

- Up to **6 tags per link** (normalised: trimmed, lowercased, spaces → `-`, 2–24 chars)
- **Filter the list** with `GET /api/links?tag=docs`
- **Rename / merge** with `POST /api/tags/rename` (target duplicates merge, tag caps can never break) and **strip everywhere** with `DELETE /api/tags/{tag}` — both owner-scoped
- Colored per-tag chips (deterministic hue) in both dashboards, tag filter dropdown, tags column in CSV exports

### 🌍 Public & shareable

- **Public stats page** — `GET /s/{code}`: a shareable, no-auth HTML page per link with total/unique clicks, 14-day bar chart, device mix, top sources, recent clicks (referrer hosts only — **IP hashes are never shown**) and a QR code; styled 404 for unknown codes; `?bots=0` switches the click-derived panels to human-only traffic while hero totals stay truthful
- **QR codes** — `GET /{code}/qr`: SVG (default) or PNG, `?size=64–1024` px, recolourable with `?fg=` / `?bg=` hex params; public and cacheable

### 🛡 Privacy & resilience

- **IP privacy** — visitor IPs are salted & SHA-256 hashed before storage (truncated in UI and exports)
- **Per-key rate limiting** on `POST /api/shorten` (Redis fixed window, weighted cost for bulk calls, fails open if Redis is down) with `X-RateLimit-Limit` / `-Remaining` / `-Reset` headers and `Retry-After` on `429`
- **Graceful degradation** — Redis down → falls back to DB-only mode; DB down → clean `503/500` JSON errors
- **Structured errors** — every failure is `{"error": {"code": "...", "message": "..."}}`

### 🖥 Server-rendered dashboard (v11, ships with the API)

- Dark/light theme toggle (persisted), animated summary cards with tinted icon badges and a **weekly trend chip (▲▼ vs prev 7d)**
- Per-link 7-day sparklines, expiry badges, UTM campaign chips, colored #tag chips (click to filter) + tag filter dropdown
- Segmented status pills (Active / Archived (n) / All) that preserve sort/tag/page params
- **Bulk-select column + floating bulk-action bar**, per-row archive/restore with hatched archived rows, **undo toasts that survive page reloads**
- Keyboard shortcuts: `/` focuses the filter, `n` jumps to the create form
- Insights modal: 14-day mini bar chart, 7×24 heatmap, traffic-source bars stacked by device, device breakdown + chips per click, unique visitors
- **⚖️ Compare dialog** (dual sparklines + verdict), **QR dialog** (size 128–1024 px + ink/background pickers + 6 presets), admin **tag manager** (rename/merge/delete)
- Sticky actions column, hover accent bars, focus-visible rings, client-side filter with empty state, server-side pagination with page-size control, auto-refresh toggle (30 s, pauses while dialogs are open), quick API reference panel, bulk create, CSV downloads
- API key stays in your browser's sessionStorage

## 🖥 Web front-end (SPA)

`frontend/` holds a **React 18 + Vite + TypeScript + Tailwind CSS 4** single-page app that talks to the API over CORS using your `X-API-Key` (stored only in your browser's localStorage):

- **Connect screen** — point the app at any shortly-url deployment (defaults to the Render demo), validate the key, see live health (db/redis/version)
- **Dashboard** — stats strip, status pills (active/archived/all), server-side tag filter + pagination, client-side search, sortable click badges
- **Link management** — create (URL, custom alias, tags, expiry, UTM template), edit, archive/restore with **undo toasts**, bulk select → archive/restore/delete, delete confirmation
- **Analytics per link** — daily clicks area chart, device mix, referrer × device stacked sources, 7×24 click-hour heatmap, recent clicks feed, window selector (7/14/30/90 d), CSV export
- **Global panels** — 14-day sparklines per link, device breakdown (humans-only toggle), tag performance bars with CSV, live activity feed
- **Extras** — compare two links (dual chart + verdict), QR studio (SVG/PNG, size, colour presets + pickers), keyboard shortcuts (`n` new link, `/` search), dark/light theme, fully responsive down to 390 px

Hand-rolled SVG charts (no chart library) keep the whole bundle at **~63 KB gzipped**.

**Deployment:** every push to `main` builds the SPA via [`.github/workflows/pages.yml`](./.github/workflows/pages.yml) and publishes it to **GitHub Pages** → <https://dani-devlop.github.io/shortly-url/> (Pages must be set to *GitHub Actions* source — already configured).

**Local development:**

```bash
cd frontend && npm install && npm run dev
# then set the API URL in the connect screen, e.g. http://localhost:8000
```

## 🔌 API reference

All authenticated endpoints expect your key in the `X-API-Key` header. Errors are always structured: `{"error": {"code": "...", "message": "..."}}`.

### Shortening & link management

| Method | Path | Auth | Description |
|---|---|:-:|---|
| `POST` | `/api/shorten` | ✅ | Create a short link. Body: `{"url": "...", "custom_code": null, "expires_at": null, "utm_template": "utm_source=...", "tags": ["docs"]}` |
| `POST` | `/api/shorten/bulk` | ✅ | Shorten 1–25 URLs in one call — per-item `created` / `duplicate` / `error` results |
| `GET` | `/api/links` | ✅ | Paginated list — `{items, total, limit, offset, status}` (limit 1–100); `&tag=docs` filters by tag, `&status=archived\|all` by archive state |
| `GET` | `/api/links/{code}` | ✅ | Link detail: 20 most recent clicks (hashed IP prefix, user agent, referrer, device), all-time top-5 traffic sources + device cross-tab, device breakdown, unique clicks, zero-filled 14-day series (`daily_14d`), tags |
| `GET` | `/api/links/export` | ✅ | CSV download of all your links (click counts + tags + archived included) |
| `PATCH` | `/api/links/{code}` | ✅ | Update destination, expiry, UTM template and/or tags (null clears the field; `tags` replaces the whole set, `[]` clears all) |
| `DELETE` | `/api/links/{code}` | ✅ | Delete a link (cascades click rows, invalidates cache) |
| `POST` | `/api/links/{code}/archive` | ✅ | Soft-delete: stats stay readable, `GET /{code}` answers `410 Gone` (`link_archived`) until restore — idempotent |
| `POST` | `/api/links/{code}/restore` | ✅ | Undo the archive — redirects work again (idempotent) |
| `POST` | `/api/links/bulk-action` | ✅ | Archive / restore / delete up to 100 links — `{"action": "archive\|restore\|delete", "codes": ["..."]}`; per-code `ok`/`not_found` results |

### Redirects & public pages

| Method | Path | Auth | Description |
|---|---|:-:|---|
| `GET` | `/{code}` | — | `302` redirect (click recorded in background, `X-Cache: HIT\|MISS`, `410 Gone` when expired or archived; query params forwarded + link's UTM template applied) |
| `GET` | `/{code}/qr` | — | QR code for the short URL — `?format=svg` (default) or `?format=png`, `?size=64–1024` px (default 256), recolourable `?fg=34d399&bg=0f172a` (3/6-digit hex, `#` optional; cacheable, public) |
| `GET` | `/s/{code}` | — | **Public stats page** (shareable HTML) — total/unique clicks, 14-day chart, devices, top sources, recent clicks, QR — no API key; `?bots=0` = human-only panels |

### Click analytics

| Method | Path | Auth | Description |
|---|---|:-:|---|
| `GET` | `/api/stats/{code}` | ✅ | Total + unique clicks for a link |
| `GET` | `/api/stats/{code}/daily?days=14` | ✅ | Daily aggregated clicks (1–90 day window) |
| `GET` | `/api/stats/{code}/referrers?days=7&limit=10` | ✅ | Top traffic sources within a rolling window (1–90 days); each item carries a `devices` cross-tab (clicks per device class for that source) |
| `GET` | `/api/stats/{code}/hours?days=30` | ✅ | Zero-filled 7×24 heatmap (weekday × hour, UTC) — `{cells, total, peak}` |
| `GET` | `/api/stats/{code}/export` | ✅ | CSV download of a link's individual clicks (truncated IP hashes, referrer + device columns) |
| `GET` | `/api/stats/sparklines?days=7` | ✅ | Zero-filled per-link daily click series (1–30 days, up to 200 links) |
| `GET` | `/api/stats/devices?days=7` | ✅ | Device mix across your links in a rolling window (1–90 days); `&exclude_bots=true` drops crawlers |
| `GET` | `/api/stats/activity?limit=20` | ✅ | Newest clicks across all your links (code, device, referrer host, truncated IP hash) — newest first |
| `GET` | `/api/stats/compare?codes=a,b&days=14` | ✅ | Compare exactly two of your links — per-code totals, unique visitors and a zero-filled daily series (request order preserved) |

### Tags

| Method | Path | Auth | Description |
|---|---|:-:|---|
| `GET` | `/api/stats/tags?days=30` | ✅ | Click rollup per tag — `{tag, links, clicks, unique_visitors}` ranked by clicks (zero-click tags included) |
| `GET` | `/api/stats/tags/export` | ✅ | CSV download of the tag rollup |
| `POST` | `/api/tags/rename` | ✅ | Rename a tag across all your links — `{"from": "old", "to": "new"}`; links already carrying the target are merged |
| `DELETE` | `/api/tags/{tag}` | ✅ | Strip a tag from every one of your links (links are kept) |

### System

| Method | Path | Auth | Description |
|---|---|:-:|---|
| `GET` | `/health` | — | DB/Redis health probe (`503` when DB is down) |
| `GET` | `/docs` | — | Interactive Swagger docs |

### Quick example

```bash
curl -X POST http://localhost:8000/api/shorten \
  -H "X-API-Key: change-me-master-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/long/path"}'
# → 201 {"code":"aB3xK9m","short_url":"http://localhost:8000/aB3xK9m",...}

curl -i http://localhost:8000/aB3xK9m        # → 302 + Location, click counted
curl -H "X-API-Key: change-me-master-key" http://localhost:8000/api/stats/aB3xK9m
```

## 🚀 Quickstart

### Docker (recommended)

```bash
git clone https://github.com/Dani-Devlop/shortly-url.git
cd shortly-url
docker compose up --build
```

Open <http://localhost:8000> — the API runs with PostgreSQL 16 + Redis 7, migrations applied automatically.
Configure `MASTER_API_KEY` / `IP_HASH_SALT` via a `.env` file (see [`.env.example`](./.env.example)).

### Local development (no Docker)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Postgres + Redis, or degrade gracefully without them:
export DATABASE_URL="sqlite+aiosqlite:///./local.db"
export AUTO_CREATE_TABLES=true          # dev/demo only; use Alembic in production
export REDIS_URL=""                     # empty → cache & rate-limit disabled, DB-only mode
export MASTER_API_KEY="local-dev-master-key"

uvicorn app.main:app --reload
```

Run migrations against a real database with `alembic upgrade head`.

### Tests

```bash
pytest -v          # 321 tests, async SQLite + fakeredis, no services needed
ruff check .       # lint
python scripts/load_test.py --base http://localhost:8000 --code <code> --total 1000 --concurrency 50
```

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://shortly:shortly@localhost:5432/shortly` | Async DB DSN (`postgres://` / `postgresql://` DSNs are auto-upgraded to `+asyncpg`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis DSN; **empty string disables Redis** (fail-open mode) |
| `BASE_URL` | `http://localhost:8000` | Public base URL used to build `short_url` values |
| `MASTER_API_KEY` | `change-me-master-key` | API key of the bootstrap "master" user (created at startup) |
| `IP_HASH_SALT` | `change-me-ip-salt` | Salt for SHA-256 IP hashing |
| `RATE_LIMIT_REQUESTS` | `10` | Max `POST /api/shorten` per window per API key |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window |
| `CACHE_TTL_SECONDS` | `3600` | Redis TTL for `code → url` mappings |
| `CODE_LENGTH` | `7` | Length of generated short codes |
| `ENVIRONMENT` | `development` | `development` / `production` |
| `AUTO_CREATE_TABLES` | `false` | Dev/demo convenience: create tables from ORM metadata at startup |

## 🏗 Architecture

```
app/
├── main.py            # app factory, lifespan, exception handlers, router wiring
├── core/              # config (pydantic-settings), security, redis client, rate limiter
├── api/               # routers (links, redirects, stats, pages, health) + auth deps
├── models/            # SQLAlchemy 2.0 async models (User, Link, Click)
├── schemas/           # Pydantic v2 request/response models
├── services/          # business logic (link, redirect, click, stats)
├── db/                # async engine/session, declarative base, bootstrap
└── templates/         # Jinja2 dashboard + public stats page
alembic/               # migrations 0001–0005 (alembic upgrade head)
frontend/              # React 18 + Vite + TS + Tailwind 4 SPA (GitHub Pages)
tests/                 # pytest + pytest-asyncio suite (async SQLite, fakeredis)
```

**Redirect flow:**

```mermaid
flowchart LR
    A["GET /{code}"] --> B{"Redis<br/>cache"}
    B -- HIT --> E["302 redirect"]
    B -- MISS --> C["PostgreSQL<br/>lookup"] --> D["cache fill"] --> E
    E --> F["background task<br/>records click + counter"]
```

Deleting a link invalidates its cache entry, so deleted codes 404 immediately.

## 🚢 Deploy to Render

**One-click (recommended):** click the **Deploy to Render** button at the top of this README, review the blueprint summary, and hit **Apply**. Render then:

1. provisions **Web Service** (`shortly-url-api`), **PostgreSQL** (`shortly-url-db`, internal-only) and **Key Value** (`shortly-url-cache`, managed Redis) — all wired together by `render.yaml`;
2. builds with `pip install -r requirements.txt` (Python pinned to 3.12.9 via `PYTHON_VERSION`);
3. on boot runs `alembic upgrade head` (migrations) and starts `uvicorn app.main:app --host 0.0.0.0 --port $PORT`;
4. serves the dashboard at `https://shortly-url-api.onrender.com` — env vars are already pre-set (`BASE_URL`, demo `MASTER_API_KEY`, generated `IP_HASH_SALT`).

**Manual alternative:** Render dashboard → **New → Blueprint** → select `Dani-Devlop/shortly-url` → **Apply** (same result).

**Auto-deploys:** `autoDeploy: true` redeploys on every push to `main`. Optionally add a `RENDER_DEPLOY_HOOK_URL` repo secret and [`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml) will also trigger a deploy on each push.

**Troubleshooting:**

| Symptom | Cause | Fix |
|---|---|---|
| `404 Not Found` with header `x-render-routing: no-server` | No live deployment behind the URL — the blueprint was never applied (or every deploy failed) | Apply the blueprint via the button above; then check the web service's **Events**/**Logs** tabs in the Render dashboard |
| First request hangs ~30–60 s, then loads | Free instance woke from idle sleep | Nothing to do — subsequent requests are fast |
| `502`/`503` right after applying | Build/start still in progress | Watch the deploy logs until the service reports **Live** (`/health` returns 200) |
| Deploys succeeded before, now DB errors | Render **free PostgreSQL expires after 30 days** | Upgrade the database plan, or delete & recreate it — migrations re-run automatically on the fresh DB |
| Blueprint apply complains about existing resources | A previous partial apply left resources behind | Delete the stale `shortly-url-*` resources in the dashboard, then re-apply |

## 🔒 Security notes

- Parameterized queries everywhere (SQLAlchemy Core/ORM) — no string-built SQL
- Strict allow-lists: URL scheme (`http/https`), custom alias charset, short-code format
- Self-referencing URLs (pointing back at the service's own host) are rejected to prevent redirect loops
- Dashboard renders through Jinja2 auto-escaping; external links use `rel="noopener noreferrer"`
- Secrets are never committed: `.env` is gitignored, `.env.example` contains placeholders only

## 📄 License

MIT — see [LICENSE](./LICENSE).

---

<div align="center">

**⚡ shortly-url** · built by [Dani-Devlop](https://github.com/Dani-Devlop) · [⬆ back to top](#-shortly-url)

</div>

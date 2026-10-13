# ⚡ shortly-url

> **Owner:** [Dani-Devlop](https://github.com/Dani-Devlop) · **Profile:** https://github.com/Dani-Devlop

A fast, production-ready link shortener with click analytics — **Python 3.12 · FastAPI (async) · PostgreSQL · Redis**, fully dockerized and one-click deployable to [Render](https://render.com).

![CI](https://github.com/Dani-Devlop/shortly-url/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-informational)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

## 🌐 Live Demo

| What | URL |
|---|---|
| API | https://shortly-url-api.onrender.com |
| Dashboard (links + click counts) | https://shortly-url-api.onrender.com/ |
| Interactive docs (Swagger) | https://shortly-url-api.onrender.com/docs |
| Health probe | https://shortly-url-api.onrender.com/health |

> The demo becomes live once the repository is connected to Render via the included `render.yaml` blueprint (see [Deployment](#-deployment-on-render)). Free Render instances sleep when idle — the first request may take ~30s.

**Demo API key:** `shortly-demo-key-2024` — set this as the `MASTER_API_KEY` secret when deploying so the demo works out of the box. Rotate it for any serious use.

## 📦 Postman Collection

Import [`postman_collection.json`](./postman_collection.json) directly into Postman (File → Import), or use the raw URL:
https://github.com/Dani-Devlop/shortly-url/blob/main/postman_collection.json

The collection ships with variables `baseUrl` and `apiKey` and covers every endpoint, including the redirect flow.

## ✨ Features

- **Shorten** any `http(s)` URL — auto-generated 7-char codes or validated custom aliases (`4–16` chars)
- **Tags** — organise links with up to 6 tags per link (`tags` on create/PATCH, normalised: trimmed, lowercased, spaces → `-`, 2–24 chars); filter the list with `GET /api/links?tag=docs`; the dashboard renders per-tag **colored chips** (deterministic hue per tag), a tag filter dropdown, and the client filter matches tags too; links CSV export gains a `tags` column
- **Redirects** served from a Redis cache-aside layer with a PostgreSQL source of truth (`X-Cache: HIT|MISS` header on every redirect)
- **Update destinations & expiry** — `PATCH /api/links/{code}` repoints a code and/or sets/clears `expires_at`, invalidating its cache entry
- **Link expiry** — set `expires_at` on creation or via `PATCH`; expired codes answer `410 Gone` (enforced on cache and DB paths; clicks are no longer recorded)
- **Bulk shorten** — `POST /api/shorten/bulk` creates up to 25 links per call with per-item results
- **CSV export** — download your links (`/api/links/export`) or every individual click of a link (`/api/stats/{code}/export`)
- **Sparklines** — `GET /api/stats/sparklines` returns zero-filled daily click series (powering the dashboard's per-link trend charts)
- **Click-hour heatmap** — `GET /api/stats/{code}/hours?days=30` returns a zero-filled 7×24 (weekday × hour, UTC) grid with `total` + `peak`; rendered in the dashboard's insights modal and as a server-rendered **“When · last 30 days” panel on the public stats page** (aggregate only — privacy-safe)
- **Click analytics** — total clicks, daily aggregation, the 20 most recent clicks per link, and **referrer (traffic source) tracking** with a top-5 sources breakdown; recorded asynchronously via background tasks (zero redirect latency impact)
- **Unique visitors** — `unique_clicks` (distinct `ip_hash`) on `GET /api/stats/{code}`, link detail, and a **Unique visitors** summary card on the dashboard
- **Query-param forwarding** — `/abc?utm_source=twitter` redirects to the destination with `utm_source=twitter` appended (incoming params win; destination UTMs preserved; fragment-safe)
- **UTM campaign templates** — store default UTM params per link (`utm_template` on create/PATCH, e.g. `utm_source=newsletter&utm_campaign=launch`); applied on every redirect with clear precedence: explicit short-URL params > destination params > template (validated & normalised, 512-char cap)
- **Public stats page** — `GET /s/{code}` is a shareable, no-auth HTML page per link: total/unique clicks, 14-day bar chart, device mix, top sources, recent clicks (referrer hosts only — **IP hashes are never shown**) and a QR code; styled 404 for unknown codes; linked from every dashboard row via the ↗ share action
- **QR codes** at `GET /{code}/qr` — SVG (default) or PNG (`?format=png`), `?size=64–1024` px variants (default 256), public and cacheable
- **Bot filtering** — `GET /api/stats/devices?days=7&exclude_bots=true` drops crawler traffic; the dashboard's devices panel has a 🤖 one-click bots toggle (`?bots=0`)
- **Global activity feed** — `GET /api/stats/activity?limit=20` streams the owner's newest clicks across all links (device class, referrer host, truncated IP hash) and powers the dashboard's **🛰 Live activity panel**, which live-polls every 10 s while admin is unlocked
- **Device analytics** — every click is classified (from the user agent) as `desktop | mobile | tablet | bot | other`; get the mix per link (`device_breakdown` in link detail) or across all your links in a rolling window (`GET /api/stats/devices?days=7`); the dashboard shows a live stacked device bar
- **Windowed referrers** — `GET /api/stats/{code}/referrers?days=7&limit=10` ranks traffic sources inside a 1–90 day rolling window (`total` counts the whole window even beyond `limit`)
- **Paginated link listing** — `GET /api/links?limit=20&offset=0` returns `{items, total, limit, offset}`
- **Interactive dashboard v8** at `/` — dark/light theme toggle (persisted), animated summary cards with **tinted icon badges** and a **weekly trend chip (▲▼ vs prev 7d)**, per-link 7-day sparklines, expiry badges, **📣 UTM campaign chips per row**, **colored #tag chips per row** (click a chip to filter) + **tag filter dropdown**, **devices panel with stacked mix bar + bots toggle**, **🛰 live activity feed (server-rendered + 10 s live-poll)**, insights modal with a **14-day mini bar chart** + **7×24 click-hour heatmap** + **traffic-source bars + device breakdown + device chips per click + unique visitors**, client-side table filter (matches code/URL/tags), server-side pagination with page-size control, **auto-refresh toggle (30s, pauses while dialogs are open)**, centered animated dialogs, inline QR dialog (**size selector 128–1024 px**, preview/copy/download), quick API reference panel, bulk create, **custom-alias + tags fields on create**, CSV downloads, and create/edit/delete actions — create & edit dialogs manage destination, expiry, **tags** and the UTM template (API key stays in your browser's sessionStorage)
- **Per-key rate limiting** on `POST /api/shorten` (Redis fixed window, weighted cost for bulk calls, fails open if Redis is down) with **observability headers**: `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` on success and `Retry-After` on `429`
- **IP privacy** — visitor IPs are salted & SHA-256 hashed before storage (truncated in UI and exports)
- **Graceful degradation** — Redis down → falls back to DB; DB down → clean `503/500` JSON errors
- **Interactive docs** at `/docs`, health probe at `/health`, HTML dashboard at `/`

## 🔌 API Overview

| Method | Path | Auth (`X-API-Key`) | Description |
|---|---|---|---|
| `POST` | `/api/shorten` | ✅ | Create a short link. Body: `{"url": "...", "custom_code": null, "expires_at": null, "utm_template": "utm_source=...", "tags": ["docs"]}` |
| `POST` | `/api/shorten/bulk` | ✅ | Shorten 1–25 URLs in one call — per-item `created` / `duplicate` / `error` results |
| `GET` | `/{code}` | — | `302` redirect (click recorded in background, `X-Cache: HIT\|MISS`, `410 Gone` when expired; query params forwarded + link's UTM template applied) |
| `GET` | `/{code}/qr` | — | QR code for the short URL — `?format=svg` (default) or `?format=png`, `?size=64–1024` px (default 256; cacheable, public) |
| `GET` | `/s/{code}` | — | **Public stats page** (shareable HTML) — total/unique clicks, 14-day chart, devices, top sources, recent clicks, QR — no API key |
| `GET` | `/api/stats/{code}` | ✅ | Total + unique clicks for a link |
| `GET` | `/api/stats/{code}/daily?days=14` | ✅ | Daily aggregated clicks (1–90 day window) |
| `GET` | `/api/stats/sparklines?days=7` | ✅ | Zero-filled per-link daily click series (1–30 days, up to 200 links) |
| `GET` | `/api/stats/devices?days=7` | ✅ | Device mix (`desktop/mobile/tablet/bot/other`) across your links in a rolling window (1–90 days); `&exclude_bots=true` drops crawlers |
| `GET` | `/api/stats/activity?limit=20` | ✅ | Newest clicks across all your links (code, device, referrer host, truncated IP hash) — newest first |
| `GET` | `/api/stats/{code}/referrers?days=7&limit=10` | ✅ | Top traffic sources for a link within a rolling window (1–90 days) |
| `GET` | `/api/stats/{code}/hours?days=30` | ✅ | Zero-filled 7×24 heatmap (weekday × hour, UTC) over a rolling window (1–90 days) — `{cells, total, peak}` |
| `GET` | `/api/stats/{code}/export` | ✅ | CSV download of a link's individual clicks (truncated IP hashes, referrer + device columns) |
| `GET` | `/api/links?limit=20&offset=0` | ✅ | Paginated list of the user's links — `{items, total, limit, offset}` (limit 1–100); `&tag=docs` filters by tag |
| `GET` | `/api/links/export` | ✅ | CSV download of all the user's links (click counts included) |
| `GET` | `/api/links/{code}` | ✅ | Link detail incl. the 20 most recent clicks (hashed IP prefix, user agent, referrer, device) + all-time top-5 traffic sources + device breakdown + unique clicks + zero-filled 14-day daily series (`daily_14d`) + tags |
| `PATCH` | `/api/links/{code}` | ✅ | Update destination, expiry, UTM template and/or tags — `{"url": "...", "expires_at": null, "utm_template": "...", "tags": ["new"]}` (null clears the field; `tags` replaces the whole set, `[]` clears all) |
| `DELETE` | `/api/links/{code}` | ✅ | Delete a link (cascades click rows, invalidates cache) |
| `GET` | `/health` | — | DB/Redis health probe (`503` when DB is down) |
| `GET` | `/docs` | — | Interactive Swagger docs |

Errors are always structured: `{"error": {"code": "...", "message": "..."}}`.

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

## 🚀 Quickstart (Docker)

```bash
git clone https://github.com/Dani-Devlop/shortly-url.git
cd shortly-url
docker compose up --build
```

Open http://localhost:8000 — the API runs with PostgreSQL 16 + Redis 7, migrations applied automatically.
Configure `MASTER_API_KEY` / `IP_HASH_SALT` via a `.env` file (see `.env.example`).

## 🛠 Local Development (no Docker)

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

## 🧪 Tests

```bash
pytest -v          # 229 tests, async SQLite + fakeredis, no services needed
ruff check .       # lint
python scripts/load_test.py --base http://localhost:8000 --code <code> --total 1000 --concurrency 50
```

## ⚙️ Environment Variables

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
tests/                 # pytest + pytest-asyncio suite (async SQLite, fakeredis)
```

**Redirect flow:** `GET /{code}` → Redis cache lookup → (miss) PostgreSQL fetch + cache fill → `302` response → background task records the `clicks` row and increments the Redis counter. Deleting a link invalidates its cache entry, so deleted codes 404 immediately.

## 🚢 Deployment on Render

1. Push to `main` (already done by CI-friendly repo layout) and open [Render Blueprint](https://dashboard.render.com/select-repo?type=blueprint).
2. Select `Dani-Devlop/shortly-url` — Render reads `render.yaml` and provisions:
   - **Web Service** (`shortly-url-api`) — FastAPI, migrations run before start
   - **PostgreSQL** (`shortly-url-db`) — managed, internal-only
   - **Key Value** (`shortly-url-cache`) — managed Redis
3. Set the secret env vars on the web service: `MASTER_API_KEY` (e.g. the demo key above) and `BASE_URL` (`https://shortly-url-api.onrender.com`).
4. Optional: add a `RENDER_DEPLOY_HOOK_URL` secret to the repo and `.github/workflows/deploy.yml` will trigger deploys on every push.

## 🔒 Security Notes

- Parameterized queries everywhere (SQLAlchemy Core/ORM) — no string-built SQL
- Strict allow-lists: URL scheme (`http/https`), custom alias charset, short-code format
- Self-referencing URLs (pointing back at the service's own host) are rejected to prevent redirect loops
- Dashboard renders through Jinja2 auto-escaping; external links use `rel="noopener noreferrer"`
- Secrets are never committed: `.env` is gitignored, `.env.example` contains placeholders only

## 📄 License

MIT — see [LICENSE](./LICENSE).

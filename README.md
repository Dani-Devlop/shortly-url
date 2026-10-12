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
- **Redirects** served from a Redis cache-aside layer with a PostgreSQL source of truth (`X-Cache: HIT|MISS` header on every redirect)
- **Update destinations** — `PATCH /api/links/{code}` repoints a code, invalidating its cache entry
- **Click analytics** — total clicks, daily aggregation, and the 20 most recent clicks per link; recorded asynchronously via background tasks (zero redirect latency impact)
- **SVG QR codes** at `GET /{code}/qr` — pure-Python generation, no image deps
- **Interactive dashboard** at `/` — top links, sorting, copy-to-clipboard, QR, and create/edit/delete actions (API key stays in your browser's sessionStorage)
- **Per-key rate limiting** on `POST /api/shorten` (Redis fixed window, fails open if Redis is down)
- **IP privacy** — visitor IPs are salted & SHA-256 hashed before storage
- **Graceful degradation** — Redis down → falls back to DB; DB down → clean `503/500` JSON errors
- **Interactive docs** at `/docs`, health probe at `/health`, HTML dashboard at `/`

## 🔌 API Overview

| Method | Path | Auth (`X-API-Key`) | Description |
|---|---|---|---|
| `POST` | `/api/shorten` | ✅ | Create a short link. Body: `{"url": "...", "custom_code": null}` |
| `GET` | `/{code}` | — | `302` redirect to the original URL (click recorded in background, `X-Cache: HIT\|MISS`) |
| `GET` | `/{code}/qr` | — | SVG QR code for the short URL (cacheable, public) |
| `GET` | `/api/stats/{code}` | ✅ | Total clicks for a link |
| `GET` | `/api/stats/{code}/daily?days=14` | ✅ | Daily aggregated clicks (1–90 day window) |
| `GET` | `/api/links` | ✅ | List the authenticated user's links with click counts |
| `GET` | `/api/links/{code}` | ✅ | Link detail incl. the 20 most recent clicks (hashed IP prefix, user agent) |
| `PATCH` | `/api/links/{code}` | ✅ | Update the destination URL (invalidates the cache entry) |
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
pytest -v          # 61 tests, async SQLite + fakeredis, no services needed
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
└── templates/         # Jinja2 dashboard
alembic/               # migrations (alembic upgrade head)
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

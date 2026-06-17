# `api` — Headless FastAPI Backend

The FastAPI service that turns the `aishorts` core library into a multi-tenant web backend for **pdftoreel**. It owns everything the library deliberately doesn't: users, Firebase auth, credits and Stripe billing, file uploads, generation jobs, and the avatar/template/config catalog that the frontend reads.

The library does the actual work. This layer is a thin consumer of it: per request it looks up the avatars, template and provider config in the database, builds a `ShortsConfig`, and runs `generate_shorts_async` in a background task while streaming status back to the browser. For the pipeline internals (stages, providers, checkpoints, storage layout), see [`src/aishorts/README.md`](../src/aishorts/README.md); this document only covers the web layer.

```
browser ──HTTP──► FastAPI (api/main.py)
                     │  routers: public · users · upload · generate · admin
                     │  auth: Firebase JWT (api/auth.py)
                     │  db:   SQLModel → SQLite/Postgres (api/database.py, api/models.py)
                     ▼
              POST /api/generate ── credits check+deduct (atomic) ──► BackgroundTasks
                     │                                                     │
                     │  GET /api/status/{id}/stream (SSE) ◄── status_callback per stage
                     ▼                                                     ▼
              process_reel_task (api/tasks.py) ──► ShortsGenerator.generate_shorts_async()
                                                        └─ uploads finals to R2, returns URLs
```

---

## 1. Layout

| File | Responsibility |
|---|---|
| `main.py` | App entry point: CORS, router registration, root health check. |
| `auth.py` | Firebase Admin init + JWT verification dependencies (`get_current_user`, `get_current_admin_user`). |
| `database.py` | SQLModel engine + session (`get_session`), `create_db_and_tables()`. SQLite or Postgres by `DATABASE_URL`. |
| `models.py` | Full DB schema + request/response (read/create) models. |
| `tasks.py` | The background worker: DB ↔ core-library glue, status updates, credit refunds. |
| `file_conversion.py` | LibreOffice conversion of legacy office formats to PDF at upload time. |
| `populate_db.py` | Seeds avatars/templates from the CLI's JSON configs into the DB. |
| `backfill_thumbnails.py` | One-off: regenerate template thumbnails from preview videos. |
| `routers/public.py` | Unauthenticated catalog reads (avatars, templates, configs). |
| `routers/users.py` | `/me`, Stripe checkout + webhook (credits/subscriptions). |
| `routers/upload.py` | File upload → R2, per-user ownership. |
| `routers/generate.py` | Job creation, status polling, SSE stream, series CRUD. |
| `routers/admin.py` | Admin-only writes to the avatar/template/config catalog. |
| `alembic/` | Schema migrations (`alembic upgrade head`). |

---

## 2. Authentication & authorization

Auth is **Firebase Admin SDK** verifying a bearer JWT minted by the frontend.

- **Init** (`auth.py`): credentials come from `FIREBASE_CREDENTIALS_JSON` (a full JSON blob in the env, used on Railway) or, locally, the file at `FIREBASE_CREDENTIALS_PATH` (default `firebase_credentials.json`).
- **`get_current_user`** — reads `Authorization: Bearer <id_token>`, verifies it, returns the decoded token dict (`uid`, `email`, ...). Invalid tokens → `401` without leaking verifier internals.
- **`get_current_admin_user`** — additionally loads the `User` row and requires `role == ADMIN`, else `403`. Gates the whole `admin` router.
- **SSE exception**: `GET /api/status/{id}/stream` also accepts the token as a `?token=` query param, because the browser `EventSource` API cannot set headers.

**JIT provisioning**: there is no signup endpoint. The first time a valid token hits `/api/users/me`, `/api/upload`, or `/api/generate` and no `User` row exists, one is created with `credits = 90` and `role = user`. Admin is granted out-of-band (DB edit).

---

## 3. Database schema (`models.py`)

SQLModel (SQLAlchemy + Pydantic). Tables and the read/create models served over the API:

| Table | Key fields | Notes |
|---|---|---|
| `User` | `id` (Firebase UID, PK), `email`, `credits` (default **90**), `role` (`user`/`admin`), `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `plan_id`, `current_period_end` | Owns `series` and `uploads`. |
| `SubscriptionPlan` | `stripe_price_id` (PK), `name`, `credits`, `description` | Maps a Stripe price to a credit grant. |
| `Avatar` | `name` (unique), `data` (JSON) | `data` is a full `aishorts.Avatar` Pydantic model; `to_pydantic()` rehydrates it. |
| `VideoTemplate` | `name` (unique), `data` (JSON), `credits` (cost per reel, default 1), `preview_url`, `thumbnail_url` | `data` is an `aishorts.VideoTemplate`. |
| `GenerationConfig` | `name` (unique), `data` (JSON), `is_default` | Per-stage provider/model settings; `to_config_kwargs()` splats into `ShortsConfig`. |
| `ReelSeries` | `id`, `user_id`, `created_at`, `status`, `topic`, `thumbnail_url` | One generation **job**. Cascades to its reels, ordered by `sequence_number`. |
| `Reel` | `id`, `series_id`, `sequence_number`, `status`, `cloudflare_r2_url`, `local_path`, `title`, `description`, `thumbnail_url`, `duration` | One output video. |
| `UploadedFile` | `id`, `user_id`, `filename`, `url`, `key`, `content_type`, `created_at` | A user's uploaded source document in R2. |

`JobStatus` ∈ `Queued | Processing | Done | Failed` (on both `ReelSeries` and `Reel`).

`GenerationConfig.data` and `Avatar`/`VideoTemplate.data` mirror the core-library config objects, so the DB is just a serialized store of `ShortsConfig` inputs. `GenerationConfigRead` deliberately omits `data` (it may carry endpoints/credentials) since the listing is public.

---

## 4. API endpoints

All paths are prefixed `/api`. **Auth** column: 🌐 public, 🔑 any authenticated user, 🛡️ admin only.

### 🌐 Public catalog — `routers/public.py`
| Method | Path | Returns |
|---|---|---|
| GET | `/api/public/avatars` | All avatars. |
| GET | `/api/public/video-templates` | Templates as `VideoTemplateRead`: `credits`, `preview_url`, `thumbnail_url`, and the user-toggleable **tags** (resolved live from the edit template's `tag_assets` with their default state). |
| GET | `/api/public/generation-configs` | Configs (names/`is_default` only — no `data`). |

### 🔑 Users & billing — `routers/users.py`
| Method | Path | Action |
|---|---|---|
| GET | `/api/users/me` | Current user (JIT-provisions if new). |
| POST | `/api/users/create-checkout-session` | Creates/links a Stripe customer and opens a subscription Checkout session for a validated `price_id`. |
| POST | `/api/users/webhook` | Stripe webhook (signature-verified). Grants credits on `checkout.session.completed` and renewal `invoice.payment_succeeded`; marks `canceled` on `customer.subscription.deleted`. Hidden from the OpenAPI schema. |

> `add-credits` is **commented out** in the code (it was a dev/testing exploit risk). Credits now arrive only via Stripe or a manual DB edit.

### 🔑 Uploads — `routers/upload.py`
| Method | Path | Action |
|---|---|---|
| POST | `/api/upload/` | `multipart/form-data` file → R2 under `uploads/{uid}/{uuid}{ext}`. Returns `UploadedFileRead` (`key`, presigned `url`). Legacy office formats are converted to PDF first (§6). |
| GET | `/api/upload/{file_id}` | Fetch one of the caller's uploads. |
| DELETE | `/api/upload/{file_id}` | Delete from R2 + DB. |

Limits: `MAX_UPLOAD_SIZE` 50 MB; `ALLOWED_EXTENSIONS` covers docs (pdf/docx/pptx/xlsx/xls/csv/json/xml/html/epub/ipynb/msg/txt/md), images (jpg/png), audio (mp3/wav/m4a), and the legacy office set.

### 🔑 Generation — `routers/generate.py`
| Method | Path | Action |
|---|---|---|
| POST | `/api/generate` | Start a job. Body `GenerateRequest`. Returns `series_id` + `remaining_credits` immediately (non-blocking). |
| GET | `/api/status/{series_id}` | One-shot status (series + reels). |
| GET | `/api/status/{series_id}/stream` | **SSE** stream; emits the series JSON whenever it changes, closes on `Done`/`Failed`. Auth via header or `?token=`. |
| GET | `/api/series` | Caller's series, paginated (`offset`/`limit`), newest first. |
| GET | `/api/series/{series_id}` | One series the caller owns. |
| DELETE | `/api/series/{series_id}` | Delete a series (cascades to its reels). |

`GenerateRequest`: `template_name`, `avatar_names` (≤ 4), `amount` (1–7), `input_text?`, `files?`, `links?` (≤ 10), `config_name?` (else the default `GenerationConfig`), `enabled_tags?` (asset-type strings; `None` = template defaults).

`POST /api/generate` flow:
1. JIT-provision the user if needed.
2. **Validate `files`** — each must be a `key` or `url` the caller owns (see security note below).
3. **Validate `links`** — must be public `http(s)` (rejects non-global IPs, `localhost`, `.local`/`.internal`).
4. Look up the template, compute `total_cost = amount × template.credits`.
5. **Atomically** check-and-deduct credits with a conditional `UPDATE ... WHERE credits >= total_cost`; `0` rows affected → `402`. This closes the read-modify-write race between concurrent requests.
6. Create the `ReelSeries` + placeholder `Reel` rows (`Queued`).
7. Dispatch `process_reel_task(series_id, request, total_cost)` to `BackgroundTasks`.

### 🛡️ Admin catalog — `routers/admin.py`
| Method | Path | Action |
|---|---|---|
| POST | `/api/admin/avatars` | Create/update an avatar (validated by round-tripping through `to_pydantic()`). |
| POST | `/api/admin/video-templates` | Create/update a template. `multipart/form-data`: `name`, `data` (JSON), optional `preview` `.mp4`. The preview is uploaded to R2 and a thumbnail (frame at 1 s) extracted with ffmpeg and uploaded alongside it. `name` is path/key-validated to block traversal. |
| POST | `/api/admin/generation-configs` | Create/update a `GenerationConfig`; setting `is_default` unsets the previous default. |

#### Security notes worth knowing
- **File-ownership check** on `/api/generate`: `files` values are passed straight to the library's ingest layer, which will fetch `http(s)` URLs, read absolute local paths, and resolve arbitrary R2 keys. Restricting them to the caller's own uploads prevents SSRF, server-local file reads (`/etc/passwd`, credentials), and cross-tenant access — with the contents otherwise reflected back into the generated reel.
- **Link allow-listing** is a basic SSRF guard (no DNS resolution).
- **Atomic credit deduction** prevents overdraw under concurrency; **failed jobs refund** the full cost (idempotently — only once per series).

---

## 5. Background processing (`tasks.py`)

`process_reel_task` runs after the response is sent. DB work is wrapped in `run_in_threadpool` so the event loop stays free for the SSE streams.

1. **`_prepare_generation_config`** — marks the series + reels `Processing`; loads the selected `Avatar`s and `VideoTemplate` and the named (or default) `GenerationConfig` from the DB; builds a `ShortsConfig(avatars, video_template, enabled_tags, **gen_config_kwargs)`.
2. **Generate** — `ShortsGenerator(...).generate_shorts_async(amount, files, links, user_input, status_callback=...)`. The `status_callback` fires after each `PipelineStage` and writes interim data back to the DB via `_update_series_status`: a human-readable status string, plus `topic`, series/reel `thumbnail_url`, and reel `title`/`description` as soon as the SCRIPT stage produces them — so the frontend shows real content while assets are still rendering.
3. **`_save_generation_results`** — copies the returned `ReelSeriesOutput` into the DB: per reel `title`, `description`, `local_path`, `cloudflare_r2_url` (the presigned URL), `thumbnail_url`, `duration`; sets everything `Done`.
4. **On any exception** — `_mark_series_failed` sets the series + reels `Failed` and **refunds** `total_cost` credits (once).

> Unlike the older design, this layer no longer touches R2 for *outputs*: the core library uploads finals/thumbnails to R2 itself and returns the URLs. This service only persists them. Uploads of *source* files (§4) still use `boto3` directly.

Because generation runs in an in-process `BackgroundTask`, jobs do not survive a server restart and concurrency is bounded only by the process. A real queue/worker is the natural next step if that becomes a constraint.

---

## 6. File conversion (`file_conversion.py`)

MarkItDown (used by the library's ingest layer) reads modern office formats directly, so `.docx/.pptx/.xlsx/.xls` are stored as-is. The **legacy** formats `.doc/.ppt/.odt/.ods/.odp/.rtf` (`LEGACY_OFFICE_EXTENSIONS`) are converted to PDF at upload time with headless **LibreOffice** (`soffice --headless --convert-to pdf`, isolated user profile, 120 s timeout). LibreOffice must be installed on the server for those formats; everything else needs no extra binary.

---

## 7. Setup & configuration

### Install & run
```bash
pip install -e .                     # installs aishorts + api deps (fastapi, firebase-admin, stripe, ...)
playwright install chromium          # for motion-graphic question rendering (core lib)

uvicorn api.main:app --reload        # dev server on :8000
```

### Database
```bash
# Postgres (prod): apply migrations
alembic upgrade head

# or create tables directly (dev/SQLite)
python -c "from api.database import create_db_and_tables; create_db_and_tables()"

# seed the catalog from the CLI's JSON configs
python -m api.populate_db            # reads cli/configs/{avatars,video_templates}.json
```
`DATABASE_URL` selects the backend (default `sqlite:///database.db`; `postgresql://` is auto-rewritten to `postgresql+psycopg://`). Schema changes go through Alembic (`alembic revision --autogenerate -m "..."`); `create_db_and_tables()` only creates missing tables and does not migrate.

### Environment variables
This layer's own config:

| Concern | Variables |
|---|---|
| Database | `DATABASE_URL` |
| Firebase | `FIREBASE_CREDENTIALS_JSON` (prod) **or** `FIREBASE_CREDENTIALS_PATH` (local file) |
| CORS | `CORS_ORIGINS` (comma-separated) or `FRONTEND_URL` (default `http://localhost:3000`) |
| Storage (R2) | `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_DOMAIN` (optional; presigned URLs otherwise) |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |

Plus **all the provider keys the core library needs** for whichever providers your `GenerationConfig`s select (LLMs, Modal/RunPod workers, TTS, images, ...). See [`src/aishorts/README.md` §8](../src/aishorts/README.md). Only the keys for selected providers are required.

---

## 8. Frontend & related code

- **Frontend**: the React app in `web/` consumes these endpoints (public catalog to render the generate form, `/api/upload` for sources, `/api/generate` + the SSE stream for live progress, `/api/users` for billing).
- **CLI**: `cli/main.py` is the other consumer of the core library and the source of the seed configs (`cli/configs/avatars.json`, `cli/configs/video_templates.json`) used by `populate_db`.

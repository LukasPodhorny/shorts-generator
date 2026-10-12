# MCP production rollout runbook

How to ship the MCP server (`https://api.pdftoreel.com/mcp`): one-click OAuth
login, full tool parity, and durable RQ-backed generation jobs. Code changes
are already in the repo; this covers Heroku config, staging validation with
real AI clients, and rollback.

## 0. How the pieces fit

- The MCP server is mounted into the FastAPI app (`api/main.py`), so it
  deploys with the normal backend release. No separate service.
- OAuth login needs Postgres tables (Alembic migration
  `c4d2e8f1a9b3`, applied by the Procfile `release:` phase) and the React
  consent page (`/oauth/consent`, deployed with the Firebase-hosted app).
- Durable jobs need the Key-Value Store (Redis) add-on plus one `worker`
  dyno. Without `REDIS_URL` everything still works in-process (pre-queue
  behavior), so the queue can be enabled independently of the code deploy.

## 1. Config vars (Heroku)

Set on the app (`heroku config:set -a <app> ...`):

| Var | Value | Required |
|---|---|---|
| `MCP_BASE_URL` | `https://api.pdftoreel.com/mcp` | Yes (OAuth issuer/audience, metadata URLs) |
| `FRONTEND_URL` | `https://app.pdftoreel.com` | Yes (consent page redirect) |
| `MCP_JWT_SECRET` | Long random string (`openssl rand -hex 32`) | Yes (OAuth token signing; dev default is insecure) |
| `REDIS_URL` | Set automatically by the Redis add-on | For queue + OAuth throttling |
| `SOURCE_INGEST_TIMEOUT_SECONDS` | `20` (default) | No |
| `MCP_AUTH_RATE_LIMIT_PER_MINUTE` | `60` (default) | No |
| `MAX_CONCURRENT_GENERATIONS_PER_USER` | `2` (default) | No |

Rotating `MCP_JWT_SECRET` invalidates all outstanding OAuth tokens (users
reconnect once); Firebase login is unaffected.

## 2. Staging first

Use a staging Heroku app (or pipeline review app) with its own Redis, the
same Firebase project (create a dedicated test user), and the consent page
served from a Firebase preview channel or localhost via
`FRONTEND_URL=https://<preview-channel>--<project>.web.app`.

```bash
heroku addons:create heroku-redis:mini -a <staging-app>
heroku config:set -a <staging-app> \
  MCP_BASE_URL=https://<staging-app>.herokuapp.com/mcp \
  FRONTEND_URL=<preview-url> \
  MCP_JWT_SECRET=<random>
git push staging main   # or: heroku pipelines:promote
heroku ps:scale worker=1 -a <staging-app>
heroku logs --tail -a <staging-app>   # watch release (migrations) + boot
```

## 3. Staging validation checklist

Backend basics:

- `GET https://<staging>/` returns the API greeting.
- `GET https://<staging>/mcp/.well-known/oauth-protected-resource` returns
  resource metadata pointing at the staging issuer.
- `heroku ps -a <staging-app>` shows `web` and `worker` up.

OAuth + tools with real clients (the highest-risk interop surface):

1. Claude.ai: add a custom connector with the staging `/mcp` URL, click
   Connect, log in with the test user in the browser, approve. Ask it to
   list templates and check the credit balance.
2. ChatGPT: same via its MCP/apps connector flow.
3. Claude Code / Cursor: add the staging URL as a streamable-HTTP MCP
   server and run one generation end to end.
4. Deny once from the consent page: the client must show access denied,
   and no grant row may exist.
5. Revoke from Account → Connected apps mid-session: the next tool call
   must fail immediately.

Durability:

6. Start a 1-reel generation over MCP, then `heroku ps:restart web -a
   <staging-app>` mid-run. The job must still complete (worker log shows
   it) and the status poll must reach Done.
7. `POST /api/generate` from the webapp with the worker scaled to 0 and
   Redis present: expect HTTP 503, series Failed, credits refunded (the
   enqueue path fails loudly instead of hanging). Then scale the worker
   back to 1.
8. Expired/short timeout sanity: `plan_reels` with several slow links must
   return within ~30 s (ingest budget), skipping slow sources.

## 4. Production rollout (ordered)

1. Deploy the backend (migrations run in `release:`; OAuth endpoints go
   live but are unused until clients connect).
2. Deploy the webapp (consent page + Connected apps + connect hint).
3. `heroku addons:create heroku-redis:mini` on the prod app (sets
   `REDIS_URL`; dispatches switch to the queue on next deploy/restart —
   dynos pick up new config on restart, so `heroku ps:restart` if the
   add-on was attached after the deploy).
4. Set `MCP_BASE_URL`, `FRONTEND_URL`, `MCP_JWT_SECRET` on prod.
5. `heroku ps:scale worker=1`.
6. Smoke test on prod: connect once from Claude Code with your own
   account, run `get_me` + `list_video_templates`, start a 1-reel test
   generation, revoke the grant afterwards.
7. Monitor for a day: `heroku logs --tail` for `pdftoreel.mcp` tool lines,
   `pdftoreel.worker` job lines, and any 503s; watch worker memory during
   a 7-reel job.

## 5. Rollback (each step is independent)

- Queue problems: `heroku ps:scale worker=0` and unset `REDIS_URL`, then
  restart web dynos. Dispatch falls back to in-process; in-flight queued
  jobs wait until a worker returns (or expire per RQ defaults).
- OAuth problems: no flag to pull; the endpoints are additive and REST is
  untouched. Worst case, revoke leaked trust by rotating `MCP_JWT_SECRET`
  (all OAuth tokens die; users reconnect).
- Code problems: redeploy the previous release (`heroku releases:rollback`).
  The OAuth tables stay (harmless when unused); downgrade only if you must
  (`alembic downgrade -1` removes the four tables).

## 6. Ops notes

- Manual refund fallback (Heroku shell): the refund path is
  `fail_series_with_refund(series_id, total_cost)` in `api/tasks.py`; call
  it via `heroku run python -c` with the series id and its deducted cost.
  It is idempotent (never double-refunds a Failed series).
- RQ dashboard: none bundled. Queue depth via `heroku run rq info -u
  "$REDIS_URL"`; failed jobs via `rq info` (all failures already refund
  through `on_job_failure`, but check the registry after incidents).
- Stuck series (no worker, no refund): any series left in Queued/Processing
  with no live job can be failed+refunded with the same helper.
- Cost deltas: Key-Value Store Mini add-on plus one worker dyno; the web
  dyno must be always-on (a sleeping dyno sleeps the MCP endpoint too).
- Public connector directories (Claude/ChatGPT) may require app review or
  branding for listed integrations; private custom connectors work with no
  approval and are the v1 target.

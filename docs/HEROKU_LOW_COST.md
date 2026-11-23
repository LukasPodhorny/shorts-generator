# Heroku low-cost deployment

For a personal, lightly used app, run **one Basic web dyno plus Essential-0
Postgres**: $7 + $5 = **$12/month** at full-month rates. Heroku bills by
provisioned time, so this estimate does not include other apps, add-ons, or
one-off dynos. The current month's charges already incurred are not reversed.

Set `GENERATION_QUEUE=postgres` on the API. The web dyno stores each generation
request and its deducted credit cost in `generationjob`, then processes one job
at a time. Jobs interrupted by a dyno restart are retried once. If the second
attempt is interrupted, the series is marked Failed and its credits are
refunded. A retry restarts generation and may repeat external provider calls.
The API and generation share the Basic dyno's 512 MB RAM; watch for Heroku R14
or R15 memory errors during a full-size render. The MCP OAuth limiter uses an
in-memory counter when Redis is absent, appropriate for this single-web-dyno
setup; the counter resets on restart.

## Rollout

1. Deploy the code and run `alembic upgrade head` (the Heroku release command
   already does this). Confirm the web dyno boots and `/` responds.
2. Check the old RQ queue and StartedJobRegistry. Wait until both are zero.
3. Set `GENERATION_QUEUE=postgres` on `pdftoreel-api`. Confirm the web dyno
   restarts and the Postgres worker loop is active.
4. Scale `worker=0`. Submit one small test generation and verify that a
   `generationjob` row appears, then disappears when the series reaches Done
   or Failed.
5. Destroy only the `heroku-redis:mini` add-on after confirming no old RQ
   work remains. This removes `REDIS_URL` and restarts the web dyno. Confirm
   OAuth throttling still responds with 429 after repeated requests, and
   verify `heroku ps` shows only `web.1` on Basic.

Do not switch to Eco for this job setup merely to save more: Heroku sleeps an
Eco worker together with an idle Eco web dyno after 30 minutes without web
traffic, which can interrupt a long render. The one Basic web dyno does not
sleep.

## Rollback

To restore separate worker processing, create a Mini Heroku Key-Value Store,
unset `GENERATION_QUEUE`, and scale `worker=1`. Wait for a running Postgres
job to finish first; do not run it concurrently on both backends. Existing
Postgres `generationjob` rows remain in the database and can be processed by
temporarily re-enabling `GENERATION_QUEUE=postgres`.

The original in-process fallback remains available when neither Redis nor
`GENERATION_QUEUE` is set, but it does not persist requests across restarts.

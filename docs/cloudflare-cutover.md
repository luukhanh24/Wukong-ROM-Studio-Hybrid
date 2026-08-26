# Cloudflare Workers + D1 cutover runbook

This runbook moves production writes from Render/PostgreSQL to
`wukong-control-plane` without cancelling an active ROM build.

## Resources

- Worker production: `wukong-control-plane`
- Worker staging: `wukong-control-plane-staging`
- D1 production: `wukong-control-plane-db`
- D1 staging: `wukong-control-plane-staging-db`
- Mini App: `https://wukong-rom-studio.vercel.app`
- Preferred workers.dev account subdomain: `wukong-rom-studio-1678823419`
- Fallback subdomain: `wukong-rom-studio-1678823419-2675075b`

## Required GitHub configuration

Repository variables:

- `CLOUDFLARE_ACCOUNT_ID`
- `WUKONG_CLOUDFLARE_STAGING_URL`
- `WUKONG_CLOUDFLARE_PRODUCTION_URL`
- `WUKONG_TELEGRAM_MINI_APP_API_URL`
- `WUKONG_TELEGRAM_WEB_APP_URL=https://wukong-rom-studio.vercel.app`

Repository/environment secrets:

- `CLOUDFLARE_API_TOKEN`
- `WUKONG_ACTIONS_CALLBACK_SECRET`
- `WUKONG_TELEGRAM_BOT_TOKEN`
- `WUKONG_TELEGRAM_WEBHOOK_SECRET`
- `WUKONG_GITHUB_TOKEN`
- `WUKONG_GOOGLE_CLIENT_ID`
- `WUKONG_GOOGLE_CLIENT_SECRET`
- `WUKONG_GOOGLE_REFRESH_TOKEN`

The Cloudflare token must be limited to the account and to Workers Scripts,
Workers Routes, D1 and account settings required by Wrangler.

## Migration

1. Deploy the Render-compatible release containing metadata-driven read-only
   mode.
2. Query PostgreSQL and wait until `wukong_jobs` has no status outside
   `succeeded`, `failed`, or `cancelled`. Do not cancel a job for cutover.
3. Enable Render read-only without printing the connection string:

   ```bash
   python -m tools.migrate_postgres_to_d1 set-render-mode --mode read_only
   ```

4. Verify write routes return HTTP 503 with
   `code=maintenance_read_only`, while `/healthz`, `/readyz`, `/v1/me` and job
   history remain readable.
5. Export the repeatable-read snapshot:

   ```bash
   python -m tools.migrate_postgres_to_d1 export-postgres \
     --output .wkstudio/migration/postgres-snapshot.json
   python -m tools.migrate_postgres_to_d1 generate-d1-sql \
     --snapshot .wkstudio/migration/postgres-snapshot.json \
     --output .wkstudio/migration/d1-import.sql
   ```

6. Apply Worker migrations, import the SQL into staging, export the local or
   remote D1 SQLite database, and verify:

   ```bash
   python -m tools.migrate_postgres_to_d1 snapshot-sqlite \
     --database .wkstudio/migration/d1.sqlite \
     --output .wkstudio/migration/d1-snapshot.json
   python -m tools.migrate_postgres_to_d1 verify \
     --expected .wkstudio/migration/postgres-snapshot.json \
     --actual .wkstudio/migration/d1-snapshot.json \
     --attestation-sql .wkstudio/migration/cutover-attestation.sql
   ```

   Every table must have the same row count and canonical SHA-256, and the D1
   database must remain below 4 GiB. Apply `cutover-attestation.sql` only after
   verification succeeds. Production cutover refuses to continue unless that
   attestation exists, the source snapshot records Render as `read_only`, and
   the snapshot contains zero non-terminal jobs.

## Staging and production

1. Run the `Control Plane · Cloudflare Workers + D1` workflow for `staging`.
2. Run Worker contract tests, Mini App browser tests, the 100-concurrency /
   2,000-request load smoke, and a synthetic Actions job.
3. Import the verified snapshot into production D1 and deploy the exact release
   SHA.
4. Change `WUKONG_TELEGRAM_MINI_APP_API_URL` to the production Worker URL and
   keep `WUKONG_TELEGRAM_WEB_APP_URL` on Vercel.
5. Rebuild Vercel and verify the generated HTML contains the Worker origin.
6. Call Telegram `setWebhook` with the existing secret token and the Worker
   `/telegram/webhook` URL.
7. Run another synthetic Actions job and verify bootstrap, progress, terminal
   state, one Telegram notification, and a direct Drive/cloud artifact URL.

## Rollback

Before any production D1 write, point Telegram and the Mini App API variable
back to Render and set Render to `read_write`.

After D1 has accepted production writes, first lock the Worker deployment.
Export D1 to a SQLite snapshot, create a canonical migration snapshot with
`snapshot-sqlite`, and reverse-import it only while Render remains read-only:

```bash
python -m tools.migrate_postgres_to_d1 import-postgres \
  --snapshot .wkstudio/migration/d1-production-snapshot.json \
  --replace
python -m tools.migrate_postgres_to_d1 set-render-mode --mode read_write
```

Only then restore the Telegram webhook and Mini App API origin to Render.

## Retention

Keep Render and the private PostgreSQL snapshot read-only for seven full days
after cutover. If Worker/D1 metrics and synthetic builds remain healthy,
suspend Render. Do not delete the Render service or PostgreSQL snapshot.

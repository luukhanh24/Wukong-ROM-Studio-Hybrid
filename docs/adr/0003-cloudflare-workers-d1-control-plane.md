# Replace the Render control plane with Cloudflare Workers and D1

Status: Accepted — supersedes ADR 0001 for production writes.

The production Mini App remains on Vercel, while the authenticated API,
Telegram webhook and notification delivery move to a TypeScript Cloudflare
Worker backed by D1. GitHub Actions continues to execute ROM builds and Google
Drive continues to store source mirrors, recipes, checkpoints and artifacts.

The Worker owns Telegram access, permanent Build Allowance accounting, Accepted
Jobs, events, build locks, callback receipts and notification outbox state.
Accepted Job creation is one D1 batch guarded by database constraints and
triggers so an idempotent retry cannot consume a second credit or bypass the
user/device lock. GitHub Actions receives only `job_id` and
`recipe_ref=worker://<job_id>` at dispatch, verifies its run during bootstrap,
and then receives the private recipe.

ROM ZIP metadata is inspected on the user's device with the vendored fflate
0.8.3 library. The Worker provides only short-lived, SSRF-protected and
budgeted byte ranges. Metadata sent by the browser remains advisory; the
GitHub runner probes the original source again before execution.

PostgreSQL is retained only as the migration and rollback source. Cutover
requires zero non-terminal jobs, a repeatable-read snapshot, exact per-table
row counts and canonical SHA-256 matches, a healthy staging Worker, and a
synthetic bootstrap-to-terminal Actions run. Render is kept read-only for
seven days after cutover, then suspended rather than deleted.

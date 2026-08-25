# Cloud Run production control plane

Cloud Run hosts the stateless Wukong Mini API and Telegram webhook. The Mini App stays on Vercel, durable control-plane state stays in PostgreSQL, ROM execution stays in private GitHub Actions, and sources/artifacts stay on Google Drive.

The production service is fixed to `asia-southeast1`, 2 vCPU, 2 GiB, concurrency 40, minimum 0 and maximum 2 instances. Minimum 0 allows scale-to-zero on unused days; startup CPU boost reduces cold-start latency. A request may still see a cold start after idle time.

## One-time bootstrap

Use Google Cloud Shell from the repository root, or install and initialize the current Google Cloud CLI locally. The operator needs permission to create a project, link billing, enable APIs, manage IAM/service accounts, create budgets and deploy Cloud Run.

```bash
export PROJECT_ID=wukong-rom-studio-1678823419
export REGION=asia-southeast1
export GITHUB_REPOSITORY=luukhanh24/Wukong-ROM-Studio-Hybrid
export BILLING_ACCOUNT_ID=000000-000000-000000
bash deploy/cloud-run/bootstrap.sh
```

The script is idempotent. It creates the Artifact Registry repository, Cloud Run placeholder, runtime/task/deployer service accounts, GitHub Workload Identity Federation, two Cloud Tasks queues, empty Secret Manager containers and a USD 5 billing budget with USD 1 and USD 5 thresholds. It also writes the public project/API variables and WIF secrets to GitHub when `gh` is authenticated.

Billing must already be active. A budget sends alerts; it does not cap or stop spending.

## Add secret versions

Never paste secret values into command history. Load them into environment variables or files in the protected Cloud Shell session, then pipe them to Secret Manager:

```bash
printf '%s' "$DATABASE_URL" | gcloud secrets versions add wukong-database-url --data-file=-
printf '%s' "$WUKONG_TELEGRAM_BOT_TOKEN" | gcloud secrets versions add wukong-telegram-bot-token --data-file=-
printf '%s' "$WUKONG_GITHUB_TOKEN" | gcloud secrets versions add wukong-github-token --data-file=-
gcloud secrets versions add wukong-rclone-config --data-file="$HOME/rclone.conf"
printf '%s' "$WUKONG_ACTIONS_CALLBACK_SECRET" | gcloud secrets versions add wukong-actions-callback-secret --data-file=-
printf '%s' "$WUKONG_ACTIONS_CALLBACK_SECRET" | gh secret set WUKONG_ACTIONS_CALLBACK_SECRET --repo "$GITHUB_REPOSITORY" --body-file=-
```

`DATABASE_URL` must be the provider's pooled PostgreSQL connection string. `WUKONG_ACTIONS_CALLBACK_SECRET` must be the same random value in GCP and GitHub; use at least 32 random bytes. The GitHub token needs access to dispatch and inspect Actions runs in the private repository. The rclone file must contain the `wukong-gdrive` remote.

During the seven-day rollback window, add that same callback secret to Render as `WUKONG_ACTIONS_CALLBACK_SECRET`. This keeps Actions progress and terminal callbacks compatible before cutover and after an emergency rollback.

Confirm these repository values exist:

- Variable `GCP_PROJECT_ID`
- Variable `WUKONG_CLOUD_RUN_API_URL`
- Secret `GCP_WORKLOAD_IDENTITY_PROVIDER`
- Secret `GCP_DEPLOYER_SERVICE_ACCOUNT`
- Secret `WUKONG_ACTIONS_CALLBACK_SECRET`

The existing variable `WUKONG_TELEGRAM_MINI_APP_API_URL` must still point to Render until cutover.

## First deploy and smoke test

Run the `Cloud Run Production · API + Vercel` workflow manually on the commit to release. The workflow runs the full suite, publishes an immutable image, deploys the exact SHA, verifies `/healthz`, configures Telegram commands/webhook through an OIDC Cloud Task, then publishes Vercel.

Before allowing the Telegram configuration task to switch production traffic, use a temporary bot token for a rehearsal or omit that final task during the rehearsal. For the real cutover, verify:

```bash
curl -fsS "$WUKONG_CLOUD_RUN_API_URL/healthz"
gcloud run services describe wukong-mini-api --region=asia-southeast1 \
  --format='yaml(status.url,status.latestReadyRevisionName,spec.template.spec.containerConcurrency,spec.template.spec.containers[0].resources)'
gcloud tasks queues describe wukong-telegram --location=asia-southeast1
gcloud tasks queues describe wukong-dispatch --location=asia-southeast1
```

Health must report the released SHA and `"stateBackend":"postgresql"`. Open the Mini App as admin, as an Approved User and as a Pending User. Create one small test job, verify the running progress updates about every 10 seconds, inspect a different historical job, and verify the final Drive/cloud artifact link.

## Production cutover

Perform these changes together during a quiet window:

1. Verify the Cloud Run revision and PostgreSQL state.
2. Set GitHub variable `WUKONG_TELEGRAM_MINI_APP_API_URL` to the exact Cloud Run URL.
3. Run `Telegram Mini App · Vercel` and verify the generated page embeds the Cloud Run origin.
4. Enqueue `/internal/tasks/configure-telegram` for the released SHA, or rerun the Cloud Run production workflow, to register commands and switch the Telegram webhook.
5. Test `/start`, Mini App authentication, Pending/Approved access, job submission, progress and artifact download.

Do not suspend Render yet. Keep its database and secrets unchanged for seven days. After the observation period, make `Control Plane Production · Render + Vercel` manual-only and suspend Render auto-deploy; retain its configuration as the rollback target.

## Rollback to Render

If Cloud Run fails after cutover:

1. Set `WUKONG_TELEGRAM_MINI_APP_API_URL` back to the known healthy Render URL.
2. Run the Vercel Mini App workflow and wait for its production health check.
3. Trigger the Render deployment/binding workflow so Telegram commands and webhook point back to Render.
4. Verify `/healthz`, `/start`, access state and one job lookup.
5. Leave Cloud Run deployed with minimum 0 while diagnosing; it incurs no idle instance charge, but Artifact Registry and external PostgreSQL/provider charges can still apply.

Because both services use the same PostgreSQL database and Drive history, rollback does not copy job or user state. Never run Render long polling and the Cloud Run webhook against the same bot simultaneously.

## Operations and cost checks

Review Cloud Run request latency, instance count, 5xx logs, Cloud Tasks retry/dead-letter behavior, PostgreSQL pool usage and the billing budget weekly during the first month. The service intentionally uses one Gunicorn worker with 16 threads per instance and a PostgreSQL pool capped at 8 connections, keeping two-instance database usage bounded.

Artifact Registry keeps the two newest releases and deletes older images after seven days. Render can be suspended after the seven-day rollback window; the GitHub workflow should remain available for manual emergency rollback.

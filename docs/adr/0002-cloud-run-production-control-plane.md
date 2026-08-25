---
status: accepted
---

# Use Cloud Run and Cloud Tasks for the production control plane

Production keeps Vercel, PostgreSQL, private GitHub Actions and Google Drive, but moves the authenticated API and Telegram webhook from Render to Cloud Run in `asia-southeast1`. Cloud Run uses 2 vCPU, 2 GiB, concurrency 40, zero minimum and two maximum instances; PostgreSQL-backed sessions, task leases and progress ledgers plus OIDC-authenticated Cloud Tasks preserve correctness across cold starts and concurrent instances. Render remains a seven-day rollback target because switching the API origin and Telegram webhook is coordinated and not instantly reversible.

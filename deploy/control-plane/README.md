# Always-on Telegram control plane

This service keeps the Telegram bot and Mini App available when the Windows PC
is off. It stores only control-plane state and dispatches heavy ROM work to
GitHub Actions; source ROMs, content packs, checkpoints and artifacts stay on
Google Drive. Production uses a static Vercel Mini App, the Render API/bot, and
private PostgreSQL for jobs, access control, events, and Telegram UI state.

## Production requirements

- A Vercel project rooted at this repository. `vercel.json` publishes only the
  generated `.vercel-static` directory.
- The Render `wukong-mini-api` Docker service described by `render.yaml`.
- A private PostgreSQL database (Neon or managed Render PostgreSQL) whose pooled
  connection string is stored only in Render as `DATABASE_URL`.
- A fine-grained GitHub token and the same private rclone Google Drive
  configuration used by Actions. These are Render secrets, never frontend values.

Set `WUKONG_TELEGRAM_WEB_APP_URL` in Render to the exact Vercel production URL.
The API permits only that HTTPS origin. Set `WUKONG_GITHUB_REPOSITORY` privately
in Render; do not hard-code a personal owner/repository in frontend files or the
public blueprint. Production refuses to start without `DATABASE_URL`, and
`/healthz` must report `"stateBackend":"postgresql"` before the Telegram Mini
App is switched to the new origin.

Vercel deployments need only the public API origin in
`WUKONG_TELEGRAM_MINI_APP_API_URL`. Connecting Vercel to a private GitHub
repository does not publish the repository identity in the generated bundle.
The CI privacy test scans the output for personal GitHub references.

## Optional self-hosted VPS

## One-time VPS bootstrap

Install Docker Engine with Compose v2, create a dedicated SSH deploy user, then
run the bootstrap script as root:

```bash
sudo ./deploy/control-plane/bootstrap_host.sh wukong-deploy
```

Reconnect that user and verify `docker compose version`. The account needs no
general `sudo`; it owns only `/opt/wukong-control-plane` and belongs to Docker's
privileged group. Limit its SSH key and firewall access to trusted operators.

Create the DNS record before deployment and verify its address. Record the real
SSH host key from the VPS console with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`;
do not obtain the trusted value using `ssh-keyscan` over an untrusted network.

Configure these repository variables:

- `WUKONG_MINI_API_DOMAIN`: API hostname without `https://`.
- `WUKONG_VPS_PORT`: SSH port, normally `22`.
- `WUKONG_TELEGRAM_WEB_APP_URL`: exact Vercel Mini App URL.
- `WUKONG_RCLONE_REMOTE`: normally `wukong-gdrive`.

Configure these repository secrets:

- `WUKONG_VPS_HOST`, `WUKONG_VPS_USER`, `WUKONG_VPS_SSH_KEY`.
- `WUKONG_VPS_KNOWN_HOSTS`: trusted OpenSSH known-hosts line from the VPS console.
- `WUKONG_TELEGRAM_BOT_TOKEN` and `WUKONG_TELEGRAM_ADMIN_IDS`.
- `WUKONG_TELEGRAM_WEBHOOK_SECRET`: stable random 32–256 character value.
- `WUKONG_GITHUB_TOKEN` and `RCLONE_CONFIG_B64`.
- `WUKONG_ACTIONS_CALLBACK_SECRET`: the same HMAC secret configured in GitHub
  Actions and, during Cloud Run migration, GCP Secret Manager.

The GitHub token needs Actions read/write and repository Metadata read. The
workflow token updates repository variables after public health verification.

Run the manually triggered `Control Plane Production` workflow. It deploys the
exact Git commit over host-key-verified SSH, validates Telegram/GitHub/Drive,
registers the authenticated Telegram webhook and waits for internal and public
HTTPS health. Vercel deploys the static Mini App independently. A failed container release
automatically restores the previous immutable image/release.

## Manual deploy

The manual path is useful for initial diagnostics. Automated production deploys
are preferred because they bind the API and bot to one verified release SHA.

```bash
cd deploy/control-plane
cp .env.example .env
mkdir -p secrets
chmod 700 secrets
editor .env
editor secrets/rclone.conf
chmod 600 .env secrets/rclone.conf
docker compose up -d --build
docker compose ps
curl https://mini-api.example.com/healthz
```

Do not put `.env` or `secrets/rclone.conf` in Git. PostgreSQL preserves the
allowlist, recipes, jobs, events, and Telegram UI state across image upgrades
and host restarts. The `wukong-state` volume is only a local rollback source and
scratch area; it is not the production database backup. The container entrypoint copies the
root-readable rclone bind mount to a mode `0600` runtime file, then drops to the
unprivileged `wukong` user before starting Python.

Keep `WUKONG_TELEGRAM_WEB_APP_URL` set to the exact Vercel URL because the API
uses that origin as its only CORS origin. A custom domain can be attached in
Vercel later; update this Render variable and Telegram's Web App URL together.

## Backup and recovery

Use the PostgreSQL provider's encrypted backup/point-in-time recovery for jobs,
access, events, and UI state. Google Drive remains the durable store for ROM
sources, content packs, checkpoints, and build artifacts. The legacy JSON state
is imported once and marked complete in PostgreSQL; restarting the service does
not restore revoked users or overwrite newer UI preferences.

Production uses an authenticated Telegram webhook. Registering it disables the
old `getUpdates` polling path, so a Windows bot process cannot steal updates.
Windows remains usable as a normal Studio client and optional local build
machine; it is not part of Mini App availability.

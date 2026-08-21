# Always-on Telegram control plane

This service keeps the Telegram bot and Mini App available when the Windows PC
is off. It stores only control-plane state and dispatches heavy ROM work to
GitHub Actions; source ROMs, content packs, checkpoints and artifacts stay on
Google Drive.

## Requirements

- A small always-on Linux VPS (1 vCPU / 1 GiB RAM is sufficient for the control plane).
- Docker Engine with Compose v2.
- A DNS `A`/`AAAA` record such as `mini-api.example.com` pointing to the VPS.
- Inbound TCP 80 and TCP/UDP 443 allowed. Caddy obtains and renews TLS automatically.
- A fine-grained GitHub token and the same private rclone Drive configuration used by Actions.

## Deploy

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

Do not put `.env` or `secrets/rclone.conf` in Git. The Compose volume
`wukong-state` preserves allowlist, recipes, jobs, events and watcher state
across image upgrades and host restarts. The container entrypoint copies the
root-readable rclone bind mount to a mode `0600` runtime file, then drops to the
unprivileged `wukong` user before starting Python.

Set repository variable `WUKONG_TELEGRAM_MINI_APP_API_URL` to the same public
HTTPS origin, then run the `Telegram Mini App Pages` workflow. Keep
`WUKONG_TELEGRAM_WEB_APP_URL` set to the exact GitHub Pages URL because the API
uses it as the only allowed CORS origin.

Until that repository variable exists, the Pages workflow intentionally skips
deployment and leaves the last known-good Mini App online.

## Upgrade and backup

```bash
git pull --ff-only
docker compose up -d --build
docker run --rm -v control-plane_wukong-state:/state -v "$PWD":/backup alpine \
  tar czf /backup/wukong-state-backup.tgz -C /state .
```

Only one control-plane instance may long-poll the same Telegram bot token at a
time. Once VPS deployment is healthy, stop the bot inside the Windows app or
remove its Telegram credentials. Windows remains usable as a normal Studio
client and optional local build machine.

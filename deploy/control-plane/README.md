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
- `WUKONG_TELEGRAM_WEB_APP_URL`: exact GitHub Pages Mini App URL.
- `WUKONG_RCLONE_REMOTE`: normally `wukong-gdrive`.

Configure these repository secrets:

- `WUKONG_VPS_HOST`, `WUKONG_VPS_USER`, `WUKONG_VPS_SSH_KEY`.
- `WUKONG_VPS_KNOWN_HOSTS`: trusted OpenSSH known-hosts line from the VPS console.
- `WUKONG_TELEGRAM_BOT_TOKEN` and `WUKONG_TELEGRAM_ADMIN_IDS`.
- `WUKONG_TELEGRAM_WEBHOOK_SECRET`: stable random 32–256 character value.
- `WUKONG_GITHUB_TOKEN` and `RCLONE_CONFIG_B64`.

The GitHub token needs Actions read/write and repository Metadata read. The
workflow token updates repository variables after public health verification.

Run the manually triggered `Control Plane Production` workflow. It deploys the
exact Git commit over host-key-verified SSH, validates Telegram/GitHub/Drive,
registers the authenticated Telegram webhook, waits for internal and public
HTTPS health, and only then publishes GitHub Pages. A failed container release
automatically restores the previous immutable image/release.

## Manual deploy

The manual path is useful for initial diagnostics. Automated production deploys
are preferred because they bind API, bot and Pages to one verified release SHA.

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

The production workflow sets repository variable
`WUKONG_TELEGRAM_MINI_APP_API_URL` only after the public endpoint reports the
expected release. Keep `WUKONG_TELEGRAM_WEB_APP_URL` set to the exact GitHub
Pages URL because the API uses that origin as its only CORS origin.

Until that repository variable exists, the Pages workflow intentionally skips
deployment and leaves the last known-good Mini App online.

## Backup

```bash
docker run --rm -v control-plane_wukong-state:/state -v "$PWD":/backup alpine \
  tar czf /backup/wukong-state-backup.tgz -C /state .
```

Production uses an authenticated Telegram webhook. Registering it disables the
old `getUpdates` polling path, so a Windows bot process cannot steal updates.
Windows remains usable as a normal Studio client and optional local build
machine; it is not part of Mini App availability.

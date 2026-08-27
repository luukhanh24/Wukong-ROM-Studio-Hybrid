# Render Free control plane

This deployment keeps the Telegram Mini App API available without a Windows
PC or a privately managed VPS. ROM builds still run on GitHub Actions. The
Render service only authenticates Telegram users, probes ROM metadata,
dispatches jobs, and shows their history.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/xuankhanh24/Wukong-ROM-Studio-Hybrid)

## First deployment

1. Open the Deploy to Render button and sign in with GitHub.
2. Keep the `free` service plan selected.
3. Supply the four prompted secrets:
   - `WUKONG_TELEGRAM_BOT_TOKEN`: the existing `@WK_build_bot` token.
   - `WUKONG_TELEGRAM_ADMIN_IDS`: the numeric Telegram user/chat ID already
     configured for the project.
   - `WUKONG_GITHUB_TOKEN`: a fine-grained or classic token that can dispatch
     Actions and manage Actions repository variables for this repository.
   - `WUKONG_RCLONE_CONFIG_CONTENT_B64`: base64 of the existing rclone config.
4. Create the Blueprint and wait until `/healthz` reports `status: ready`.
   Startup validates the Telegram account, GitHub Actions permission, and
   Google Drive remote before the API is allowed to become healthy.

The service discovers its generated `https://*.onrender.com` URL at runtime,
registers the Telegram webhook, writes the verified API origin to the GitHub
repository variable `WUKONG_TELEGRAM_MINI_APP_API_URL`, and triggers a fresh
GitHub Pages deployment. The fallback workflow **Bind Render Free Control
Plane** can perform the last binding step manually if the GitHub token lacks
permission to update repository variables.

## Free-tier behavior

Render can spin a free web service down after 15 minutes without inbound
traffic. Opening the bot or Mini App wakes it again; the Mini App allows enough
time for a cold start before reporting an API timeout. GitHub Actions sends an
authenticated terminal callback after each build, which also wakes the service
to synchronize the public artifact and send the Telegram completion message.
State is also snapshotted continuously while the service is awake because the
free plan does not expose a configurable shutdown grace period.

The free filesystem is ephemeral. Small control-plane files are therefore
snapshotted to `WukongROM/control-plane/state-v1.zip` on the configured Google
Drive and restored before the API starts. The allowlist includes only:

- job manifests, recipes, and event logs;
- Telegram access approvals;
- language, session, and short job-reference preferences.

Bot tokens, GitHub tokens, rclone credentials, ROM files, and build artifacts
are never included in this snapshot.

Render's free service terms and limits can change. A small VPS remains the
recommended option for guaranteed 24/7 response with no cold start, but it is
not required for this deployment.

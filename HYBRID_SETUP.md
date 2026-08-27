# Wukong ROM Studio Hybrid setup

## 1. Google Drive

Install rclone and create an OAuth remote named `wukong-gdrive`:

```text
rclone config
```

Use a private Google OAuth `client_id` and `client_secret` for this remote. The
shared rclone Drive client is being retired during 2026 and is not suitable for
a long-running build service.

The expected private layout is:

```text
wukong-gdrive:WukongROM/
  content-packs/
  sources/
  recipes/
  jobs/
  checkpoints/
  artifacts/
```

Generate, upload and verify content-packs:

```text
python content_pack_tool.py index --content-root . --index content-packs/index.json
python content_pack_tool.py index --content-root C:\WukongROMStudio\Content --index content-packs/index.json --pack MOD/ColorOS_16.0.9
python content_pack_tool.py upload --content-root . --index content-packs/index.json --pack MOD/ColorOS_16.0.8
python content_pack_tool.py install --content-root verification-content --index content-packs/index.json --pack MOD/ColorOS_16.0.8
python content_pack_tool.py verify --content-root verification-content --index content-packs/index.json --pack MOD/ColorOS_16.0.8
```

`upload` creates one deterministic `.tar.zst` object per pack, uploads it
sequentially, then compares its size and Google Drive MD5 before returning
success. It then downloads, safely extracts and checks every per-file SHA-256
by default. Omit `--pack` only to upload every pack. Use
`--skip-download-verify` only for emergency diagnostics, never for publishing.

Do not delete local content or publish the clean Git history until every pack
has been downloaded and verified from Drive.

## 2. GitHub repository and secrets

Create public repository `xuankhanh24/Wukong-ROM-Studio-Hybrid`. Configure:

- `RCLONE_CONFIG_B64`: Base64 of the complete rclone config.
- `WUKONG_GITHUB_TOKEN`: fine-grained token with Actions read/write, Metadata
  read and Administration read for the hybrid repository.

Keep Actions workflow permissions at `contents: read`. Workflows containing
secrets must not run for untrusted forks. All external actions in this project
are pinned to immutable commit SHAs.

The Windows Settings page can store the repository, GitHub token and rclone
configuration using Windows DPAPI. These values are never returned by REST.

## 3. Self-hosted Linux runner

Add repository labels:

```text
self-hosted, linux, x64, wukong-rom
```

Minimum verified capacity is 150 GiB free disk, 16 GiB memory and 8 logical
CPUs. Install Python 3.13 and allow the runner account to use `sudo apt-get`.
Run `python3 tools/runner_preflight.py` after registration. An explicit
`self-hosted-linux` recipe fails immediately when that runner is unavailable.
`github-auto` instead falls back to a maximized `ubuntu-24.04` runner, so a
missing private runner does not leave the Telegram job queued forever.

Hosted recipes use `ubuntu-24.04`, must estimate at most 10 GiB workspace and
must retain at least 4 GiB free disk after dependencies/content are installed.

## 4. Telegram daemon

For a Mini App that remains available while Windows is off, deploy the
standalone webhook control plane using
[deploy/control-plane/README.md](deploy/control-plane/README.md). Production
uses the manually triggered `Control Plane Production` workflow; Windows is no
longer in the Mini App request path. The packaged Windows backend can still
host the controller for local-only development, but two processes must not
share the same `Data/Jobs/hybrid` directory.

Set these only in the Windows process/user environment or encrypted desktop
store:

```text
WUKONG_TELEGRAM_BOT_TOKEN=...
WUKONG_TELEGRAM_ADMIN_IDS=123456789,987654321
WUKONG_TELEGRAM_WEB_APP_URL=https://wukong-rom-studio.vercel.app/
WUKONG_TELEGRAM_MINI_APP_API_BIND=127.0.0.1
WUKONG_TELEGRAM_MINI_APP_API_PORT=8766
```

Start long polling:

```text
python telegram_bot_daemon.py
```

Send `/start` to open the button menu. The bot registers Telegram's slash-command
suggestions automatically and provides a Vietnamese/English build wizard for
execution target, ROM source, device, MOD version, preset, paged MOD selection
and confirmation. Local Windows jobs read the configured installed Content root.
GitHub jobs list only MOD versions whose verified archive is present in
`content-packs/index.json`; Actions downloads that private archive from Drive and
checks it before building.
Language preference and non-sensitive wizard state are stored in
`Data/telegram-ui-state.json`; signed URL query strings remain memory-only.

The same menu prepares a Telegram reply-keyboard button that opens the bilingual
Mini App. Its transport is the dedicated Mini App API on port `8766`.
Every request validates Telegram's signed `initData`, checks the allowlist and
enforces job ownership. Recipe submission therefore remains inside the Mini App;
`sendData` is retained only as a compatibility fallback when the public API has
not been deployed.

Enable GitHub Pages with **Source: GitHub Actions**. The production workflow
deploys Caddy/API on the VPS, validates the exact release SHA, sets this
repository variable, then publishes the Mini App:

```text
WUKONG_TELEGRAM_MINI_APP_API_URL=https://mini-api.example.com
```

The app never receives the bot token, GitHub token, webhook secret or rclone
configuration. Build, mirror, jobs, event history, artifact links, cancel,
resume, cloud and diagnostics stay inside the Mini App; terminal reports are
also delivered to the owning Telegram user.

For a no-cost deployment with a managed HTTPS hostname, use the Render
Blueprint in [`render.yaml`](render.yaml) and follow
[`deploy/render/README.md`](deploy/render/README.md). It accounts for Render's
idle spin-down and ephemeral filesystem by restoring the small control-plane
state from Google Drive and by letting the terminal GitHub Actions job wake the
service. Heavy ROM work remains on GitHub runners.

Set `WUKONG_TELEGRAM_CONTENT_ROOT` when the installed content is not in the
default `C:\WukongROMStudio\Content` location.

Admins approve users with `/approve <telegram_user_id>`. Users may create builds
without JSON, browse their jobs, refresh progress, view events, download
artifacts, cancel and resume only their own jobs. `/submit <recipe JSON>` remains
available for advanced use. Admins may control all jobs and manage the allowlist.
The VPS registers an authenticated Telegram webhook after credential preflight;
this disables competing long polling from an old Windows bot process.

## 5. Recipe and CLI

Recipe tasks are `source_mirror`, `build` and `artifact_publish`. Sources are
`local`, `http`, `https` or `rclone`. Execution is `local-windows`,
`github-auto`, `github-hosted` or `self-hosted-linux`.

```text
python wukong_cli.py validate --recipe recipe.json
python wukong_cli.py submit --recipe recipe.json --channel cli --subject local --role admin
python wukong_cli.py execute <job-id>
```

Recipe JSON cannot contain tokens, passwords, credentials or requester roles.
Identity is supplied by the authenticated Windows session, Telegram allowlist
or GitHub runner.

### Build resilience (Actions-friendly defaults)

These knobs reduce the most common hybrid failures without putting multi-GB
assets back into Git:

| Behaviour | Default on GitHub Actions | Override |
|-----------|---------------------------|----------|
| Reject missing MODs before downloading the ROM | on (`WUKONG_DROP_MISSING_MODS=0`) | set `1` only for an explicit best-effort recovery |
| Fall back to maximized `ubuntu-24.04` when the self-hosted runner is offline (large estimates) | on for `github-auto` / `github-hosted` | explicit `self-hosted-linux` still requires the runner |
| Continue build if a checkpoint upload hits Drive quota | on | set `WUKONG_DISABLE_CLOUD_CHECKPOINTS=1` to skip uploads entirely |
| Continue with a clean workspace if checkpoint restore fails | on | n/a |

Hosted jobs cache the pinned Linux toolchain, common recovery/image content and
Python packages. ROM source archives and private per-version MOD packs are not
put in GitHub cache; they remain checksum-verified downloads from the configured
Drive to avoid stale or cross-version builds.

Still required before a real build: valid `RCLONE_CONFIG_B64`, uploaded
content-packs for `MOD/<version>`, `STARK/common`, `Flash_script/common`,
`copy-image/v1`, `OFX/v1`, `TWRP/v1`, and a
ROM source that is `http(s)` or `rclone` (never a local Windows path on Actions).

Validate MODs against installed content before downloading a multi-GB ROM:

```text
python -m tools.validate_recipe_content --recipe recipe.json --content-root . --drop-missing --rewrite
python -m tools.validate_recipe_content --recipe recipe.json --content-root . --strict
```

### Detailed workflow dispatch

`Wukong Hybrid Build` accepts either a private `recipe_ref` or detailed manual
fields. When `recipe_ref` is empty, Actions materializes a validated BuildRecipe
from `task`, `device`, `source_uri`, optional source checksum/size, MOD pack,
preset, individual MODs, enabled pipeline steps, debloat paths, runner policy,
workspace estimate, ZIP packaging, Drive publishing and Telegram notification.
The generated recipe is uploaded privately to
`wukong-gdrive:WukongROM/recipes/<job-id>.json` before routing.

For Daniel Springer OTA pages, use the stable build page itself as `source_uri`,
for example:

```text
https://roms.danielspringer.at/index.php?view=ota&build=8429f705a32868eeabdddea9
```

The downloader resolves that page immediately before transfer and follows the
short-lived OPlus CDN link with resume and parallel ranges. Do not persist the
temporary CDN URL in a recipe. For this PKG110 build, set `source_size_bytes` to
`8680370027`; the known upstream MD5 is
`6fb0095cc9c07dbdb74074c87cbb643f` (SHA-256 may remain empty and is computed
after download).

## 6. Retention and sharing

- Sources, content-packs and recipes stay private.
- Build artifacts receive an rclone public link when publishing is enabled.
- Checkpoints are deleted after 7 days.
- Job manifests/logs are deleted after 30 days.
- Sources and artifacts remain until an administrator removes them.

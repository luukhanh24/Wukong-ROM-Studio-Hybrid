# Wukong ROM Studio Hybrid setup

## 1. Google Drive

Install rclone and create an OAuth remote named `wukong-gdrive`:

```text
rclone config
```

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
python content_pack_tool.py upload --content-root . --index content-packs/index.json
python content_pack_tool.py install --content-root verification-content --index content-packs/index.json --pack MOD/ColorOS_16.0.8
python content_pack_tool.py verify --content-root verification-content --index content-packs/index.json --pack MOD/ColorOS_16.0.8
```

`upload` downloads every uploaded pack into a temporary directory and verifies
the complete file set, sizes and SHA-256 values before returning success.

Do not delete local content or publish the clean Git history until every pack
has been downloaded and verified from Drive.

## 2. GitHub repository and secrets

Create public repository `luukhanh24/Wukong-ROM-Studio-Hybrid`. Configure:

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
Run `python3 tools/runner_preflight.py` after registration. If the runner is
offline or does not meet the profile, large recipes fail before dispatch.

Hosted recipes use `ubuntu-24.04`, must estimate at most 10 GiB workspace and
must retain at least 4 GiB free disk after dependencies/content are installed.

## 4. Telegram daemon

The packaged Windows backend hosts this controller automatically. Run the
standalone daemon only when the desktop backend is stopped; two processes must
not share the same `Data/Jobs/hybrid` directory.

Set these only in the Windows process/user environment or encrypted desktop
store:

```text
WUKONG_TELEGRAM_BOT_TOKEN=...
WUKONG_TELEGRAM_ADMIN_IDS=123456789,987654321
```

Start long polling:

```text
python telegram_bot_daemon.py
```

Admins approve users with `/approve <telegram_user_id>`. Users may submit full
recipes and control only their own jobs. Admins may control all jobs and manage
the allowlist. `TelegramWebhookAdapter` is available for a later VPS/webhook
deployment without changing orchestration logic.

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

## 6. Retention and sharing

- Sources, content-packs and recipes stay private.
- Build artifacts receive an rclone public link when publishing is enabled.
- Checkpoints are deleted after 7 days.
- Job manifests/logs are deleted after 30 days.
- Sources and artifacts remain until an administrator removes them.

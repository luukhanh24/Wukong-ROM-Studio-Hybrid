# Wukong ROM Studio Hybrid

One shared ROM orchestration module for the native Windows application,
GitHub Actions and Telegram. All channels use `BuildRecipe v1` and the same
pipeline implementation; only their interaction adapters differ.

Core capabilities:

- Local file, HTTP/HTTPS and private rclone ROM sources with SHA-256 checks.
- OPlus OTA resolver support with safe redirects and resumable 16-range downloads.
- Local Windows, GitHub-hosted Ubuntu 24.04 and qualified self-hosted Linux.
- Private Google Drive content/source/checkpoint storage and public artifact links.
- Owner-scoped job status, events, cancel and checkpoint resume.
- GitHub checkpoints are streamed as one TAR plus SHA-256 metadata, avoiding
  Google Drive's per-file throttling while preserving safe resume validation.
- Native WinUI Hybrid Cloud page, headless CLI and Telegram admin/user bot.
- Verified one-click content synchronization from Windows to Drive and the
  public GitHub manifest, including shared `STARK` and flash-script packs.

See [HYBRID_SETUP.md](HYBRID_SETUP.md) for setup and
[LEGACY_PROVENANCE.md](LEGACY_PROVENANCE.md) for the legacy snapshot.

Local ROM build studio for Windows with a Flask backend and an HTML/CSS/JavaScript dashboard.

See [STUDIO_README.md](STUDIO_README.md) for setup, CLI, dashboard, Telegram, and build instructions.

The WinUI 3 desktop host, runtime packaging, content-pack tooling and Inno
Setup installer are documented in [desktop/README.md](desktop/README.md).

## Quick start

```bat
RUN_UI.bat
```

The dashboard binds to localhost. Runtime jobs, logs, generated ROMs, local credentials, and signing keys are intentionally excluded from Git.

## Private content packs

The public repository intentionally contains no ROM sources, build artifacts or
Git LFS objects. Large `MOD`, `STARK`, `Flash_script`, `copy-image`, `OFX` and `TWRP` assets are stored as
private Google Drive content packs with a size and SHA-256 manifest.

Configure the `wukong-gdrive:` rclone remote, then follow
[HYBRID_SETUP.md](HYBRID_SETUP.md) to install and verify only the content packs
needed for a build. The test workflow creates harmless placeholder files; those
fixtures must never be used for a real ROM build.

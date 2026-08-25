# Wukong ROM Studio Hybrid

## Product

Wukong ROM Studio Hybrid is a ROM build and source-mirroring tool with one shared orchestration core. It is operated through a Windows desktop app, GitHub Actions, a headless CLI, and a Telegram bot.

## Users and access

- Administrators manage approved Telegram users, runners, secrets, content packs, and all jobs.
- Approved users create and manage only their own jobs.
- Channel adapters provide the authenticated identity; recipes never determine ownership.

## Telegram surface

- Platform: native Telegram chat controls plus an authenticated Telegram Mini App. Both submit requests to the same controller and orchestration core.
- Mode: Operate. The primary task is to create and monitor a ROM build with one-handed mobile interaction.
- Vietnamese is the default language; English can be selected instantly and is remembered per Telegram user ID.
- Common flows use buttons, a step-by-step chat wizard, or the bilingual Build Control Ledger Mini App. Raw `/submit <JSON>` remains available as an advanced compatibility path.
- The Mini App maps the Windows operating model into four focused destinations: Studio, Jobs, Catalog, and System. Catalog gives operators a searchable, read-only view of the same device, content-pack, fixed default release label, and MOD data used by Studio and every runner; ROM-library operations remain chat fast paths.
- Job details expose refresh, a compact event preview, an explicit full-log view with complete sanitized event data, artifact, cancel, resume, and back actions only when relevant.
- Errors name the problem and provide a direct recovery action.

## Build wizard

The chat wizard gathers the complete task envelope. The Mini App is build-focused: it gathers execution target, ROM source, device, MOD pack, fixed default release-version label, preset, individual MOD selections, pipeline stages, packaging, publishing, notification, and confirmation without exposing separate source-mirror or artifact-publish task modes. An operator may override the release label for the current job only; the MOD pack default remains unchanged. The selected label is copied into the new job so history and logs retain the exact context. Chat MOD selection is paginated for one-handed use; the Mini App exposes the complete searchable build plan in one responsive surface. Local files are permitted only for eligible Windows/admin jobs; GitHub jobs use HTTP(S) or a private Google Drive reference and only advertise MOD versions backed by a verified private content-pack. Cloud UI state is stored by Telegram user ID in private PostgreSQL (with a local file fallback for Windows development) and never contains credentials.

## Product constraints

- The orchestration package remains the single source of truth for validation, routing, status, ownership, cancel, and resume.
- Telegram callback data is short, versioned, and never grants access by itself.
- Mini App requests are capped at Telegram's 4096-byte `sendData` limit and ownership always comes from the authenticated Telegram sender, never from browser payload fields.
- Tokens, rclone configuration, and credentials never appear in recipes, state files, logs, or messages.
- Vietnamese and English command descriptions and all critical UI states are maintained together.

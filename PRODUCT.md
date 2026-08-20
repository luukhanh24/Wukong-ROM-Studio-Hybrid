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
- The Mini App maps the Windows operating model into Studio, Jobs, Library, Catalog, and System; the chat menu keeps New build, My jobs, ROM library, Diagnostics, and Language as fast paths.
- Job details expose refresh, events, artifact, cancel, resume, and back actions only when relevant.
- Errors name the problem and provide a direct recovery action.

## Build wizard

The chat wizard and Mini App gather task, execution target, ROM source, device, MOD version, preset, individual MOD selections, pipeline stages, packaging, publishing, notification, and confirmation. Chat MOD selection is paginated for one-handed use; the Mini App exposes the complete searchable flight plan in one responsive surface. Local files are permitted only for eligible Windows/admin jobs; GitHub jobs use HTTP(S) or a private Google Drive reference and only advertise MOD versions backed by a verified private content-pack. UI state is stored locally by Telegram user ID and never contains credentials.

## Product constraints

- The orchestration package remains the single source of truth for validation, routing, status, ownership, cancel, and resume.
- Telegram callback data is short, versioned, and never grants access by itself.
- Mini App requests are capped at Telegram's 4096-byte `sendData` limit and ownership always comes from the authenticated Telegram sender, never from browser payload fields.
- Tokens, rclone configuration, and credentials never appear in recipes, state files, logs, or messages.
- Vietnamese and English command descriptions and all critical UI states are maintained together.

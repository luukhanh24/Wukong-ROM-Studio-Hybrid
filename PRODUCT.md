# Wukong ROM Studio Hybrid

## Product

Wukong ROM Studio Hybrid is a ROM build and source-mirroring tool with one shared orchestration core. It is operated through a Windows desktop app, GitHub Actions, a headless CLI, and a Telegram bot.

## Users and access

- Administrators manage approved Telegram users, runners, secrets, content packs, and all jobs.
- Approved users create and manage only their own jobs.
- Channel adapters provide the authenticated identity; recipes never determine ownership.

## Telegram surface

- Platform: native Telegram chat controls (bot command menu, inline keyboards, and messages), not a website or Telegram Web App.
- Mode: Operate. The primary task is to create and monitor a ROM build with one-handed mobile interaction.
- Vietnamese is the default language; English can be selected instantly and is remembered per Telegram user ID.
- Common flows use buttons and a step-by-step build wizard. Raw `/submit <JSON>` remains available as an advanced compatibility path.
- The main actions are New build, My jobs, ROM library, Diagnostics, and Language.
- Job details expose refresh, events, artifact, cancel, resume, and back actions only when relevant.
- Errors name the problem and provide a direct recovery action.

## Build wizard

The wizard gathers task, execution target, ROM source, device, MOD version, preset, individual MOD selections, and confirmation. MOD selection is paginated for one-handed use. Local files are permitted only for eligible Windows/admin jobs; GitHub jobs use HTTP(S) or a private Google Drive reference and only advertise MOD versions backed by a verified private content-pack. UI state is stored locally by Telegram user ID and never contains credentials.

## Product constraints

- The orchestration package remains the single source of truth for validation, routing, status, ownership, cancel, and resume.
- Telegram callback data is short, versioned, and never grants access by itself.
- Tokens, rclone configuration, and credentials never appear in recipes, state files, logs, or messages.
- Vietnamese and English command descriptions and all critical UI states are maintained together.

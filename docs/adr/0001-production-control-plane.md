---
status: superseded by ADR-0002
---

# Use Vercel, Render, PostgreSQL and Drive as the production control plane

Production uses Vercel for the static Mini App, Render for the authenticated API and Telegram bot, PostgreSQL for durable control-plane state, private GitHub Actions for ROM execution, and Google Drive for artifacts. This separates the always-available user experience from the Windows workstation and keeps the personal repository, database and credentials outside every user-facing payload; changing this split would require coordinated deployment, state and bot migration.

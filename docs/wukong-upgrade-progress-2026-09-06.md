# Wukong ROM Studio upgrade progress — 2026-09-06

This document records implementation evidence for the approved upgrade plan. A green fixture test is not treated as a production deployment or a Telegram/runner acceptance test.

| Ticket | Status | Evidence | Still required |
| --- | --- | --- | --- |
| A1 | Implemented and tested | `943e49c`, `2c31bc0`; Mini App polling regression suite covers hidden/offline detail, resume, stale requests, coalesced reconnect, pairing, maintenance, batch and admin-user scopes. | Real Telegram visibility/online event run on Android and iOS. |
| A2 | Implemented and tested | `943e49c`, `2c31bc0`; confirmed job is shown before profile/draft cleanup, pending payload/key survives uncertain or malformed responses, and duplicate submit is serialized. | Production timeout confirmation with a real authenticated account. |
| A3 | Implemented and tested | Shared `tests/fixtures/hybrid_recipe_corpus.json` is read by Vitest and Python; recipe, preset, source, pipeline and protected-step cases pass. | Extend the same corpus with executable lifecycle fixtures if a new cross-runtime status contract is introduced. |
| A4 | Partially implemented and tested | Existing callback/bootstrap/recovery tests plus late terminal callback after cancel. | Full failure-injection matrix for batch interruption, callback ordering after resume, and one-time quota/slot/notification side effects. |
| B1–B4 | Implemented and tested in fixture browser | `1a87d5c` plus current accessibility/log-window changes; old card/line layout restored, local hashed bundle/fonts retained, five-slot dock retained, exact viewport regression and 10,000-event buffer/500-row DOM tests pass. | Computed-style audit for every primary control, DOM pagination test over 10,000 API events, and Telegram keyboard/safe-area acceptance. |
| C1 | Harness implemented | `tools/cloudflare_load_smoke.py` supports authenticated paths, payload and optional D1 row metrics. | Seeded 10,000-job staging D1 run with real auth and p50/p95 report. |
| C2 | Implemented and measured locally | `tools/mini_app_bundle_budget.py`; baseline `8dededd` → current bundle: raw 336,297 → 185,016 bytes (45.0% reduction), gzip 87,864 → 55,962 bytes (36.3% reduction). | 30-run interaction p95 report on pinned Chromium/CPU throttle. |
| C3 | Implemented and tested | `1a87d5c`, `2c31bc0` plus current executor metrics; terminal steps always emit a metric with explicit `cacheState`, missing duration/bytes stay absent, and materialize/checkpoint/checksum/publish include stage metrics. Artifact checksum fallback remains. | Real runner metrics across cold/warm builds. |
| C4 | Harness implemented | `tools/build_benchmark.py` records cold/warm runs, stage JSON metrics, medians and assumptions. | One fixed ROM/recipe/runner, three cold and three warm runs plus ZIP/partition/metadata validation. |
| D1 | Tested locally | Worker check: 21 files/103 tests plus 8 transport tests; frontend 5 Node tests and build; Mini App 7/7 and relevant Python regression suites pass. Deploy validation now gates the same suites. | Full repository CI after final release commit. |
| D2–D3 | Partially configured | `5ce2c8a` makes Vercel production promotion manual CLI-only, removes Git Integration fallback, verifies the promoted frontend after Worker health, and the latest workflow pins Vercel to the Worker release SHA. | Verify environment approvals, run staging canary for 24 hours, and rehearse independent rollback. |

## Current release state

- Local implementation commits: `943e49c`, `1a87d5c`, `2c31bc0`, `8bc3a81`, `5ce2c8a`, `3bb1720`, `86f862a`, `c085cd6`, `aeda192`, `c56e899`, `9040f44`, `0943074`; workflow release-SHA and regression-gate edits are pending their own commit.
- No database migration was added.
- Production evidence must be recorded separately with the Worker version, frontend deployment ID, health/release response, and post-deploy smoke results.
- Until the external rows above are completed, the upgrade is **not fully accepted**.

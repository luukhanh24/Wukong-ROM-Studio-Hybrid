# Limit production to 20 active builds globally

Status: Accepted — supersedes the per-user and per-device build lock policy in
ADR 0003.

Wukong ROM Studio accepts concurrent builds from the same Telegram User and
for the same device. GitHub-hosted runners isolate each workspace, while job
IDs isolate Drive recipes, checkpoints, manifests and artifacts.

The control plane enforces one atomic global ceiling of 20 non-terminal Jobs
in D1. The twenty-first Job is rejected before Build Credit consumption with
the stable `build_concurrency_limit` error. Idempotent retries still return the
previously Accepted Job and do not occupy another slot.

Terminal Jobs (`succeeded`, `failed` or `cancelled`) no longer count toward the
ceiling. Legacy rows in `wukong_build_locks` remain compatible during rollout
and are removed by the existing terminal cleanup paths, but new Jobs do not
create user/device lock rows.

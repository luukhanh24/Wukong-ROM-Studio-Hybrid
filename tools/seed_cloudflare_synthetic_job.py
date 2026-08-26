from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def _literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def synthetic_sql(job_id: str, *, source_url: str) -> str:
    if not job_id.startswith("synthetic-") or len(job_id) > 64:
        raise ValueError("Synthetic job ID is invalid")
    if not source_url.startswith("https://"):
        raise ValueError("Synthetic source URL must use HTTPS")
    now = datetime.now(tz=timezone.utc).isoformat()
    recipe = {
        "schemaVersion": 1,
        "task": "artifact_publish",
        "device": "PKG110",
        "source": {"kind": "https", "uri": source_url},
        "build": {
            "preset": "custom",
            "modVersion": "ColorOS_16.0.10",
            "modReleaseVersion": "synthetic",
            "mods": [],
            "notifyTelegram": True,
        },
        "execution": {"target": "github-hosted"},
        "storage": {"remote": "wukong-gdrive", "publishArtifact": True},
    }
    manifest = {
        "schema_version": 1,
        "job_id": job_id,
        "owner": {"channel": "actions", "subject": "1678823419", "role": "admin"},
        "recipe_digest": "",
        "task": "artifact_publish",
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "runner": "github-actions",
        "external_run_id": "",
        "created_at": now,
        "updated_at": now,
        "finished_at": "",
        "checkpoint": None,
        "artifacts": [],
        "error": None,
    }
    return "\n".join(
        [
            "PRAGMA foreign_keys = ON;",
            (
                "INSERT INTO wukong_jobs "
                "(job_id, manifest_json, recipe_json, created_at, updated_at, "
                "next_event_sequence, owner_channel, owner_subject, device, status, stage, progress) "
                f"VALUES ({_literal(job_id)}, "
                f"{_literal(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')))}, "
                f"{_literal(json.dumps(recipe, ensure_ascii=False, separators=(',', ':')))}, "
                f"{_literal(now)}, {_literal(now)}, 2, 'actions', '1678823419', "
                "'PKG110', 'queued', 'queued', 0);"
            ),
            (
                "INSERT INTO wukong_build_locks "
                "(lock_key, job_id, subject, device, created_at) VALUES "
                f"({_literal('synthetic:' + job_id)}, {_literal(job_id)}, "
                f"'1678823419', 'PKG110', {_literal(now)});"
            ),
            (
                "INSERT INTO wukong_job_events "
                "(job_id, sequence, timestamp, event_type, payload_json) VALUES "
                f"({_literal(job_id)}, 1, {_literal(now)}, 'submitted', "
                "'{\"runner\":\"github-actions\",\"channel\":\"actions\",\"synthetic\":true}');"
            ),
        ]
    ) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a D1 synthetic Actions job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        synthetic_sql(args.job_id, source_url=args.source_url),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

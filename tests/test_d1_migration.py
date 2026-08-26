from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.migrate_postgres_to_d1 import (
    TABLES,
    cutover_attestation_sql,
    generate_d1_sql,
    snapshot_sqlite,
    verify_snapshots,
)


ROOT = Path(__file__).resolve().parents[1]


class D1MigrationTests(unittest.TestCase):
    def test_snapshot_import_matches_row_counts_and_canonical_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as root_value:
            root = Path(root_value)
            database = root / "d1.sqlite"
            migrations = [
                ROOT / "deploy/cloudflare-worker/migrations/0001_initial.sql",
                ROOT / "deploy/cloudflare-worker/migrations/0002_job_guards.sql",
            ]
            now = "2026-08-26T00:00:00+00:00"
            manifest = {
                "job_id": "fixture-job",
                "owner": {"channel": "telegram", "subject": "42", "role": "user"},
                "status": "succeeded",
                "stage": "complete",
                "progress": 1,
                "created_at": now,
                "updated_at": now,
                "finished_at": now,
                "artifacts": [],
            }
            rows = {
                table: [] for table in TABLES
            }
            rows["wukong_telegram_users"] = [{
                "subject": "42", "username": "fixture", "display_name": "Fixture",
                "photo_url": "", "access_status": "approved", "role": "user",
                "first_seen_at": now, "last_seen_at": now, "mini_app_open_count": 1,
                "job_count": 1, "build_credits": 0, "unlimited": 0,
                "lifetime_granted": 1, "lifetime_used": 1, "last_job_id": "fixture-job",
                "last_job_status": "succeeded", "approved_at": now, "revoked_at": "",
                "access_actor": "1678823419", "access_reason": "", "language": "vi",
                "platform": "android", "app_version": "1.0", "configured_admin": 0,
            }]
            rows["wukong_telegram_access"] = [{"subject": "42", "role": "user"}]
            rows["wukong_control_plane_metadata"] = [{
                "key": "control_plane_mode",
                "value": "read_only",
            }]
            rows["wukong_jobs"] = [{
                "job_id": "fixture-job",
                "manifest_json": json.dumps(manifest, separators=(",", ":")),
                "recipe_json": '{"schemaVersion":1,"task":"build","device":"PKG110"}',
                "created_at": now, "next_event_sequence": 2,
                "owner_channel": "telegram", "owner_subject": "42",
                "device": "PKG110", "status": "succeeded",
            }]
            rows["wukong_job_events"] = [{
                "job_id": "fixture-job", "sequence": 1, "timestamp": now,
                "event_type": "submitted", "payload_json": "{}",
            }]
            snapshot = {
                "schemaVersion": 1,
                "estimatedD1Bytes": 1024,
                "tables": {
                    table: {
                        "columns": list(spec.columns),
                        "orderBy": list(spec.order_by),
                        "rowCount": len(rows[table]),
                        "sha256": __import__("hashlib").sha256(json.dumps(
                            [[row.get(column) for column in spec.columns] for row in rows[table]],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode()).hexdigest(),
                        "rows": rows[table],
                    }
                    for table, spec in TABLES.items()
                },
            }
            connection = sqlite3.connect(database)
            try:
                for migration in migrations:
                    connection.executescript(migration.read_text(encoding="utf-8"))
                connection.executescript(generate_d1_sql(snapshot))
            finally:
                connection.close()
            migrated = snapshot_sqlite(database)
            self.assertEqual([], verify_snapshots(snapshot, migrated))
            attestation = cutover_attestation_sql(snapshot)
            self.assertIn("migration_verified_snapshot_sha256", attestation)
            self.assertIn("migration_non_terminal_jobs', '0", attestation)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
MAX_D1_BYTES = 4 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class TableSpec:
    columns: tuple[str, ...]
    order_by: tuple[str, ...]
    expiry: str = ""


TABLES: dict[str, TableSpec] = {
    "wukong_telegram_users": TableSpec(
        (
            "subject", "username", "display_name", "photo_url", "access_status", "role",
            "first_seen_at", "last_seen_at", "mini_app_open_count", "job_count",
            "build_credits", "unlimited", "lifetime_granted", "lifetime_used",
            "last_job_id", "last_job_status", "approved_at", "revoked_at",
            "access_actor", "access_reason", "language", "platform", "app_version",
            "configured_admin",
        ),
        ("subject",),
    ),
    "wukong_telegram_access": TableSpec(("subject", "role"), ("subject",)),
    "wukong_telegram_user_events": TableSpec(
        ("event_id", "subject", "event_type", "actor_subject", "reason", "details_json", "created_at"),
        ("event_id",),
    ),
    "wukong_telegram_sessions": TableSpec(
        ("subject", "session_id", "opened_at"),
        ("subject", "session_id"),
    ),
    "wukong_telegram_quota_ledger": TableSpec(
        (
            "ledger_id", "subject", "entry_type", "delta", "balance_after", "job_id",
            "idempotency_key", "consumed", "actor_subject", "reason", "created_at",
        ),
        ("ledger_id",),
    ),
    "wukong_telegram_ui_state": TableSpec(
        ("subject", "language", "session_json", "job_refs_json"),
        ("subject",),
    ),
    "wukong_telegram_pairings": TableSpec(
        ("pair_id", "secret_hash", "created_at", "expires_at", "user_id"),
        ("pair_id",),
        "expires_at >= {now}",
    ),
    "wukong_telegram_source_drafts": TableSpec(
        ("subject", "uri", "updated_at"),
        ("subject",),
        "updated_at >= {draft_minimum}",
    ),
    "wukong_jobs": TableSpec(
        (
            "job_id", "manifest_json", "recipe_json", "created_at",
            "next_event_sequence", "owner_channel", "owner_subject", "device", "status",
        ),
        ("job_id",),
    ),
    "wukong_job_events": TableSpec(
        ("job_id", "sequence", "timestamp", "event_type", "payload_json"),
        ("job_id", "sequence"),
    ),
    "wukong_build_locks": TableSpec(
        ("lock_key", "job_id", "subject", "device", "created_at"),
        ("lock_key",),
    ),
    "wukong_control_plane_metadata": TableSpec(("key", "value"), ("key",)),
}

IMPORT_ORDER = tuple(TABLES)
DELETE_ORDER = tuple(reversed(IMPORT_ORDER))


def _canonical_rows(rows: Iterable[Mapping[str, object]], columns: Sequence[str]) -> bytes:
    values = [[row.get(column) for column in columns] for row in rows]
    return json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _table_hash(rows: Iterable[Mapping[str, object]], columns: Sequence[str]) -> str:
    return hashlib.sha256(_canonical_rows(rows, columns)).hexdigest()


def _snapshot_table(rows: list[dict[str, object]], spec: TableSpec) -> dict[str, object]:
    return {
        "columns": list(spec.columns),
        "orderBy": list(spec.order_by),
        "rowCount": len(rows),
        "sha256": _table_hash(rows, spec.columns),
        "rows": rows,
    }


def export_postgres(database_url: str, *, now: int | None = None) -> dict[str, object]:
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    import psycopg
    from psycopg.rows import dict_row

    current = int(datetime.now(tz=timezone.utc).timestamp()) if now is None else int(now)
    draft_minimum = current - 24 * 60 * 60
    tables: dict[str, object] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for table, spec in TABLES.items():
            where = (
                f" WHERE {spec.expiry.format(now=current, draft_minimum=draft_minimum)}"
                if spec.expiry
                else ""
            )
            columns = ", ".join(spec.columns)
            order_by = ", ".join(spec.order_by)
            rows = [
                {column: row.get(column) for column in spec.columns}
                for row in connection.execute(
                    f"SELECT {columns} FROM {table}{where} ORDER BY {order_by}"
                ).fetchall()
            ]
            tables[table] = _snapshot_table(rows, spec)
        connection.rollback()
    encoded = json.dumps(tables, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "exportedAt": datetime.now(tz=timezone.utc).isoformat(),
        "source": "postgresql",
        "estimatedD1Bytes": len(encoded),
        "tables": tables,
    }


def snapshot_sqlite(database: Path) -> dict[str, object]:
    tables: dict[str, object] = {}
    connection = sqlite3.connect(database)
    try:
        connection.row_factory = sqlite3.Row
        for table, spec in TABLES.items():
            columns = ", ".join(spec.columns)
            order_by = ", ".join(spec.order_by)
            rows = [
                {column: row[column] for column in spec.columns}
                for row in connection.execute(
                    f"SELECT {columns} FROM {table} ORDER BY {order_by}"
                ).fetchall()
            ]
            tables[table] = _snapshot_table(rows, spec)
    finally:
        connection.close()
    encoded = json.dumps(tables, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "exportedAt": datetime.now(tz=timezone.utc).isoformat(),
        "source": "d1-sqlite",
        "estimatedD1Bytes": len(encoded),
        "tables": tables,
    }


def load_snapshot(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Migration snapshot schema is not supported")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or set(TABLES) - set(tables):
        raise ValueError("Migration snapshot is incomplete")
    if int(payload.get("estimatedD1Bytes") or 0) >= MAX_D1_BYTES:
        raise ValueError("Migration snapshot exceeds the 4 GiB D1 cutover limit")
    return payload


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _manifest_fields(row: Mapping[str, object]) -> dict[str, object]:
    try:
        manifest = json.loads(str(row.get("manifest_json") or "{}"))
    except json.JSONDecodeError:
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    external_run_id = manifest.get("external_run_id")
    try:
        github_run_id = int(external_run_id) if external_run_id else None
    except (TypeError, ValueError):
        github_run_id = None
    return {
        "updated_at": str(manifest.get("updated_at") or row.get("created_at") or ""),
        "finished_at": str(manifest.get("finished_at") or ""),
        "stage": str(manifest.get("stage") or row.get("status") or "queued"),
        "progress": max(0.0, min(1.0, float(manifest.get("progress") or 0.0))),
        "github_run_id": github_run_id,
        "terminal_notified": 0,
        "recipe_drive_ref": "",
    }


def generate_d1_sql(snapshot: Mapping[str, object]) -> str:
    tables = snapshot["tables"]
    if not isinstance(tables, Mapping):
        raise ValueError("Migration snapshot tables are invalid")
    lines = [
        "PRAGMA foreign_keys = OFF;",
        "INSERT INTO wukong_control_plane_metadata (key, value)",
        "VALUES ('d1_migration_mode', 'migration')",
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value;",
    ]
    for table in DELETE_ORDER:
        lines.append(f"DELETE FROM {table};")
    lines.append(
        "INSERT INTO wukong_control_plane_metadata (key, value) "
        "VALUES ('d1_migration_mode', 'migration');"
    )
    for table in IMPORT_ORDER:
        table_payload = tables.get(table)
        if not isinstance(table_payload, Mapping):
            raise ValueError(f"Migration snapshot table is invalid: {table}")
        rows = table_payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"Migration snapshot rows are invalid: {table}")
        source_columns = list(TABLES[table].columns)
        for raw_row in rows:
            if not isinstance(raw_row, Mapping):
                raise ValueError(f"Migration row is invalid: {table}")
            row = dict(raw_row)
            columns = list(source_columns)
            if table == "wukong_jobs":
                extra = _manifest_fields(row)
                columns.extend(extra)
                row.update(extra)
            values = ", ".join(_sql_literal(row.get(column)) for column in columns)
            lines.append(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({values});"
            )
    lines.extend(
        [
            "DELETE FROM wukong_control_plane_metadata WHERE key = 'd1_migration_mode';",
            "PRAGMA foreign_keys = ON;",
        ]
    )
    return "\n".join(lines) + "\n"


def verify_snapshots(expected: Mapping[str, object], actual: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    expected_tables = expected.get("tables")
    actual_tables = actual.get("tables")
    if not isinstance(expected_tables, Mapping) or not isinstance(actual_tables, Mapping):
        return ["Snapshot tables are invalid"]
    for table in TABLES:
        left = expected_tables.get(table)
        right = actual_tables.get(table)
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            errors.append(f"{table}: missing")
            continue
        if int(left.get("rowCount") or 0) != int(right.get("rowCount") or 0):
            errors.append(
                f"{table}: row count {right.get('rowCount')} != {left.get('rowCount')}"
            )
        if str(left.get("sha256") or "") != str(right.get("sha256") or ""):
            errors.append(f"{table}: canonical SHA-256 mismatch")
    return errors


def cutover_attestation_sql(snapshot: Mapping[str, object]) -> str:
    tables = snapshot.get("tables")
    if not isinstance(tables, Mapping):
        raise ValueError("Migration snapshot tables are invalid")
    metadata = tables.get("wukong_control_plane_metadata")
    metadata_rows = metadata.get("rows") if isinstance(metadata, Mapping) else None
    if not isinstance(metadata_rows, list):
        raise ValueError("Migration metadata is invalid")
    source_mode = next(
        (
            str(row.get("value") or "")
            for row in metadata_rows
            if isinstance(row, Mapping) and row.get("key") == "control_plane_mode"
        ),
        "",
    )
    if source_mode != "read_only":
        raise ValueError("PostgreSQL snapshot was not exported after Render entered read_only mode")
    jobs = tables.get("wukong_jobs")
    job_rows = jobs.get("rows") if isinstance(jobs, Mapping) else None
    if not isinstance(job_rows, list):
        raise ValueError("Migration job rows are invalid")
    non_terminal = sum(
        1
        for row in job_rows
        if isinstance(row, Mapping)
        and str(row.get("status") or "") not in {"succeeded", "failed", "cancelled"}
    )
    if non_terminal:
        raise ValueError(f"Migration snapshot still contains {non_terminal} non-terminal job(s)")
    fingerprints = {
        table: {
            "rowCount": int(payload.get("rowCount") or 0),
            "sha256": str(payload.get("sha256") or ""),
        }
        for table, payload in tables.items()
        if isinstance(payload, Mapping)
    }
    digest = hashlib.sha256(
        json.dumps(
            fingerprints,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    values = {
        "migration_verified_snapshot_sha256": digest,
        "migration_non_terminal_jobs": "0",
        "migration_estimated_d1_bytes": str(int(snapshot.get("estimatedD1Bytes") or 0)),
        "migration_verified_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    return "\n".join(
        [
            "PRAGMA foreign_keys = ON;",
            *[
                "INSERT INTO wukong_control_plane_metadata (key, value) "
                f"VALUES ({_sql_literal(key)}, {_sql_literal(value)}) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value;"
                for key, value in values.items()
            ],
        ]
    ) + "\n"


def import_postgres(
    database_url: str,
    snapshot: Mapping[str, object],
    *,
    replace: bool,
) -> None:
    if not replace:
        raise ValueError("Reverse import requires the explicit --replace flag")
    import psycopg

    tables = snapshot.get("tables")
    if not isinstance(tables, Mapping):
        raise ValueError("Migration snapshot tables are invalid")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table in DELETE_ORDER:
            cursor.execute(f"DELETE FROM {table}")
        for table in IMPORT_ORDER:
            payload = tables[table]
            rows = payload.get("rows") if isinstance(payload, Mapping) else None
            if not isinstance(rows, list):
                raise ValueError(f"Migration snapshot rows are invalid: {table}")
            columns = TABLES[table].columns
            placeholders = ", ".join("%s" for _ in columns)
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError(f"Migration row is invalid: {table}")
                cursor.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    tuple(row.get(column) for column in columns),
                )
        connection.commit()


def set_render_mode(database_url: str, mode: str) -> None:
    if mode not in {"read_only", "read_write"}:
        raise ValueError("Render mode must be read_only or read_write")
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wukong_control_plane_metadata (key, value) "
            "VALUES ('control_plane_mode', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (mode,),
        )
        connection.commit()


def _write_snapshot(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _database_url(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise ValueError(f"{env_name} is required")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate Wukong PostgreSQL state to Cloudflare D1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export-postgres")
    export.add_argument("--database-url-env", default="DATABASE_URL")
    export.add_argument("--output", type=Path, required=True)

    generate = subparsers.add_parser("generate-d1-sql")
    generate.add_argument("--snapshot", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)

    sqlite_snapshot = subparsers.add_parser("snapshot-sqlite")
    sqlite_snapshot.add_argument("--database", type=Path, required=True)
    sqlite_snapshot.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--expected", type=Path, required=True)
    verify.add_argument("--actual", type=Path, required=True)
    verify.add_argument("--attestation-sql", type=Path)

    reverse = subparsers.add_parser("import-postgres")
    reverse.add_argument("--database-url-env", default="DATABASE_URL")
    reverse.add_argument("--snapshot", type=Path, required=True)
    reverse.add_argument("--replace", action="store_true")

    mode = subparsers.add_parser("set-render-mode")
    mode.add_argument("--database-url-env", default="DATABASE_URL")
    mode.add_argument("--mode", choices=["read_only", "read_write"], required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "export-postgres":
            _write_snapshot(args.output, export_postgres(_database_url(args.database_url_env)))
        elif args.command == "generate-d1-sql":
            snapshot = load_snapshot(args.snapshot)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(generate_d1_sql(snapshot), encoding="utf-8")
        elif args.command == "snapshot-sqlite":
            _write_snapshot(args.output, snapshot_sqlite(args.database))
        elif args.command == "verify":
            expected = load_snapshot(args.expected)
            actual = load_snapshot(args.actual)
            errors = verify_snapshots(expected, actual)
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            if args.attestation_sql:
                args.attestation_sql.parent.mkdir(parents=True, exist_ok=True)
                args.attestation_sql.write_text(
                    cutover_attestation_sql(expected),
                    encoding="utf-8",
                )
            print("All migrated table row counts and canonical SHA-256 values match.")
        elif args.command == "import-postgres":
            import_postgres(
                _database_url(args.database_url_env),
                load_snapshot(args.snapshot),
                replace=args.replace,
            )
        elif args.command == "set-render-mode":
            set_render_mode(_database_url(args.database_url_env), args.mode)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

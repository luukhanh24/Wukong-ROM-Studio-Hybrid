from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def _api_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized.startswith("https://") or any(char.isspace() for char in normalized):
        raise ValueError("Control-plane API URL must be public HTTPS")
    return normalized


def _request_json(
    url: str,
    payload: Mapping[str, object],
    *,
    headers: Mapping[str, str],
    attempts: int = 5,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "wukong-actions-control-plane/1.0",
                **dict(headers),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise RuntimeError("Control-plane response must be an object")
                return result
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read(1024).decode("utf-8", errors="replace").strip()
            except OSError:
                detail = ""
            last_error = RuntimeError(
                f"HTTP {exc.code}{f': {detail}' if detail else ''}"
            )
            if attempt + 1 < max(1, attempts):
                time.sleep(min(10, 2 ** attempt))
        except (OSError, RuntimeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < max(1, attempts):
                time.sleep(min(10, 2 ** attempt))
    raise RuntimeError(f"Control-plane request failed: {last_error}") from last_error


def _signed_headers(secret: str, body: bytes, *, now: int | None = None) -> dict[str, str]:
    if len(secret) < 20:
        raise ValueError("Actions callback secret is not configured")
    timestamp = str(int(time.time()) if now is None else int(now))
    key = hmac.new(
        b"WukongActionsCallback\0",
        secret.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = hmac.new(
        key,
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Wukong-Timestamp": timestamp,
        "X-Wukong-Signature": signature,
    }


def _post_signed(
    api_url: str,
    path: str,
    payload: Mapping[str, object],
    secret: str,
    *,
    attempts: int = 5,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _request_json(
        f"{_api_url(api_url)}{path}",
        payload,
        headers=_signed_headers(secret, body),
        attempts=attempts,
    )


def bootstrap(
    api_url: str,
    *,
    job_id: str,
    run_id: int,
    github_token: str,
    secret: str,
    output: Path,
    recipe_output: Path,
) -> dict[str, Any]:
    if len(github_token) < 20:
        raise ValueError("GITHUB_TOKEN is required for Actions bootstrap")
    if len(secret) < 20:
        raise ValueError("Actions callback secret is required for Actions bootstrap")
    payload = {"jobId": job_id, "runId": int(run_id)}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    result = _request_json(
        f"{_api_url(api_url)}/internal/actions/bootstrap",
        payload,
        headers={
            "Authorization": f"Bearer {github_token}",
            **_signed_headers(secret, body),
        },
        attempts=6,
    )
    recipe = result.get("recipe")
    if not isinstance(recipe, dict):
        raise RuntimeError("Actions bootstrap did not return a recipe")
    output.parent.mkdir(parents=True, exist_ok=True)
    recipe_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    recipe_output.write_text(
        json.dumps(recipe, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _translated_event(event: Mapping[str, object], offset: int) -> dict[str, object]:
    sequence = max(1, int(event.get("sequence") or 1))
    payload = dict(event)
    payload["sequence"] = offset + sequence
    return payload


def monitor_progress(
    api_url: str,
    *,
    job_id: str,
    run_id: int,
    secret: str,
    jobs_root: Path,
    sequence_offset: int = 2,
    interval_seconds: float = 2.0,
    timeout_seconds: int = 24 * 60 * 60,
) -> None:
    job_root = jobs_root / job_id
    manifest_path = job_root / "manifest.json"
    events_path = job_root / "events.jsonl"
    started = time.monotonic()
    last_local_sequence = 0
    last_signature: tuple[str, str, float] | None = None
    last_upload_sent = 0.0
    pending_events: list[dict[str, Any]] = []
    callback_sequence = sequence_offset + 1
    while time.monotonic() - started < timeout_seconds:
        manifest = _read_json(manifest_path)
        events = _read_events(events_path)
        new_events = [
            event
            for event in events
            if int(event.get("sequence") or 0) > last_local_sequence
        ]
        if new_events:
            last_local_sequence = max(int(event.get("sequence") or 0) for event in new_events)
            callback_sequence = max(callback_sequence, sequence_offset + last_local_sequence)
            pending_events.extend(new_events)
        status = str(manifest.get("status") or "running")
        stage = str(manifest.get("stage") or status)
        progress = max(0.0, min(1.0, float(manifest.get("progress") or 0.0)))
        if status in TERMINAL_STATUSES:
            return
        signature = (status, stage, progress)
        upload_only = bool(pending_events) and all(
            str(event.get("type") or "") == "upload_progress" for event in pending_events
        )
        now = time.monotonic()
        stage_or_status_changed = (
            last_signature is None
            or signature[:2] != last_signature[:2]
        )
        progress_changed = last_signature is None or signature[2] != last_signature[2]
        should_send = bool(manifest) and (
            stage_or_status_changed
            or bool(pending_events) and not upload_only
            or upload_only and now - last_upload_sent >= 5
            or progress_changed and not pending_events
        )
        if should_send:
            callback_sequence += 1
            _post_signed(
                api_url,
                "/internal/actions/progress",
                {
                    "jobId": job_id,
                    "runId": int(run_id),
                    "sequence": callback_sequence,
                    "status": status,
                    "stage": stage,
                    "progress": progress,
                    "events": [
                        _translated_event(event, sequence_offset)
                        for event in pending_events
                    ],
                },
                secret,
                attempts=3,
            )
            last_signature = signature
            if upload_only:
                last_upload_sent = now
            pending_events.clear()
        time.sleep(max(0.5, interval_seconds))


def terminal_callback(
    api_url: str,
    *,
    job_id: str,
    run_id: int,
    secret: str,
    workflow_result: str,
    manifest_path: Path | None,
    events_path: Path | None,
    pre_executor_failure: bool,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path) if manifest_path else {}
    events = _read_events(events_path) if events_path else []
    last_sequence = max(
        (int(event.get("sequence") or 0) for event in events),
        default=0,
    )
    result = workflow_result if workflow_result in {"success", "failure", "cancelled"} else "failure"
    payload: dict[str, object] = {
        "jobId": job_id,
        "runId": int(run_id),
        "workflowResult": result,
        "preExecutorFailure": bool(pre_executor_failure),
        "sequence": max(3, last_sequence + 3),
    }
    if manifest:
        payload["manifest"] = manifest
    return _post_signed(
        api_url,
        "/internal/actions/callback",
        payload,
        secret,
        attempts=30,
    )


def mirror_repair_callback(
    api_url: str,
    *,
    job_id: str,
    run_id: int,
    secret: str,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    if not manifest:
        raise ValueError("Repaired manifest is required")
    return _post_signed(
        api_url,
        "/internal/actions/mirror-repair",
        {
            "jobId": job_id,
            "runId": int(run_id),
            "manifest": manifest,
        },
        secret,
        attempts=30,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cloudflare control-plane bridge for GitHub Actions")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--api-url", required=True)
    bootstrap_parser.add_argument("--job-id", required=True)
    bootstrap_parser.add_argument("--run-id", type=int, required=True)
    bootstrap_parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""))
    bootstrap_parser.add_argument(
        "--secret",
        default=os.environ.get("WUKONG_ACTIONS_CALLBACK_SECRET", ""),
    )
    bootstrap_parser.add_argument("--output", type=Path, default=Path(".wkstudio/actions-bootstrap.json"))
    bootstrap_parser.add_argument("--recipe-output", type=Path, default=Path(".wkstudio/recipe.json"))

    progress_parser = subparsers.add_parser("progress")
    progress_parser.add_argument("--api-url", required=True)
    progress_parser.add_argument("--job-id", required=True)
    progress_parser.add_argument("--run-id", type=int, required=True)
    progress_parser.add_argument("--secret", default=os.environ.get("WUKONG_ACTIONS_CALLBACK_SECRET", ""))
    progress_parser.add_argument("--jobs-root", type=Path, default=Path(".wkstudio/Jobs/hybrid"))
    progress_parser.add_argument("--sequence-offset", type=int, default=2)
    progress_parser.add_argument("--interval", type=float, default=2.0)

    terminal_parser = subparsers.add_parser("terminal")
    terminal_parser.add_argument("--api-url", required=True)
    terminal_parser.add_argument("--job-id", required=True)
    terminal_parser.add_argument("--run-id", type=int, required=True)
    terminal_parser.add_argument("--secret", default=os.environ.get("WUKONG_ACTIONS_CALLBACK_SECRET", ""))
    terminal_parser.add_argument("--workflow-result", required=True)
    terminal_parser.add_argument("--manifest", type=Path)
    terminal_parser.add_argument("--events", type=Path)
    terminal_parser.add_argument("--pre-executor-failure", action="store_true")
    repair_parser = subparsers.add_parser("mirror-repair")
    repair_parser.add_argument("--api-url", required=True)
    repair_parser.add_argument("--job-id", required=True)
    repair_parser.add_argument("--run-id", type=int, required=True)
    repair_parser.add_argument("--secret", default=os.environ.get("WUKONG_ACTIONS_CALLBACK_SECRET", ""))
    repair_parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "bootstrap":
        bootstrap(
            args.api_url,
            job_id=args.job_id,
            run_id=args.run_id,
            github_token=args.github_token,
            secret=args.secret,
            output=args.output,
            recipe_output=args.recipe_output,
        )
    elif args.command == "progress":
        monitor_progress(
            args.api_url,
            job_id=args.job_id,
            run_id=args.run_id,
            secret=args.secret,
            jobs_root=args.jobs_root,
            sequence_offset=args.sequence_offset,
            interval_seconds=args.interval,
        )
    elif args.command == "terminal":
        terminal_callback(
            args.api_url,
            job_id=args.job_id,
            run_id=args.run_id,
            secret=args.secret,
            workflow_result=args.workflow_result,
            manifest_path=args.manifest,
            events_path=args.events,
            pre_executor_failure=args.pre_executor_failure,
        )
    elif args.command == "mirror-repair":
        mirror_repair_callback(
            args.api_url,
            job_id=args.job_id,
            run_id=args.run_id,
            secret=args.secret,
            manifest_path=args.manifest,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

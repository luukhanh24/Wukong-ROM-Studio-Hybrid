from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _one_request(url: str, index: int, headers: dict[str, str] | None = None) -> tuple[int, float, str, int, int | None]:
    started = time.perf_counter()
    request_url = url.format(index=index)
    if "{index}" not in url and request_url.rstrip("/").endswith(url.rstrip("/")):
        request_url = f"{url.rstrip('/')}/healthz?load={index}"
    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": "wukong-cloudflare-load-smoke/1.0", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            body = raw[:4096].decode("utf-8", errors="replace")
            rows = response.headers.get("X-D1-Rows-Read")
            return response.status, time.perf_counter() - started, body, len(raw), int(rows) if rows and rows.isdigit() else None
    except urllib.error.HTTPError as exc:
        raw = exc.read(4096)
        return exc.code, time.perf_counter() - started, raw.decode("utf-8", errors="replace"), len(raw), None
    except OSError as exc:
        return 0, time.perf_counter() - started, str(exc), 0, None


def run_load(url: str, *, requests: int, concurrency: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda index: _one_request(url, index, headers), range(requests)))
    statuses = [status for status, _duration, _body, _bytes, _rows in results]
    durations = [duration * 1000 for _status, duration, _body, _bytes, _rows in results]
    payloads = [size for _status, _duration, _body, size, _rows in results]
    rows = [row for _status, _duration, _body, _bytes, row in results if row is not None]
    failures = [
        {"status": status, "body": body[:240]}
        for status, _duration, body, _bytes, _rows in results
        if status < 200 or status >= 300 or "Error 1102" in body
    ]
    if failures:
        raise RuntimeError(f"Load smoke failed: {failures[:10]}")
    return {
        "requests": len(results),
        "concurrency": concurrency,
        "statusCounts": {
            str(status): statuses.count(status)
            for status in sorted(set(statuses))
        },
        "latencyMs": {
            "mean": round(statistics.fmean(durations), 3),
            "p50": round(_percentile(durations, 0.50), 3),
            "p95": round(_percentile(durations, 0.95), 3),
            "p99": round(_percentile(durations, 0.99), 3),
        },
        "payloadBytes": {
            "mean": round(statistics.fmean(payloads), 3),
            "p50": round(_percentile([float(value) for value in payloads], 0.50), 3),
            "p95": round(_percentile([float(value) for value in payloads], 0.95), 3),
        },
        "d1RowsRead": {
            "samples": len(rows),
            "mean": round(statistics.fmean(rows), 3) if rows else None,
            "p95": round(_percentile([float(value) for value in rows], 0.95), 3) if rows else None,
        },
    }


def run_endpoint_load(
    url: str,
    path: str,
    *,
    requests: int,
    concurrency: int,
    authorization: str = "",
) -> dict[str, Any]:
    """Load one endpoint, preserving the original health-smoke URL contract."""
    endpoint = path.lstrip("/")
    base = url.rstrip("/")
    request_url = f"{base}/{endpoint}"
    if "{index}" not in request_url:
        request_url += ("&" if "?" in request_url else "?") + "load={index}"
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    return run_load(
        request_url,
        requests=requests,
        concurrency=concurrency,
        headers=headers,
    )


def _analytics_query(
    *,
    account_id: str,
    api_token: str,
    script_name: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    query = """
    query WorkerCpu($accountTag: string, $start: string, $end: string, $script: string) {
      viewer {
        accounts(filter: {accountTag: $accountTag}) {
          workersInvocationsAdaptive(
            limit: 100,
            filter: {
              scriptName: $script,
              datetime_geq: $start,
              datetime_leq: $end
            }
          ) {
            sum { requests errors }
            quantiles { cpuTimeP50 cpuTimeP95 cpuTimeP99 }
            dimensions { scriptName status }
          }
        }
      }
    }
    """
    body = json.dumps(
        {
            "query": query,
            "variables": {
                "accountTag": account_id,
                "start": start.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "end": end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "script": script_name,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"Cloudflare Analytics query failed: {payload['errors']}")
    accounts = payload.get("data", {}).get("viewer", {}).get("accounts", [])
    groups = accounts[0].get("workersInvocationsAdaptive", []) if accounts else []
    if not isinstance(groups, list):
        groups = []
    requests = sum(int(group.get("sum", {}).get("requests") or 0) for group in groups)
    errors = sum(int(group.get("sum", {}).get("errors") or 0) for group in groups)
    p95_microseconds = max(
        (float(group.get("quantiles", {}).get("cpuTimeP95") or 0) for group in groups),
        default=0.0,
    )
    return {
        "requests": requests,
        "errors": errors,
        "cpuTimeP95Microseconds": p95_microseconds,
        "cpuTimeP95Milliseconds": p95_microseconds / 1000,
    }


def wait_for_cpu_metrics(
    *,
    account_id: str,
    api_token: str,
    script_name: str,
    start: datetime,
    maximum_p95_ms: float,
    attempts: int = 18,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(attempts):
        end = datetime.now(tz=timezone.utc) + timedelta(seconds=5)
        last = _analytics_query(
            account_id=account_id,
            api_token=api_token,
            script_name=script_name,
            start=start - timedelta(minutes=2),
            end=end,
        )
        if last["requests"] > 0:
            if last["errors"] > 0:
                raise RuntimeError(f"Worker analytics reported errors: {last}")
            if last["cpuTimeP95Milliseconds"] >= maximum_p95_ms:
                raise RuntimeError(
                    f"Worker CPU p95 is {last['cpuTimeP95Milliseconds']:.3f} ms, "
                    f"expected below {maximum_p95_ms:.3f} ms"
                )
            return last
        if attempt + 1 < attempts:
            time.sleep(10)
    raise RuntimeError(f"Cloudflare Analytics did not publish Worker CPU metrics: {last}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load-smoke a Cloudflare Worker and verify CPU p95")
    parser.add_argument("--url", required=True)
    parser.add_argument("--script-name", required=True)
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--maximum-cpu-p95-ms", type=float, default=8.0)
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="Endpoint path to exercise; repeat for sync/history. Defaults to /healthz.",
    )
    parser.add_argument(
        "--authorization",
        default=os.environ.get("WUKONG_AUTHORIZATION", ""),
        help="Authorization header (for example 'tma ...' or 'wla ...'); never put credentials in source.",
    )
    parser.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    parser.add_argument("--api-token", default=os.environ.get("CLOUDFLARE_API_TOKEN", ""))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.account_id or not args.api_token:
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")
    started = datetime.now(tz=timezone.utc)
    paths = args.paths or ["/healthz"]
    loads = {
        path: run_endpoint_load(
            args.url,
            path,
            requests=max(1, args.requests),
            concurrency=max(1, args.concurrency),
            authorization=args.authorization,
        )
        for path in paths
    }
    analytics = wait_for_cpu_metrics(
        account_id=args.account_id,
        api_token=args.api_token,
        script_name=args.script_name,
        start=started,
        maximum_p95_ms=args.maximum_cpu_p95_ms,
    )
    payload = {"loads": loads, "analytics": analytics}
    if len(loads) == 1:
        payload["load"] = next(iter(loads.values()))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

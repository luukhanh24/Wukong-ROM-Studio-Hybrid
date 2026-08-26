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


def _one_request(url: str, index: int) -> tuple[int, float, str]:
    started = time.perf_counter()
    request = urllib.request.Request(
        f"{url.rstrip('/')}/healthz?load={index}",
        headers={"User-Agent": "wukong-cloudflare-load-smoke/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return response.status, time.perf_counter() - started, body
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return exc.code, time.perf_counter() - started, body
    except OSError as exc:
        return 0, time.perf_counter() - started, str(exc)


def run_load(url: str, *, requests: int, concurrency: int) -> dict[str, Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda index: _one_request(url, index), range(requests)))
    statuses = [status for status, _duration, _body in results]
    durations = [duration * 1000 for _status, duration, _body in results]
    failures = [
        {"status": status, "body": body[:240]}
        for status, _duration, body in results
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
    }


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
    parser.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    parser.add_argument("--api-token", default=os.environ.get("CLOUDFLARE_API_TOKEN", ""))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.account_id or not args.api_token:
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")
    started = datetime.now(tz=timezone.utc)
    load = run_load(
        args.url,
        requests=max(1, args.requests),
        concurrency=max(1, args.concurrency),
    )
    analytics = wait_for_cpu_metrics(
        account_id=args.account_id,
        api_token=args.api_token,
        script_name=args.script_name,
        start=started,
        maximum_p95_ms=args.maximum_cpu_p95_ms,
    )
    print(json.dumps({"load": load, "analytics": analytics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

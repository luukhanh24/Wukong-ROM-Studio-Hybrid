#!/usr/bin/env bash
set -Eeuo pipefail

release_sha="${1:-}"
if [[ ! "$release_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full lowercase Git release SHA is required." >&2
  exit 2
fi

base=/opt/wukong-control-plane
staging="/tmp/wukong-control-plane-${release_sha}"
archive="$staging/release.tar.gz"
incoming_env="$staging/control-plane.env"
incoming_rclone="$staging/rclone.conf"
release="$base/releases/${release_sha}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
candidate="${release}.incoming"
current="$base/current"
previous=""

for path in "$archive" "$incoming_env" "$incoming_rclone"; do
  if [[ ! -s "$path" ]]; then
    echo "Missing deployment payload: $path" >&2
    exit 2
  fi
done
command -v docker >/dev/null
docker compose version >/dev/null

install -d -m 0755 "$base" "$base/releases"
if [[ -L "$current" ]]; then
  previous="$(readlink -f "$current")"
fi

rm -rf -- "$candidate"
install -d -m 0755 "$candidate"
tar -xzf "$archive" -C "$candidate"
install -m 0600 "$incoming_env" "$candidate/deploy/control-plane/.env"
install -d -m 0700 "$candidate/deploy/control-plane/secrets"
install -m 0600 "$incoming_rclone" "$candidate/deploy/control-plane/secrets/rclone.conf"

mv -- "$candidate" "$release"
ln -sfn "$release" "$current"

rollback() {
  echo "Control-plane release failed; restoring the previous release." >&2
  if [[ -n "$previous" && -d "$previous/deploy/control-plane" ]]; then
    ln -sfn "$previous" "$current"
    (
      cd "$previous/deploy/control-plane"
      docker compose up -d --remove-orphans
    ) || true
  else
    (
      cd "$release/deploy/control-plane"
      docker compose down --remove-orphans
    ) || true
    if [[ "$(readlink -f "$current" 2>/dev/null || true)" == "$release" ]]; then
      unlink "$current"
    fi
  fi
}
trap rollback ERR

cd "$release/deploy/control-plane"
docker compose config --quiet
docker compose build --pull
docker compose run --rm --no-deps wukong-control-plane \
  python -m tools.control_plane_preflight --online
docker compose up -d --remove-orphans

container_id="$(docker compose ps -q wukong-control-plane)"
if [[ -z "$container_id" ]]; then
  echo "The control-plane container was not created." >&2
  exit 1
fi
for _attempt in {1..30}; do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  if [[ "$health" == healthy ]]; then
    break
  fi
  if [[ "$health" == unhealthy || "$health" == exited || "$health" == dead ]]; then
    docker compose logs --no-color --tail 200
    exit 1
  fi
  sleep 2
done
if [[ "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" != healthy ]]; then
  docker compose logs --no-color --tail 200
  exit 1
fi

docker compose exec -T wukong-control-plane python - "$release_sha" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8766/healthz", timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "ready" or payload.get("release") != sys.argv[1]:
    raise SystemExit(f"Unexpected control-plane health payload: {payload}")
PY

trap - ERR
rm -rf -- "$staging"
docker image prune -f --filter 'until=168h' >/dev/null
for old_release in "$base"/releases/*; do
  [[ -d "$old_release" ]] || continue
  [[ "$old_release" == "$release" || "$old_release" == "$previous" ]] && continue
  old_name="$(basename "$old_release")"
  if [[ "$old_name" =~ ^[0-9a-f]{40}-[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]]; then
    rm -rf -- "$old_release"
  fi
done
echo "Control-plane release $release_sha is healthy."

#!/usr/bin/env bash
set -Eeuo pipefail

deploy_user="${1:-}"
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this one-time bootstrap as root." >&2
  exit 2
fi
if [[ ! "$deploy_user" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  echo "Usage: bootstrap_host.sh DEPLOY_USER" >&2
  exit 2
fi
if ! id "$deploy_user" >/dev/null 2>&1; then
  echo "The deploy user does not exist: $deploy_user" >&2
  exit 2
fi
command -v docker >/dev/null
docker compose version >/dev/null

docker_group="$(getent group docker | cut -d: -f1)"
if [[ "$docker_group" != docker ]]; then
  echo "Docker Engine must be installed with a docker group." >&2
  exit 2
fi
usermod -aG docker "$deploy_user"
install -d -o "$deploy_user" -g "$deploy_user" -m 0750 /opt/wukong-control-plane
install -d -o "$deploy_user" -g "$deploy_user" -m 0750 /opt/wukong-control-plane/releases

echo "Host prepared. Reconnect the deploy user's SSH session so docker group membership applies."

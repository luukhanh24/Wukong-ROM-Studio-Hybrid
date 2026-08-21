#!/bin/sh
set -eu

state_root=/var/lib/wukong
runtime_secret="$state_root/data/Secrets/rclone.runtime.conf"

if [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
  render_url="${RENDER_EXTERNAL_URL%/}"
  export WUKONG_TELEGRAM_MINI_APP_API_URL="${WUKONG_TELEGRAM_MINI_APP_API_URL:-$render_url}"
  export WUKONG_MINI_API_DOMAIN="${WUKONG_MINI_API_DOMAIN:-${render_url#https://}}"
fi
if [ -n "${RENDER_GIT_COMMIT:-}" ]; then
  export WUKONG_RELEASE_SHA="${WUKONG_RELEASE_SHA:-$RENDER_GIT_COMMIT}"
fi
if [ -n "${PORT:-}" ]; then
  export WUKONG_TELEGRAM_MINI_APP_API_PORT="${WUKONG_TELEGRAM_MINI_APP_API_PORT:-$PORT}"
fi
if [ -z "${WUKONG_TELEGRAM_WEBHOOK_SECRET:-}" ] && [ -n "${WUKONG_TELEGRAM_BOT_TOKEN:-}" ]; then
  WUKONG_TELEGRAM_WEBHOOK_SECRET="$(python - <<'PY'
import hashlib
import hmac
import os

token = os.environ["WUKONG_TELEGRAM_BOT_TOKEN"].encode()
domain = os.environ.get("WUKONG_MINI_API_DOMAIN", "").encode()
print(hmac.new(token, b"WukongTelegramWebhook\0" + domain, hashlib.sha256).hexdigest())
PY
  )"
  export WUKONG_TELEGRAM_WEBHOOK_SECRET
fi

mkdir -p \
  "$state_root/data/Secrets" \
  "$state_root/workspace" \
  "$state_root/output" \
  "$state_root/temp" \
  "$state_root/logs"

if [ -n "${WUKONG_RCLONE_CONFIG_CONTENT_B64:-}" ]; then
  printf '%s' "$WUKONG_RCLONE_CONFIG_CONTENT_B64" | base64 -d > "$runtime_secret"
elif [ -s /run/secrets/rclone.conf ]; then
  install -o wukong -g wukong -m 0600 /run/secrets/rclone.conf "$runtime_secret"
else
  echo "Missing /run/secrets/rclone.conf or WUKONG_RCLONE_CONFIG_CONTENT_B64" >&2
  exit 2
fi
chmod 0600 "$runtime_secret"
chown -R wukong:wukong "$state_root"

if [ "${WUKONG_CONTROL_PLANE_ONLINE_PREFLIGHT:-0}" = "1" ]; then
  gosu wukong python -m tools.control_plane_preflight --online
else
  gosu wukong python -m tools.control_plane_preflight
fi
exec gosu wukong "$@"

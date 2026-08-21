#!/bin/sh
set -eu

state_root=/var/lib/wukong
runtime_secret="$state_root/data/Secrets/rclone.runtime.conf"

mkdir -p \
  "$state_root/data/Secrets" \
  "$state_root/workspace" \
  "$state_root/output" \
  "$state_root/temp" \
  "$state_root/logs"

if [ ! -s /run/secrets/rclone.conf ]; then
  echo "Missing /run/secrets/rclone.conf" >&2
  exit 2
fi

install -o wukong -g wukong -m 0600 /run/secrets/rclone.conf "$runtime_secret"
chown -R wukong:wukong "$state_root"

exec gosu wukong "$@"

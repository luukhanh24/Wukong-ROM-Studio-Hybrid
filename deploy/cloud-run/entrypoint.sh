#!/bin/sh
set -eu

mkdir -p /tmp/wukong/data /tmp/wukong/workspace /tmp/wukong/output /tmp/wukong/temp /tmp/wukong/logs
chown -R wukong:wukong /tmp/wukong
exec gosu wukong "$@"

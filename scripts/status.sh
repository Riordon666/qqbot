#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

echo "[containers]"
compose ps

echo
echo "[host memory and swap]"
free -h
swapon --show

echo
echo "[root filesystem]"
df -h /

echo
echo "[container resources]"
running_ids=$(compose ps -q)
if [ -n "$running_ids" ]; then
  # shellcheck disable=SC2086
  docker_cmd stats --no-stream $running_ids
else
  echo "No project containers are running."
fi

echo
echo "[recent warning/error lines, secrets redacted]"
compose logs --no-color --since 30m --tail 500 2>&1 \
  | redact_logs \
  | grep -Ei 'warning|warn|error|critical|exception|traceback|failed|kickedoffline|packetbackend|验证码|密码回退|登录态已失效|closed by peer' \
  | tail -n 40 \
  || true

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

target=all
tail_lines=200
follow=false

if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then
  target=$1
  shift
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --follow|-f)
      follow=true
      ;;
    --tail)
      shift
      if [ "$#" -eq 0 ] || ! [[ "$1" =~ ^[0-9]+$ ]]; then
        echo "--tail requires a non-negative integer" >&2
        exit 2
      fi
      tail_lines=$1
      ;;
    *)
      echo "Usage: $0 [nonebot|napcat|all] [--tail N] [--follow]" >&2
      exit 2
      ;;
  esac
  shift
done

case "$target" in
  nonebot)
    services=(nonebot)
    ;;
  napcat)
    services=(napcat)
    ;;
  all)
    services=(nonebot napcat)
    ;;
  *)
    echo "Usage: $0 [nonebot|napcat|all] [--tail N] [--follow]" >&2
    exit 2
    ;;
esac

args=(logs --no-color --tail "$tail_lines")
if "$follow"; then
  args+=(--follow)
fi

compose "${args[@]}" "${services[@]}" 2>&1 | redact_logs

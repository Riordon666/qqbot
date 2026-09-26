#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

umask 077
include_qq=false
keep_count=7

while [ "$#" -gt 0 ]; do
  case "$1" in
    --include-qq-state)
      include_qq=true
      ;;
    --keep)
      shift
      if [ "$#" -eq 0 ] || ! [[ "$1" =~ ^[1-9][0-9]*$ ]]; then
        echo "--keep requires a positive integer" >&2
        exit 2
      fi
      keep_count=$1
      ;;
    *)
      echo "Usage: $0 [--include-qq-state] [--keep N]" >&2
      exit 2
      ;;
  esac
  shift
done

backup_dir="$PROJECT_ROOT/backups"
timestamp=$(date +%Y%m%d-%H%M%S-%N)
archive="$backup_dir/qqbot-$timestamp.tar.gz"
partial="$archive.partial"

mkdir -p "$backup_dir"
chmod 0700 "$backup_dir"
exec 9>"$backup_dir/.backup.lock"
if ! flock -n 9; then
  echo "Another QQBot backup is already running." >&2
  exit 1
fi

napcat_quiesced=false
if "$include_qq"; then
  napcat_running=$(docker_cmd inspect --format '{{.State.Running}}' qqbot-napcat 2>/dev/null || echo false)
  if [ "$napcat_running" = "true" ]; then
    echo "Refusing an inconsistent QQ-state backup while NapCat is running." >&2
    echo "Run: sudo docker compose stop napcat" >&2
    exit 1
  fi
  napcat_quiesced=true
fi

tmp_dir=$(mktemp -d "$backup_dir/.tmp-$timestamp.XXXXXX")
case "$tmp_dir" in
  "$backup_dir"/.tmp-*)
    ;;
  *)
    echo "Unexpected temporary path" >&2
    exit 1
    ;;
esac

cleanup() {
  rm -rf -- "$tmp_dir"
  rm -f -- "$partial"
}
trap cleanup EXIT

payload="$tmp_dir/payload"
mkdir -p "$payload/data" "$payload/napcat"

if [ -f "$PROJECT_ROOT/data/nonebot/bot.db" ]; then
  python3 - "$PROJECT_ROOT/data/nonebot/bot.db" "$payload/data/bot.db" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=5)
destination = sqlite3.connect(sys.argv[2], timeout=5)
try:
    source.backup(destination)
    result = destination.execute("PRAGMA quick_check").fetchone()
    if result is None or result[0] != "ok":
        detail = "no result" if result is None else str(result[0])
        raise RuntimeError(f"SQLite backup quick_check failed: {detail}")
finally:
    destination.close()
    source.close()
PY
  echo "sqlite_backup=online_api" > "$payload/data/README.txt"
else
  echo "sqlite_backup=database_not_created_yet" > "$payload/data/README.txt"
fi

if [ -d "$PROJECT_ROOT/napcat/config" ]; then
  cp -a "$PROJECT_ROOT/napcat/config" "$payload/napcat/config"
fi

if "$include_qq"; then
  cp -a "$PROJECT_ROOT/napcat/qq" "$payload/napcat/qq"
  printf '%s\n' \
    "WARNING: napcat/qq contains sensitive QQ login state." \
    "Store this archive like a credential." \
    > "$payload/napcat/QQ_STATE_WARNING.txt"
fi

if [ -f "$PROJECT_ROOT/.env" ]; then
  cp -a "$PROJECT_ROOT/.env" "$payload/.env"
fi

cp -a "$PROJECT_ROOT/docker-compose.yml" "$payload/docker-compose.yml"
cp -a "$PROJECT_ROOT/nonebot/pyproject.toml" "$payload/pyproject.toml"
cp -a "$PROJECT_ROOT/nonebot/uv.lock" "$payload/uv.lock"

if git -C "$PROJECT_ROOT" rev-parse --verify HEAD >/dev/null 2>&1; then
  git -C "$PROJECT_ROOT" bundle create "$payload/qqbot.git.bundle" --all
fi

napcat_image_ref=$(sed -n 's/^NAPCAT_IMAGE=//p' "$PROJECT_ROOT/.env" | tail -n 1)
if [ -z "$napcat_image_ref" ]; then
  napcat_image_ref='mlikiowa/napcat-docker:v4.18.19@sha256:1336a777f9a4f1f8cb89fef42f7548deacd3645919a067a50df5b66b5e77390e'
fi
napcat_image_id=$(
  docker_cmd image inspect --format '{{.Id}}' "$napcat_image_ref" 2>/dev/null || echo unavailable
)
napcat_repo_digests=$(
  docker_cmd image inspect --format '{{json .RepoDigests}}' "$napcat_image_ref" 2>/dev/null || echo unavailable
)

{
  printf 'created_at=%s\n' "$(date -Is)"
  printf 'hostname=%s\n' "$(hostname)"
  printf 'qq_state_included=%s\n' "$include_qq"
  printf 'napcat_quiesced=%s\n' "$napcat_quiesced"
  printf 'git_commit=%s\n' "$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo uncommitted)"
  printf 'napcat_image_ref=%s\n' "$napcat_image_ref"
  printf 'napcat_image_id=%s\n' "$napcat_image_id"
  printf 'napcat_repo_digests=%s\n' "$napcat_repo_digests"
  docker_cmd version --format 'docker_server={{.Server.Version}}' 2>/dev/null || true
  docker_cmd compose version --short 2>/dev/null | sed 's/^/docker_compose=/' || true
} > "$payload/MANIFEST.txt"

tar -C "$payload" -czf "$partial" .
chmod 0600 "$partial"
mv "$partial" "$archive"
sha256sum "$archive" > "$archive.sha256"
chmod 0600 "$archive.sha256"

mapfile -t archives < <(
  find "$backup_dir" -maxdepth 1 -type f -name 'qqbot-*.tar.gz' \
    -printf '%T@|%p\n' | sort -rn | cut -d'|' -f2-
)
if [ "${#archives[@]}" -gt "$keep_count" ]; then
  for old_archive in "${archives[@]:$keep_count}"; do
    rm -f -- "$old_archive" "$old_archive.sha256"
  done
fi

printf 'BACKUP_PATH=%s\n' "$archive"
printf 'Backup created: %s\n' "$archive"
if "$include_qq"; then
  echo "Sensitive QQ login state was included; archive mode is 600."
else
  echo "QQ login state was not included. Use --include-qq-state for a sensitive full backup."
fi

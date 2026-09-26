#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

usage() {
  cat >&2 <<USAGE
Usage:
  $0 nonebot
  $0 napcat 'mlikiowa/napcat-docker:vX.Y.Z@sha256:<64 hex>'

The NoneBot path rebuilds only from the committed uv.lock.
The NapCat path requires an explicit official tag and digest; latest is rejected.
USAGE
  exit 2
}

wait_nonebot_healthy() {
  local deadline=$((SECONDS + 120))
  local status
  while [ "$SECONDS" -lt "$deadline" ]; do
    status=$(docker_cmd inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' qqbot-nonebot 2>/dev/null || true)
    if [ "$status" = "healthy" ]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_napcat_stable() {
  local stable_checks=0
  local state
  local previous_restarts=-1
  local restarts
  for _ in $(seq 1 20); do
    state=$(docker_cmd inspect --format '{{.State.Status}}' qqbot-napcat 2>/dev/null || true)
    restarts=$(docker_cmd inspect --format '{{.RestartCount}}' qqbot-napcat 2>/dev/null || echo -1)
    if [ "$state" = "running" ] && [ "$restarts" = "$previous_restarts" ]; then
      stable_checks=$((stable_checks + 1))
      if [ "$stable_checks" -ge 5 ]; then
        return 0
      fi
    else
      stable_checks=0
    fi
    previous_restarts=$restarts
    sleep 2
  done
  return 1
}

restore_napcat_state() (
  set -euo pipefail
  local archive=$1
  local restore_dir
  local manifest
  local forensic_dir

  if [ ! -f "$archive" ] || [ ! -f "$archive.sha256" ]; then
    echo "Cold backup or checksum is missing: $archive" >&2
    return 1
  fi
  sha256sum -c "$archive.sha256" >/dev/null

  restore_dir=$(mktemp -d "$PROJECT_ROOT/backups/.napcat-restore-$timestamp.XXXXXX")
  case "$restore_dir" in
    "$PROJECT_ROOT"/backups/.napcat-restore-*)
      ;;
    *)
      echo "Unexpected restore temporary path" >&2
      return 1
      ;;
  esac
  trap 'rm -rf -- "$restore_dir"' EXIT
  tar -xzf "$archive" -C "$restore_dir"

  manifest="$restore_dir/MANIFEST.txt"
  if ! grep -qx 'qq_state_included=true' "$manifest" || ! grep -qx 'napcat_quiesced=true' "$manifest" || [ ! -f "$restore_dir/napcat/QQ_STATE_WARNING.txt" ] || [ ! -d "$restore_dir/napcat/config" ] || [ ! -d "$restore_dir/napcat/qq" ]; then
    echo "Backup is not a complete quiesced NapCat state backup." >&2
    return 1
  fi

  forensic_dir="$PROJECT_ROOT/backups/napcat-failed-$timestamp"
  if [ -e "$forensic_dir" ]; then
    echo "Forensic rollback directory already exists: $forensic_dir" >&2
    return 1
  fi
  mkdir -m 0700 "$forensic_dir"

  if [ -e "$PROJECT_ROOT/napcat/config" ]; then
    mv "$PROJECT_ROOT/napcat/config" "$forensic_dir/config.after-candidate"
  fi
  if [ -e "$PROJECT_ROOT/napcat/qq" ]; then
    mv "$PROJECT_ROOT/napcat/qq" "$forensic_dir/qq.after-candidate"
  fi

  cp -a "$restore_dir/napcat/config" "$PROJECT_ROOT/napcat/config"
  cp -a "$restore_dir/napcat/qq" "$PROJECT_ROOT/napcat/qq"
  chmod 0700 "$PROJECT_ROOT/napcat/config" "$PROJECT_ROOT/napcat/qq"
  printf 'Failed candidate state preserved at: %s\n' "$forensic_dir"
)

persist_env_value() {
  local key=$1
  local value=$2
  python3 - "$PROJECT_ROOT/.env" "$key" "$value" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
replacement = f"{key}={value}"
updated = False
result: list[str] = []
for line in lines:
    if line.startswith(f"{key}="):
        result.append(replacement)
        updated = True
    else:
        result.append(line)
if not updated:
    result.append(replacement)

temporary = path.with_name(path.name + ".tmp")
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    stream.write("\n".join(result) + "\n")
os.replace(temporary, path)
os.chmod(path, 0o600)
PY
}

record_update() {
  local kind=$1
  local old_value=$2
  local new_value=$3
  local rollback_ref=$4
  local backup_path=$5
  local verification_status=$6
  local record="$PROJECT_ROOT/backups/update-$timestamp-$kind.txt"
  {
    printf 'created_at=%s\n' "$(date -Is)"
    printf 'kind=%s\n' "$kind"
    printf 'old=%s\n' "$old_value"
    printf 'new=%s\n' "$new_value"
    printf 'git_commit=%s\n' "$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unavailable)"
    printf 'rollback_ref=%s\n' "$rollback_ref"
    printf 'backup_path=%s\n' "$backup_path"
    printf 'verification_status=%s\n' "$verification_status"
  } > "$record"
  chmod 0600 "$record"
  printf 'Update record: %s\n' "$record"
}

[ "$#" -ge 1 ] || usage
kind=$1
shift
timestamp=$(date +%Y%m%d-%H%M%S)

if [ ! -f "$PROJECT_ROOT/.env" ]; then
  echo ".env is missing; refusing to update." >&2
  exit 1
fi

case "$kind" in
  nonebot)
    [ "$#" -eq 0 ] || usage
    if ! git -C "$PROJECT_ROOT" rev-parse --verify HEAD >/dev/null 2>&1; then
      echo "NoneBot update requires an existing Git commit." >&2
      exit 1
    fi
    if [ -n "$(git -C "$PROJECT_ROOT" status --porcelain)" ]; then
      echo "NoneBot update requires a clean Git worktree." >&2
      exit 1
    fi
    ;;
  napcat)
    [ "$#" -eq 1 ] || usage
    target=$1
    if [[ "$target" == *latest* ]] || ! [[ "$target" =~ ^(docker\.io/)?mlikiowa/napcat-docker:v[0-9][A-Za-z0-9._-]*@sha256:[0-9a-f]{64}$ ]]; then
      echo "NapCat target must be an official explicit v-tag plus full sha256 digest; latest is forbidden." >&2
      exit 2
    fi
    ;;
  *)
    usage
    ;;
esac

case "$kind" in
  nonebot)
    echo "[phase 1] create backup"
    backup_output=$("$SCRIPT_DIR/backup.sh")
    printf '%s\n' "$backup_output"
    backup_path=$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_PATH=//p' | tail -n 1)
    [ -n "$backup_path" ] || {
      echo "Backup path was not reported." >&2
      exit 1
    }

    echo "[phase 2] record current NoneBot image"
    nonebot_image=$(compose config --images | sed -n '/^qqbot-nonebot:/p' | head -n 1)
    if [ -z "$nonebot_image" ]; then
      echo "Unable to resolve the NoneBot image from Compose." >&2
      exit 1
    fi
    old_id=$(docker_cmd inspect --format '{{.Image}}' qqbot-nonebot 2>/dev/null || true)
    if [ -z "$old_id" ]; then
      old_id=$(docker_cmd image inspect --format '{{.Id}}' "$nonebot_image" 2>/dev/null || true)
    fi
    if [ -n "$old_id" ]; then
      docker_cmd image tag "$old_id" "qqbot-nonebot:rollback-$timestamp"
    fi

    echo "[phase 3] build strictly from pyproject.toml and uv.lock"
    compose build nonebot

    echo "[phase 4] recreate NoneBot and wait for process health"
    if ! compose up -d --no-deps nonebot || ! wait_nonebot_healthy; then
      echo "New NoneBot image failed health validation." >&2
      if [ -n "$old_id" ]; then
        echo "Rolling back to the previous local image." >&2
        docker_cmd image tag "$old_id" "$nonebot_image"
        compose up -d --no-deps --force-recreate nonebot
        if ! wait_nonebot_healthy; then
          echo "Previous image is not healthy; preserve the backup and follow scripts/restore.md." >&2
          exit 1
        fi
      fi
      echo "Image rollback does not undo database migrations or bind-mounted Prompt/Skill changes." >&2
      exit 1
    fi
    new_id=$(docker_cmd image inspect --format '{{.Id}}' "$nonebot_image")
    record_update nonebot "${old_id:-none}" "$new_id" "qqbot-nonebot:rollback-$timestamp" "$backup_path" "healthcheck_passed"
    ;;

  napcat)
    old_target=$(sed -n 's/^NAPCAT_IMAGE=//p' "$PROJECT_ROOT/.env" | tail -n 1)
    if [ -z "$old_target" ]; then
      old_target='mlikiowa/napcat-docker:v4.18.19@sha256:1336a777f9a4f1f8cb89fef42f7548deacd3645919a067a50df5b66b5e77390e'
    fi
    was_running=$(docker_cmd inspect --format '{{.State.Running}}' qqbot-napcat 2>/dev/null || echo false)

    echo "[phase 1] pull explicit NapCat target while the current service remains unchanged"
    pulled=false
    for attempt in 1 2 3; do
      printf 'pull attempt %d/3\n' "$attempt"
      if docker_cmd pull "$target"; then
        pulled=true
        break
      fi
      sleep 5
    done
    "$pulled" || {
      echo "NapCat pull failed after three attempts." >&2
      exit 1
    }

    echo "[phase 2] stop NapCat and create a consistent sensitive state backup"
    compose stop napcat >/dev/null 2>&1 || true
    backup_output=$("$SCRIPT_DIR/backup.sh" --include-qq-state)
    printf '%s\n' "$backup_output"
    backup_path=$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_PATH=//p' | tail -n 1)
    [ -n "$backup_path" ] || {
      echo "Cold backup path was not reported; NapCat remains stopped." >&2
      exit 1
    }

    echo "[phase 3] start candidate without persisting it"
    if ! compose_with_napcat_image "$target" up -d --no-deps --force-recreate napcat || ! wait_napcat_stable; then
      echo "Candidate NapCat was not process-stable; restoring previous state and image." >&2
      compose stop napcat >/dev/null 2>&1 || true
      restore_napcat_state "$backup_path"
      if [ "$was_running" = "true" ]; then
        compose_with_napcat_image "$old_target" up -d --no-deps --force-recreate napcat
      else
        compose_with_napcat_image "$old_target" up -d --no-deps --force-recreate napcat
        compose stop napcat >/dev/null 2>&1 || true
      fi
      record_update napcat "$old_target" "$target" "$old_target" "$backup_path" "rollback_completed_after_failed_candidate"
      exit 1
    fi

    echo "[phase 4] persist process-stable candidate reference"
    persist_env_value NAPCAT_IMAGE "$target"
    record_update napcat "$old_target" "$target" "$old_target" "$backup_path" "pending_manual_qq_ws_command_verification"
    echo "Candidate is only process-stable, not fully verified."
    echo "Keep the old image and cold backup until QQ login, Reverse WS, ping and help pass."
    ;;

  *)
    usage
    ;;
esac

echo "[phase 5] current status"
"$SCRIPT_DIR/status.sh"

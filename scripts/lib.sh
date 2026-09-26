#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null; then
  DOCKER=(sudo docker)
else
  echo "Docker is unavailable. Run as a user with Docker access or sudo." >&2
  exit 1
fi

docker_cmd() {
  "${DOCKER[@]}" "$@"
}

compose() {
  "${DOCKER[@]}" compose \
    --project-directory "$PROJECT_ROOT" \
    -f "$COMPOSE_FILE" \
    "$@"
}

# An explicit Compose override survives sudo's environment filtering. Never
# preserve the caller's entire environment merely to select one public image.
compose_with_napcat_image() (
  set -euo pipefail
  local image=$1
  shift
  if ! [[ "$image" =~ ^(docker\.io/)?mlikiowa/napcat-docker:v[0-9][A-Za-z0-9._-]*@sha256:[0-9a-f]{64}$ ]]; then
    echo "NapCat image must contain an official version tag and digest." >&2
    return 2
  fi
  local override
  override=$(mktemp "$PROJECT_ROOT/.compose-napcat.XXXXXX.yaml")
  trap 'rm -f -- "$override"' EXIT
  chmod 0600 "$override"
  printf 'services:\n  napcat:\n    image: "%s"\n' "$image" > "$override"
  compose -f "$override" "$@"
)

redact_logs() {
  python3 "$SCRIPT_DIR/redact_logs.py" "$PROJECT_ROOT/.env"
}

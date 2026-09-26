#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -t 0 || ! -t 1 ]]; then
  echo "This command must be run interactively in an SSH terminal." >&2
  exit 2
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

read -r -s -p "QQ password (input hidden): " password
printf '\n'
read -r -s -p "Confirm QQ password: " password_confirm
printf '\n'

if [ -z "$password" ]; then
  unset password password_confirm
  echo "Password must not be empty." >&2
  exit 2
fi

if [ "$password" != "$password_confirm" ]; then
  unset password password_confirm
  echo "Passwords do not match." >&2
  exit 2
fi

digest=$(printf '%s' "$password" | md5sum)
digest=${digest%% *}
unset password password_confirm

if ! [[ "$digest" =~ ^[a-f0-9]{32}$ ]]; then
  unset digest
  echo "Failed to calculate a valid password digest." >&2
  exit 1
fi

umask 077
temp_file=$(mktemp "$PROJECT_ROOT/.env.qq-password.XXXXXX")
cleanup() {
  rm -f -- "$temp_file"
}
trap cleanup EXIT HUP INT TERM

found=false
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    NAPCAT_QUICK_PASSWORD=*)
      # Never retain a raw QQ password in the environment file.
      ;;
    NAPCAT_QUICK_PASSWORD_MD5=*)
      printf 'NAPCAT_QUICK_PASSWORD_MD5=%s\n' "$digest"
      found=true
      ;;
    *)
      printf '%s\n' "$line"
      ;;
  esac
done < "$ENV_FILE" > "$temp_file"

if ! "$found"; then
  printf 'NAPCAT_QUICK_PASSWORD_MD5=%s\n' "$digest" >> "$temp_file"
fi

chmod 600 "$temp_file"
mv -f -- "$temp_file" "$ENV_FILE"
trap - EXIT HUP INT TERM
unset digest

if [ "$(stat -c '%a' "$ENV_FILE")" != 600 ]; then
  echo "Refusing to continue: .env permissions are not 600." >&2
  exit 1
fi

compose config --quiet

echo "QQ password fallback credential stored in .env (mode 600)."
echo "Recreate NapCat only when you intentionally want to apply this fallback."

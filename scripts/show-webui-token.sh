#!/usr/bin/env bash
set -Eeuo pipefail

# This command intentionally displays one secret. Refuse pipes/redirection so
# it cannot be accidentally captured by a log file or another process.
set +x
export LC_ALL=C

script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(CDPATH='' cd -- "${script_dir}/.." && pwd)"
env_file="${project_root}/.env"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

[[ -t 1 ]] || die "refusing to print the WebUI token to a pipe or redirected file"
[[ -f "${env_file}" && ! -L "${env_file}" ]] || die "missing regular .env file; run setup first"

token=""
while IFS= read -r line || [[ -n "${line}" ]]; do
  line="${line%$'\r'}"
  if [[ "${line%%=*}" == "NAPCAT_WEBUI_TOKEN" ]]; then
    token="${line#*=}"
    break
  fi
done <"${env_file}"

[[ "${#token}" -ge 32 && "${token}" =~ ^[A-Za-z0-9._~-]+$ ]] \
  || die "NAPCAT_WEBUI_TOKEN is missing or still a placeholder"

printf 'NapCat WebUI token (keep it private):\n%s\n' "${token}"
unset token

#!/usr/bin/env bash
set -Eeuo pipefail

export LC_ALL=C
umask 077

script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(CDPATH='' cd -- "${script_dir}/.." && pwd)"
compose_file="${project_root}/docker-compose.yml"
env_example="${project_root}/.env.example"
env_file="${project_root}/.env"
onebot_config="${project_root}/napcat/config/onebot11.json"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

on_error() {
  printf 'Setup stopped at line %s. Existing .env and persistent data were not deleted.\n' "$1" >&2
}
trap 'on_error "$LINENO"' ERR

[[ "$(uname -s)" == "Linux" ]] || die "this setup script must run on Linux"
[[ -r /etc/os-release ]] || die "/etc/os-release is missing"
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || die "only Ubuntu 22.04 and 24.04 are supported"
case "${VERSION_ID:-}" in
  22.04|24.04) ;;
  *) die "unsupported Ubuntu version: ${VERSION_ID:-unknown}" ;;
esac
case "$(uname -m)" in
  x86_64|aarch64|arm64) ;;
  *) die "unsupported CPU architecture: $(uname -m)" ;;
esac

[[ -f "${compose_file}" ]] || die "missing ${compose_file}"
[[ -f "${env_example}" ]] || die "missing ${env_example}"

docker_ready=false
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker_ready=true
fi

if ! ${docker_ready}; then
  printf 'Docker Engine or the Compose plugin is missing.\n'
  if [[ "${EUID}" -eq 0 ]]; then
    bash "${script_dir}/install-docker.sh"
  else
    command -v sudo >/dev/null 2>&1 || die "sudo is required to install Docker"
    sudo bash "${script_dir}/install-docker.sh"
  fi
fi

if docker info >/dev/null 2>&1; then
  docker_command=(docker)
elif [[ "${EUID}" -eq 0 ]] && docker info >/dev/null 2>&1; then
  docker_command=(docker)
elif command -v sudo >/dev/null 2>&1; then
  printf 'Docker requires elevated access; sudo may ask for your password.\n'
  sudo docker info >/dev/null
  docker_command=(sudo docker)
else
  die "the current user cannot access the Docker daemon"
fi

compose() {
  "${docker_command[@]}" compose \
    --project-directory "${project_root}" \
    -f "${compose_file}" \
    "$@"
}

generate_token() {
  local token
  token="$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')"
  [[ "${#token}" -eq 64 ]] || die "secure token generation failed"
  printf '%s' "${token}"
}

set_env_value() {
  local target_file="$1"
  local wanted_key="$2"
  local wanted_value="$3"
  local temporary_file line key found=false
  temporary_file="$(mktemp "${target_file}.tmp.XXXXXX")"

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    key="${line%%=*}"
    if [[ "${key}" == "${wanted_key}" ]]; then
      printf '%s=%s\n' "${wanted_key}" "${wanted_value}" >>"${temporary_file}"
      found=true
    else
      printf '%s\n' "${line}" >>"${temporary_file}"
    fi
  done <"${target_file}"
  if ! ${found}; then
    printf '%s=%s\n' "${wanted_key}" "${wanted_value}" >>"${temporary_file}"
  fi

  chmod 0600 "${temporary_file}"
  mv -f -- "${temporary_file}" "${target_file}"
}

get_env_value() {
  local wanted_key="$1"
  local line key value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    key="${line%%=*}"
    if [[ "${key}" == "${wanted_key}" ]]; then
      value="${line#*=}"
      printf '%s' "${value}"
      return 0
    fi
  done <"${env_file}"
  return 1
}

is_safe_token() {
  local value="$1"
  [[ "${#value}" -ge 32 && "${value}" =~ ^[A-Za-z0-9._~-]+$ ]]
}

created_env=false
if [[ -e "${env_file}" ]]; then
  [[ -f "${env_file}" && ! -L "${env_file}" ]] || die "refusing to use a non-regular .env file"
  chmod 0600 "${env_file}"
  printf 'Keeping the existing .env file unchanged.\n'
else
  [[ -t 0 || -r /dev/tty ]] || die "first-time setup requires an interactive terminal"

  napcat_account=""
  while :; do
    printf 'Bot QQ number (input hidden): ' >/dev/tty
    IFS= read -r -s napcat_account </dev/tty
    printf '\n' >/dev/tty
    if [[ "${napcat_account}" =~ ^[1-9][0-9]{4,11}$ ]]; then
      break
    fi
    printf 'Please enter 5 to 12 digits, without spaces.\n' >&2
  done

  superuser=""
  while :; do
    printf 'Administrator QQ number (optional, press Enter to skip): ' >/dev/tty
    IFS= read -r superuser </dev/tty
    if [[ -z "${superuser}" || "${superuser}" =~ ^[1-9][0-9]{4,11}$ ]]; then
      break
    fi
    printf 'Please enter 5 to 12 digits, or leave it empty.\n' >&2
  done

  runtime_uid="${SUDO_UID:-$(id -u)}"
  runtime_gid="${SUDO_GID:-$(id -g)}"
  if [[ "${runtime_uid}" == "0" ]]; then
    runtime_uid=1000
  fi
  if [[ "${runtime_gid}" == "0" ]]; then
    runtime_gid=1000
  fi

  onebot_token="$(generate_token)"
  webui_token="$(generate_token)"
  [[ "${onebot_token}" != "${webui_token}" ]] || die "token generation produced duplicate values"

  env_tmp="$(mktemp "${project_root}/.env.new.XXXXXX")"
  cp -- "${env_example}" "${env_tmp}"
  chmod 0600 "${env_tmp}"
  set_env_value "${env_tmp}" NAPCAT_ACCOUNT "${napcat_account}"
  set_env_value "${env_tmp}" SUPERUSERS "${superuser}"
  set_env_value "${env_tmp}" ONEBOT_ACCESS_TOKEN "${onebot_token}"
  set_env_value "${env_tmp}" NAPCAT_WEBUI_TOKEN "${webui_token}"
  set_env_value "${env_tmp}" APP_UID "${runtime_uid}"
  set_env_value "${env_tmp}" APP_GID "${runtime_gid}"
  set_env_value "${env_tmp}" NAPCAT_UID "${runtime_uid}"
  set_env_value "${env_tmp}" NAPCAT_GID "${runtime_gid}"

  if [[ -e "${env_file}" ]]; then
    rm -f -- "${env_tmp}"
    die ".env appeared during setup; it was not overwritten"
  fi
  mv -- "${env_tmp}" "${env_file}"
  created_env=true
  unset napcat_account superuser runtime_uid runtime_gid webui_token
  printf 'Created .env with mode 600 and independent random tokens.\n'
fi

napcat_account="$(get_env_value NAPCAT_ACCOUNT || true)"
onebot_token="$(get_env_value ONEBOT_ACCESS_TOKEN || true)"
webui_token="$(get_env_value NAPCAT_WEBUI_TOKEN || true)"
[[ "${napcat_account}" =~ ^[1-9][0-9]{4,11}$ ]] || die "NAPCAT_ACCOUNT in .env is missing or invalid; .env was not modified"
is_safe_token "${onebot_token}" || die "ONEBOT_ACCESS_TOKEN in .env must be at least 32 safe characters; .env was not modified"
is_safe_token "${webui_token}" || die "NAPCAT_WEBUI_TOKEN in .env must be at least 32 safe characters; .env was not modified"
[[ "${onebot_token}" != "${webui_token}" ]] || die "OneBot and WebUI tokens must be different"

install -d -m 0700 \
  "${project_root}/data/nonebot" \
  "${project_root}/napcat/config" \
  "${project_root}/napcat/qq" \
  "${project_root}/backups"

app_uid="$(get_env_value APP_UID || printf '1000')"
app_gid="$(get_env_value APP_GID || printf '1000')"
[[ "${app_uid}" =~ ^[1-9][0-9]*$ && "${app_gid}" =~ ^[1-9][0-9]*$ ]] \
  || die "APP_UID and APP_GID in .env must be positive integers"
if [[ "${EUID}" -eq 0 ]]; then
  chown "${app_uid}:${app_gid}" \
    "${project_root}/data/nonebot" \
    "${project_root}/napcat/config" \
    "${project_root}/napcat/qq"
fi

if [[ -e "${onebot_config}" ]]; then
  [[ -f "${onebot_config}" && ! -L "${onebot_config}" ]] || die "refusing to use a non-regular NapCat OneBot config"
  chmod 0600 "${onebot_config}"
  printf 'Keeping the existing NapCat OneBot configuration unchanged.\n'
else
  config_tmp="$(mktemp "${project_root}/napcat/config/onebot11.json.tmp.XXXXXX")"
  cat >"${config_tmp}" <<EOF
{
  "network": {
    "httpServers": [],
    "httpSseServers": [],
    "httpClients": [],
    "websocketServers": [],
    "websocketClients": [
      {
        "enable": true,
        "name": "nonebot",
        "url": "ws://nonebot:8080/onebot/v11/ws",
        "reportSelfMessage": false,
        "messagePostFormat": "array",
        "token": "${onebot_token}",
        "debug": false,
        "heartInterval": 30000,
        "reconnectInterval": 30000
      }
    ],
    "plugins": []
  },
  "musicSignUrl": "",
  "enableLocalFile2Url": false,
  "parseMultMsg": false
}
EOF
  chmod 0600 "${config_tmp}"
  mv -- "${config_tmp}" "${onebot_config}"
  printf 'Created the NapCat Reverse WebSocket configuration.\n'
fi

if [[ "${EUID}" -eq 0 ]]; then
  chown "${app_uid}:${app_gid}" "${onebot_config}"
fi

unset onebot_token webui_token

# Fail before starting anything if the repository no longer binds WebUI to
# loopback. Reverse WS means ports 3000, 3001 and 8080 do not need host maps.
grep -Fq '127.0.0.1:6099:6099' "${compose_file}" \
  || die "docker-compose.yml must bind NapCat WebUI as 127.0.0.1:6099:6099"

printf 'Validating Docker Compose configuration...\n'
compose config --quiet

printf 'Building the NoneBot image (the first build can take several minutes)...\n'
compose build nonebot

printf 'Starting services...\n'
compose up -d

mapfile -t webui_bindings < <(compose port napcat 6099 2>/dev/null || true)
if ((${#webui_bindings[@]} == 0)); then
  die "NapCat started without the expected WebUI port mapping"
fi
for binding in "${webui_bindings[@]}"; do
  if [[ "${binding}" != 127.0.0.1:* ]]; then
    compose stop napcat >/dev/null 2>&1 || true
    die "unsafe NapCat WebUI binding detected; NapCat was stopped"
  fi
done

compose ps

printf '\nInitial deployment is running.\n'
printf '1. On your own computer, open an SSH tunnel:\n'
printf '   ssh -N -L 6099:127.0.0.1:6099 <SSH_USER>@<SERVER_IP>\n'
printf '2. On the server, reveal the WebUI token only in your terminal:\n'
printf '   bash scripts/show-webui-token.sh\n'
printf '3. Open http://127.0.0.1:6099/webui and scan the QQ login QR code.\n'
printf '4. After login, check the connection with: bash scripts/status.sh\n'
printf '\nThe WebUI, OneBot endpoint and NoneBot port are not published to the public network.\n'

if ${created_env}; then
  printf 'AI remains disabled by default. Configure it later with: bash scripts/set-ai-config.sh\n'
fi

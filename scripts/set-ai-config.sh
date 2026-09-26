#!/usr/bin/env bash
set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${project_root}/.env"

if [[ ! -f "${env_file}" ]]; then
    echo "Missing ${env_file}; create it from .env.example first." >&2
    exit 1
fi

read -r -p "OpenAI-compatible Base URL (for example https://host/v1): " ai_base_url
read -r -p "Model name: " ai_model
read -r -p "Private chat mode [all/off] (default all): " ai_private_mode
read -r -p "Group chat mode [mention/all/off] (default mention): " ai_group_mode
ai_private_mode="${ai_private_mode:-all}"
ai_group_mode="${ai_group_mode:-mention}"
read -r -s -p "API Key (hidden): " ai_api_key
printf '\n'

if [[ ! "${ai_base_url}" =~ ^https?://[^[:space:]]+$ ]]; then
    echo "Base URL must be an http:// or https:// URL without whitespace." >&2
    exit 1
fi
if [[ -z "${ai_model}" || "${ai_model}" == *$'\n'* || "${ai_model}" == *$'\r'* ]]; then
    echo "Model name cannot be empty or contain newlines." >&2
    exit 1
fi
if [[ -z "${ai_api_key}" || "${ai_api_key}" == *$'\n'* || "${ai_api_key}" == *$'\r'* ]]; then
    echo "API Key cannot be empty or contain newlines." >&2
    exit 1
fi
if [[ "${ai_private_mode}" != "all" && "${ai_private_mode}" != "off" ]]; then
    echo "Private mode must be all or off." >&2
    exit 1
fi
if [[ "${ai_group_mode}" != "mention" && "${ai_group_mode}" != "all" && "${ai_group_mode}" != "off" ]]; then
    echo "Group mode must be mention, all, or off." >&2
    exit 1
fi

umask 077
temporary_file="$(mktemp "${env_file}.tmp.XXXXXX")"
trap 'rm -f -- "${temporary_file}"' EXIT

declare -A updates=(
    [AI_ENABLED]="true"
    [AI_BASE_URL]="${ai_base_url%/}"
    [AI_API_KEY]="${ai_api_key}"
    [AI_MODEL]="${ai_model}"
    [AI_PRIVATE_MODE]="${ai_private_mode}"
    [AI_GROUP_MODE]="${ai_group_mode}"
)

# Compose interpolates dollar signs in unquoted/double-quoted dotenv values.
# Single quotes preserve provider credentials, spaces and URL fragments.
dotenv_quote() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\'/\\\'}
    printf "'%s'" "$value"
}
for key in AI_BASE_URL AI_API_KEY AI_MODEL; do
    updates[$key]="$(dotenv_quote "${updates[$key]}")"
done

while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    key="${line%%=*}"
    if [[ -v "updates[${key}]" ]]; then
        printf '%s=%s\n' "${key}" "${updates[${key}]}" >> "${temporary_file}"
        unset 'updates['"${key}"']'
    else
        printf '%s\n' "${line}" >> "${temporary_file}"
    fi
done < "${env_file}"

for key in AI_ENABLED AI_PRIVATE_MODE AI_GROUP_MODE AI_BASE_URL AI_API_KEY AI_MODEL; do
    if [[ -v "updates[${key}]" ]]; then
        printf '%s=%s\n' "${key}" "${updates[${key}]}" >> "${temporary_file}"
    fi
done

chmod 600 "${temporary_file}"
mv -f -- "${temporary_file}" "${env_file}"
trap - EXIT
unset ai_api_key updates

echo "AI configuration saved securely in ${env_file}."
echo "The API Key was not printed. Rebuild/restart only NoneBot to apply it."

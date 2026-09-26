#!/usr/bin/env bash
set -Eeuo pipefail

# Install Docker Engine and the Compose plugin from Docker's official APT
# repository. This script is intentionally interactive and never pipes a
# downloaded script into a shell.

export LC_ALL=C

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  die "run this installer as root (for example: sudo bash scripts/install-docker.sh)"
fi

[[ -r /etc/os-release ]] || die "/etc/os-release is missing"
# shellcheck disable=SC1091
. /etc/os-release

[[ "${ID:-}" == "ubuntu" ]] || die "only Ubuntu 22.04 and 24.04 are supported"
case "${VERSION_ID:-}" in
  22.04|24.04) ;;
  *) die "unsupported Ubuntu version: ${VERSION_ID:-unknown} (expected 22.04 or 24.04)" ;;
esac

arch="$(dpkg --print-architecture)"
case "${arch}" in
  amd64|arm64) ;;
  *) die "unsupported CPU architecture: ${arch} (expected amd64 or arm64)" ;;
esac

engine_present=false
compose_present=false
command -v docker >/dev/null 2>&1 && engine_present=true
if ${engine_present} && docker compose version >/dev/null 2>&1; then
  compose_present=true
fi

if ${engine_present} && ${compose_present}; then
  printf 'Docker Engine and Docker Compose are already installed; nothing changed.\n'
  exit 0
fi

if [[ ! -t 0 && ! -r /dev/tty ]]; then
  die "installation requires an interactive terminal for confirmation"
fi

printf '\nThis will add Docker\x27s official APT repository and install:\n'
if ! ${engine_present}; then
  printf '  docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin\n'
fi
printf '  docker-compose-plugin\n\n'
printf 'No remote script will be executed. Continue? [y/N] '
read -r answer </dev/tty
case "${answer}" in
  y|Y|yes|YES) ;;
  *) printf 'Cancelled; nothing changed.\n'; exit 1 ;;
esac

if ! ${engine_present}; then
  conflicting=()
  for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "${package}" 2>/dev/null | grep -q '^install ok installed$'; then
      conflicting+=("${package}")
    fi
  done
  if ((${#conflicting[@]})); then
    printf 'Conflicting packages were detected: %s\n' "${conflicting[*]}" >&2
    printf 'They were not removed automatically. Follow Docker\x27s official uninstall/conflict instructions, then rerun this script:\n' >&2
    printf '  https://docs.docker.com/engine/install/ubuntu/\n' >&2
    exit 1
  fi
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings

key_tmp="$(mktemp /etc/apt/keyrings/docker.asc.tmp.XXXXXX)"
cleanup() {
  rm -f -- "${key_tmp:-}"
}
trap cleanup EXIT
curl --fail --silent --show-error --location \
  --retry 3 --connect-timeout 15 \
  https://download.docker.com/linux/ubuntu/gpg \
  --output "${key_tmp}"
chmod 0644 "${key_tmp}"
mv -f -- "${key_tmp}" /etc/apt/keyrings/docker.asc
key_tmp=""

codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
[[ -n "${codename}" ]] || die "could not determine the Ubuntu codename"

sources_tmp="$(mktemp /etc/apt/sources.list.d/docker.sources.tmp.XXXXXX)"
cat >"${sources_tmp}" <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${codename}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
chmod 0644 "${sources_tmp}"
mv -f -- "${sources_tmp}" /etc/apt/sources.list.d/docker.sources

apt-get update
if ${engine_present}; then
  apt-get install -y docker-compose-plugin
else
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker
docker version >/dev/null
docker compose version
docker run --rm hello-world >/dev/null

trap - EXIT
printf 'Docker Engine and the Docker Compose plugin are ready.\n'

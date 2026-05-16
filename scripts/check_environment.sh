#!/usr/bin/env bash
set -euo pipefail

missing=()

printf 'Environment check\n'
printf '=================\n'

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  printf 'Distro: %s\n' "${PRETTY_NAME:-unknown}"
else
  printf 'Distro: unknown (/etc/os-release not readable)\n'
fi

printf 'Kernel: %s\n' "$(uname -srmo)"
printf '\n'

check_command() {
  local name="$1"
  local label="${2:-$1}"

  if command -v "${name}" >/dev/null 2>&1; then
    printf 'OK: %-10s %s\n' "${label}" "$(command -v "${name}")"
  else
    printf 'MISSING: %s\n' "${label}"
    missing+=("${label}")
  fi
}

check_command python3

if python3 -m venv --help >/dev/null 2>&1; then
  printf 'OK: %-10s available through python3 -m venv\n' "venv"
else
  printf 'MISSING: venv\n'
  missing+=("venv")
fi

if python3 -m pip --version >/dev/null 2>&1; then
  printf 'OK: %-10s %s\n' "pip" "$(python3 -m pip --version)"
elif command -v pip3 >/dev/null 2>&1; then
  printf 'OK: %-10s %s\n' "pip3" "$(command -v pip3)"
else
  printf 'MISSING: pip\n'
  missing+=("pip")
fi

check_command readpst
check_command pffinfo
check_command pffexport

printf '\n'
if [[ "${#missing[@]}" -eq 0 ]]; then
  printf 'All required environment commands are available.\n'
else
  printf 'Missing items: %s\n' "${missing[*]}"
  printf '\n'
  printf 'On Ubuntu/Debian, install missing system dependencies with:\n'
  printf '  sudo apt update\n'
  printf '  sudo apt install -y python3 python3-venv python3-pip pst-utils pff-tools libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0\n'
  printf '\n'
  printf 'This script does not run sudo. Review and run the commands yourself, or ask before allowing sudo execution.\n'
fi

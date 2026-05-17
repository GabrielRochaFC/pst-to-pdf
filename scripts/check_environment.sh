#!/usr/bin/env bash
set -euo pipefail

missing_required=()
missing_optional=()

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

check_required_command() {
  local name="$1"
  local label="${2:-$1}"

  if command -v "${name}" >/dev/null 2>&1; then
    printf 'OK: %-10s %s\n' "${label}" "$(command -v "${name}")"
  else
    printf 'MISSING: %s\n' "${label}"
    missing_required+=("${label}")
  fi
}

check_optional_command() {
  local name="$1"
  local label="${2:-$1}"

  if command -v "${name}" >/dev/null 2>&1; then
    printf 'OK: %-10s %s\n' "${label}" "$(command -v "${name}")"
  else
    printf 'OPTIONAL: %s not found\n' "${label}"
    missing_optional+=("${label}")
  fi
}

check_required_command python3
check_required_command pipx
check_required_command readpst

if python3 -m venv --help >/dev/null 2>&1; then
  printf 'OK: %-10s available through python3 -m venv\n' "venv"
else
  printf 'OPTIONAL: venv not found\n'
  missing_optional+=("venv")
fi

if python3 -m pip --version >/dev/null 2>&1; then
  printf 'OK: %-10s %s\n' "pip" "$(python3 -m pip --version)"
elif command -v pip3 >/dev/null 2>&1; then
  printf 'OK: %-10s %s\n' "pip3" "$(command -v pip3)"
else
  printf 'OPTIONAL: pip not found\n'
  missing_optional+=("pip")
fi

check_optional_command pffinfo
check_optional_command pffexport

printf '\n'
if [[ "${#missing_required[@]}" -eq 0 ]]; then
  printf 'All required environment commands are available.\n'
else
  printf 'Missing required items: %s\n' "${missing_required[*]}"
  printf '\n'
  printf 'On Ubuntu/Debian, install missing system dependencies with:\n'
  printf '  sudo apt update\n'
  printf '  sudo apt install -y python3 pipx pst-utils\n'
  printf '  pipx ensurepath\n'
  printf '\n'
  printf 'This script does not run sudo. Review and run the commands yourself, or ask before allowing sudo execution.\n'
fi

if [[ "${#missing_optional[@]}" -gt 0 ]]; then
  printf '\n'
  printf 'Optional missing items: %s\n' "${missing_optional[*]}"
  printf 'Optional/developer dependencies on Ubuntu/Debian:\n'
  printf '  sudo apt install -y python3-venv python3-pip pff-tools libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0\n'
fi

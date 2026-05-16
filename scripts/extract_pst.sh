#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/extract_pst.sh [--force] <source.pst> <output-eml-dir>

Extracts a PST to EML files with readpst.

Safety:
  - Refuses to overwrite a non-empty output directory unless --force is passed.
  - Does not delete existing data.
  - Does not print email bodies.
USAGE
}

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
  shift
fi

if [[ "$#" -ne 2 ]]; then
  usage >&2
  exit 2
fi

source_pst="$1"
output_dir="$2"

if [[ ! -f "${source_pst}" ]]; then
  printf 'PST not found: %s\n' "${source_pst}" >&2
  exit 1
fi

if ! command -v readpst >/dev/null 2>&1; then
  printf 'Missing readpst. Install it with: sudo apt install -y pst-utils\n' >&2
  exit 1
fi

if [[ -d "${output_dir}" ]] && [[ -n "$(find "${output_dir}" -mindepth 1 -maxdepth 1 -print -quit)" ]] && [[ "${force}" -ne 1 ]]; then
  printf 'Output directory is not empty: %s\n' "${output_dir}" >&2
  printf 'Re-run with --force to allow readpst to write into it. Existing files are not deleted by this script.\n' >&2
  exit 1
fi

mkdir -p "${output_dir}"
mkdir -p "logs"

log_file="logs/extract_$(date +%Y%m%d_%H%M%S).log"
printf 'Extracting PST locally with readpst. Log: %s\n' "${log_file}"
printf 'Source PST: %s\n' "${source_pst}" >>"${log_file}"
printf 'Output EML dir: %s\n' "${output_dir}" >>"${log_file}"

readpst -e -D -o "${output_dir}" "${source_pst}" >>"${log_file}" 2>&1

printf 'Extraction completed. EML output: %s\n' "${output_dir}"

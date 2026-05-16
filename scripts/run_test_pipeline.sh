#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/run_test_pipeline.sh [--process] [--force]

Default behavior:
  - Runs the environment check only.

With --process:
  - Creates .venv if needed.
  - Installs requirements.txt into .venv.
  - Extracts input/teste.pst to output/teste/eml using readpst.
  - Converts extracted EML files to PDFs under output/teste/pdf.
  - Writes output/teste/manifest/teste.csv and logs under logs/.

Safety:
  - Does not run sudo.
  - Does not delete existing data.
  - Refuses non-empty output unless --force is passed.
USAGE
}

process=0
force=0

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --process)
      process=1
      ;;
    --force)
      force=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

scripts/check_environment.sh

if [[ "${process}" -ne 1 ]]; then
  printf '\nEnvironment check complete. Re-run with --process only after approving PST extraction/conversion.\n'
  exit 0
fi

source_pst="input/teste.pst"
eml_dir="output/teste/eml"
pdf_dir="output/teste/pdf"
manifest="output/teste/manifest/teste.csv"
log_file="logs/convert_teste_$(date +%Y%m%d_%H%M%S).log"

if [[ ! -f "${source_pst}" ]]; then
  printf 'Test PST not found: %s\n' "${source_pst}" >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv ".venv"
fi

".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

extract_args=()
convert_args=()
if [[ "${force}" -eq 1 ]]; then
  extract_args+=(--force)
  convert_args+=(--force)
fi

scripts/extract_pst.sh "${extract_args[@]}" "${source_pst}" "${eml_dir}"
".venv/bin/python" scripts/convert_eml_to_pdf.py \
  --source-pst "${source_pst}" \
  --eml-dir "${eml_dir}" \
  --pdf-dir "${pdf_dir}" \
  --manifest "${manifest}" \
  --log-file "${log_file}" \
  "${convert_args[@]}"

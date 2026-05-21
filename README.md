[🇺🇸 English](README.md) · [🇧🇷 Português](docs/README.pt-BR.md) · [🇪🇸 Español](docs/README.es.md)

# pst-to-pdf

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=white)](https://www.kernel.org/)
[![PDF engines](https://img.shields.io/badge/PDF%20engines-ReportLab%20%C2%B7%20WeasyPrint-blue)](https://www.reportlab.com/)
[![Privacy: 100% local](https://img.shields.io/badge/privacy-100%25%20local-brightgreen)](README.md)

Local CLI pipeline for converting Outlook PST archives to PDF. Runs `readpst` to extract EML files, converts them in parallel, and writes a manifest CSV per PST. No cloud services, no external APIs, no internet required after install.

## Features

- Interactive wizard for case setup and job configuration
- Parallel EML→PDF conversion with configurable workers and timeout
- Two PDF engines: `fast` (ReportLab, plain-text) and `weasyprint` (styled HTML)
- Resume support — reads the existing manifest and skips already-converted files
- Manifest CSV tracks every EML with status `ok`, `error`, or `timeout`
- Validation cross-references EML files, PDFs, and manifest rows for consistency
- Safe manifest repair with timestamped backups and dry-run by default
- Email bodies never written to stdout, stderr, or log files

## Requirements

- Linux
- Python 3.10+
- `pipx`
- `readpst` from `pst-utils`

```bash
sudo apt update && sudo apt install pipx pst-utils
pipx ensurepath
```

## Installation

Clone the repository and install locally:

```bash
git clone <repo-url>
cd pst-to-pdf-incra
pipx install --editable . --force
```

> [!NOTE]
> `pipx install pst-to-pdf` will be available once the package is published to PyPI.

## Usage

```bash
pst-to-pdf                  # interactive wizard
pst-to-pdf --dry-run        # preview commands without running
pst-to-pdf --validate-only  # validate existing output, skip conversion
```

The wizard collects: case directory, PST source (folder or comma-separated paths), PDF mode, worker count (default `8`), and timeout (default `60s`). Extraction and conversion start only after explicit confirmation.

### Output layout

```
case-dir/
├── input/
├── output/
│   └── <slug>/
│       ├── eml/
│       ├── pdf/
│       └── manifest/<slug>.csv
└── logs/
```

Slugs are derived from PST filenames; collisions get a SHA-256 suffix.

## PDF Modes

| Mode | Engine | Notes |
|------|--------|-------|
| `fast` *(default)* | ReportLab | Strips `<style>`, `<script>`, `<head>`, `<title>`, `<noscript>`, and HTML comments; no CSS or JS in output |
| `weasyprint` | WeasyPrint | Renders full HTML template; slower, more layout fidelity |

External resource loading is disabled in both modes.

## Advanced Usage

### Script-based pipeline

```bash
python3 scripts/process_user_psts.py --case-dir "/mnt/hd/pst-pdf/example-user"

python3 scripts/convert_eml_to_pdf.py \
  --source-pst input/sample.pst \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv \
  --log-file logs/convert_sample.log \
  --resume

python3 scripts/validate_outputs.py \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv
```

### Manifest repair

```bash
# Dry-run (default)
python3 -m pst_to_pdf.repair_manifest \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --slug example-user-001 --slug example-user-005

# Apply after reviewing dry-run output
python3 -m pst_to_pdf.repair_manifest \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --slug example-user-001,example-user-005 \
  --apply
```

### Optional system packages

```bash
sudo apt install python3 python3-venv python3-pip pff-tools \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`pff-tools` (`pffinfo`, `pffexport`) are fallback inspection tools only; `readpst` is the primary extractor.

## Filtering by email participant

By default, every EML extracted from a PST is converted to a PDF. You can
optionally restrict PDF generation to messages whose participant headers
contain at least one of a list of email addresses.

### Via the wizard

Step 4/5 of the wizard asks:

```
Enable email filter (y/n) [n*]:
```

Answer `y` and provide a comma-separated list:

```
Enter email addresses, separated by commas:
email1@example.com, email2@example.com
```

The wizard stores the normalized list at `case_dir/config/filter_emails.txt`
and a sha256 fingerprint at `case_dir/config/filter_emails.fingerprint`.

### Via CLI (advanced)

```bash
python3 -m pst_to_pdf.processor --case-dir /path/to/case \
  --filter-email a@x.com --filter-email b@y.com

python3 -m pst_to_pdf.processor --case-dir /path/to/case \
  --filter-emails-file /path/to/emails.txt
```

The file format is one email per line; blank lines and `#`-prefixed comments
are ignored. Both flags can be combined; addresses are deduped.

### How matching works

A message matches the filter if any address in any of these headers is in the
filter set:

- `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Sender`

Matching is exact (case-insensitive). The body, subject, and attachment
filenames are **not** checked.

### How non-matching messages are recorded

Non-matching EMLs do not produce PDFs. Instead, the manifest records a row
with `status=filtered`. Filtered rows count as covered EMLs in validation and
never make validation fail.

### Changing the filter

If you want to use a different filter, create a new case directory. Re-running
with a different filter on the same case is blocked by a fingerprint check;
pass `--force-filter` only if you know you want to overwrite the case's stored
filter.

## Development

```bash
python3 -m py_compile \
  pst_to_pdf/__init__.py pst_to_pdf/cli.py pst_to_pdf/processor.py \
  pst_to_pdf/converter.py pst_to_pdf/validator.py pst_to_pdf/extraction.py \
  pst_to_pdf/repair_manifest.py scripts/convert_eml_to_pdf.py \
  scripts/process_user_psts.py scripts/validate_outputs.py

bash -n scripts/check_environment.sh scripts/extract_pst.sh scripts/run_test_pipeline.sh

python3 -m pytest tests/
```

## Publishing Checklist

- [ ] Replace author and URL placeholders in `pyproject.toml`
- [ ] Add license file
- [ ] Add tests for CLI prompts, PST copy collision handling, and dry-run behavior
- [ ] `python -m build`
- [ ] `twine check dist/*`
- [ ] Publish to TestPyPI before PyPI

## License

[MIT](LICENSE)

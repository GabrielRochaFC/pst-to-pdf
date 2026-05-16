# Local PST to PDF Pipeline

This project converts Outlook PST email data into readable PDF files on a local Linux machine. PST, EML, PDF, manifest, and log files stay local.

The scripts do not print email bodies to the terminal and do not use cloud services, online converters, or external APIs.

## System Dependencies

Run:

```bash
scripts/check_environment.sh
```

On Ubuntu/Debian, missing system dependencies can be installed with:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip pst-utils pff-tools libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`readpst` from `pst-utils` is the primary extractor. `pffinfo` and `pffexport` from `pff-tools` are fallback tooling only.

## Python Environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## Recommended Multi-PST Workflow

Use one case directory per person/user. Put all PST files for that person in `input/`:

```text
/mnt/hd/pst-pdf-incra/example-user/
├── input/
│   ├── example.user@example.local.001.pst
│   └── example.user@example.local.002.pst
├── output/
└── logs/
```

Create the input directory and copy PSTs:

```bash
mkdir -p "/mnt/hd/pst-pdf-incra/example-user/input"
cp "$HOME/Downloads/"*.pst "/mnt/hd/pst-pdf-incra/example-user/input/"
```

Run everything with the defaults:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user"
```

Defaults:

- `--mode fast`
- `--workers 8`
- `--timeout-seconds 60`
- conversion resumes safely by default

The output is created per PST:

```text
output/<pst-slug>/eml/
output/<pst-slug>/pdf/
output/<pst-slug>/manifest/<pst-slug>.csv
logs/
```

For `example.user@example.local.001.pst`, the slug is `example-user-001`.

## Resume and Pause

To pause, press `Ctrl+C`. Existing EML, PDF, manifest, and log files are kept.

To resume, run the same command again:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user"
```

The script skips PST extraction when EML files already exist, and it runs conversion with resume behavior.

## Validation

Validate every PST output in the case directory:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user" \
  --validate-only
```

Validation reports total EML files, PDF files, manifest rows, successful rows, failed rows, timeout rows, duplicate EML rows, and missing PDFs for successful rows. It does not print email body content.

## Dry Run

Preview the planned directories and commands without creating files or processing PSTs:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user" \
  --dry-run
```

## Advanced Options

Use fewer workers if the machine becomes overloaded:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user" \
  --workers 4
```

Use WeasyPrint instead of the default fast ReportLab mode:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user" \
  --mode weasyprint
```

Force re-extraction of PSTs into existing EML directories:

```bash
.venv/bin/python scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf-incra/example-user" \
  --force-extract
```

`--force-extract` does not delete existing files; it lets `readpst` write into the existing directory.

## Lower-Level Commands

The lower-level scripts are still available when you need explicit paths.

Extract one PST:

```bash
scripts/extract_pst.sh input/sample.pst output/sample/eml
```

Convert one extracted EML tree:

```bash
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/sample.pst \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv \
  --log-file logs/convert_sample.log \
  --resume
```

Validate one output:

```bash
.venv/bin/python scripts/validate_outputs.py \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv
```

Each PDF includes subject, from, to, cc, bcc, date, message-id, source EML path, attachment filenames, and the email text body. Attachment contents are not embedded.

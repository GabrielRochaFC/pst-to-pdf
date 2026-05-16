# PST to PDF Local Pipeline

This project converts Outlook PST email data into readable PDF files on a local Linux machine. PST, EML, PDF, manifest, and log files stay local.

The scripts do not print email bodies to the terminal and do not use cloud services, online converters, or external APIs.

## System Dependencies

Run the environment check:

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

The converter supports two local PDF engines:

- `--mode fast`: ReportLab text-only PDF generation. This is the default and recommended for large batches.
- `--mode weasyprint`: WeasyPrint rendering from constructed, escaped HTML. External resource loading is disabled.

## Test PST Placement

Place the test PST at:

```text
input/teste.pst
```

The `.gitignore` excludes `input/`, `output/`, `logs/`, PST/OST/EML/PDF/CSV/log files, and `.venv/`.

## Extract PST

```bash
scripts/extract_pst.sh input/teste.pst output/teste/eml
```

If the output directory already contains files, extraction refuses to continue unless `--force` is passed. The script does not delete existing data.

## Convert EML to PDF

Fast mode, recommended for large batches:

```bash
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/teste.pst \
  --eml-dir output/teste/eml \
  --pdf-dir output/teste/pdf \
  --manifest output/teste/manifest/teste.csv \
  --log-file logs/convert_teste_fast.log \
  --mode fast \
  --workers 2 \
  --timeout-seconds 60
```

WeasyPrint mode:

```bash
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/teste.pst \
  --eml-dir output/teste/eml \
  --pdf-dir output/teste/pdf \
  --manifest output/teste/manifest/teste.csv \
  --log-file logs/convert_teste_weasy.log \
  --mode weasyprint \
  --workers 2 \
  --timeout-seconds 120
```

Each PDF includes subject, from, to, cc, bcc, date, message-id, source EML path, attachment filenames, and the email text body. Attachment contents are not embedded.

## Resume Safely

Use `--resume` to continue a partial conversion. On resume, the converter:

- Creates a timestamped backup of the manifest before modifying it.
- Compacts duplicate manifest rows, preferring successful rows.
- Skips EML files that already have a successful manifest row.
- Detects deterministic existing PDF files and records successful manifest rows for them when possible.
- Writes manifest rows only from the main process.

Recommended resume command:

```bash
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/teste.pst \
  --eml-dir output/teste/eml \
  --pdf-dir output/teste/pdf \
  --manifest output/teste/manifest/teste.csv \
  --log-file logs/convert_teste_fast_resume_$(date +%Y%m%d_%H%M%S).log \
  --resume \
  --mode fast \
  --workers 2 \
  --timeout-seconds 60
```

`--workers` controls parallel message conversion. Start with `2` for predictable CPU and memory usage.

`--timeout-seconds` caps one email conversion. Timed-out messages are written as `status=timeout` in the manifest and the batch continues.

Progress is printed every 100 processed messages with converted, recovered, skipped, failed, timeout, and remaining counts. Email bodies are not printed.

## Validate Output

Run:

```bash
.venv/bin/python scripts/validate_outputs.py \
  --eml-dir output/teste/eml \
  --pdf-dir output/teste/pdf \
  --manifest output/teste/manifest/teste.csv
```

The validation reports:

- total EML files
- total PDF files
- total manifest rows
- successful rows
- failed rows
- timeout rows
- duplicate EML rows
- missing PDFs for successful rows

It does not print email body content.

## Run the Test Pipeline

By default, the wrapper runs only the environment check:

```bash
scripts/run_test_pipeline.sh
```

After approving PST processing:

```bash
scripts/run_test_pipeline.sh --process --mode fast --workers 2 --timeout-seconds 60
```

To resume using existing EML output:

```bash
scripts/run_test_pipeline.sh --process --resume --mode fast --workers 2 --timeout-seconds 60
```

## Process Another PST Later

For another PST, choose a new output name:

```bash
scripts/extract_pst.sh input/another.pst output/another/eml
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/another.pst \
  --eml-dir output/another/eml \
  --pdf-dir output/another/pdf \
  --manifest output/another/manifest/another.csv \
  --log-file logs/convert_another.log \
  --mode fast \
  --workers 2 \
  --timeout-seconds 60
```

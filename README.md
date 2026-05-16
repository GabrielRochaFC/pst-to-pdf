# PST to PDF Local Pipeline

This project converts Outlook PST email data into readable PDF files on a local Linux machine. It is designed for institutional processing where PST, EML, PDF, manifest, and log files must remain local.

The scripts do not print email bodies to the terminal and do not use cloud services, online converters, or external APIs.

## System Dependencies

Run the environment check first:

```bash
scripts/check_environment.sh
```

On Ubuntu/Debian, missing system dependencies can be installed with:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip pst-utils pff-tools libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`readpst` from `pst-utils` is the primary extractor. `pffinfo` and `pffexport` from `pff-tools` are checked and documented as fallback tooling only.

## Python Environment

Create the virtual environment and install local Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

The PDF converter uses WeasyPrint locally. It receives constructed HTML generated from parsed email headers and text, with external resource loading disabled.

## Test PST Placement

Place the test PST at:

```text
input/teste.pst
```

The `.gitignore` excludes `input/`, `output/`, `logs/`, PST/OST/EML/PDF/CSV/log files, and `.venv/`.

## Run Extraction

Extract the test PST into EML files:

```bash
scripts/extract_pst.sh input/teste.pst output/teste/eml
```

If the output directory already contains files, the script refuses to continue. To allow writing into an existing directory without deleting it:

```bash
scripts/extract_pst.sh --force input/teste.pst output/teste/eml
```

## Run PDF Conversion

Convert EML files to PDFs and create a manifest:

```bash
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/teste.pst \
  --eml-dir output/teste/eml \
  --pdf-dir output/teste/pdf \
  --manifest output/teste/manifest/teste.csv \
  --log-file logs/convert_teste.log
```

Use `--force` only when you intentionally want to write into existing output locations.

## Run the Test Pipeline

By default, the test pipeline runs only the environment check:

```bash
scripts/run_test_pipeline.sh
```

After approving PST processing, run:

```bash
scripts/run_test_pipeline.sh --process
```

Use `--force` only for intentional reruns into existing output:

```bash
scripts/run_test_pipeline.sh --process --force
```

## Output Layout

Expected test output:

```text
output/teste/eml/
output/teste/pdf/
output/teste/manifest/teste.csv
logs/
```

Each manifest row records source PST path, PST SHA256, EML path, PDF path, subject, from, to, cc, bcc, date, message-id, attachment filenames, status, and error.

Each PDF includes a header with subject, from, to, cc, bcc, date, message-id, source EML path, and attachment filenames, followed by the email text body. Attachment contents are not embedded.

## Validate Output

Check counts without printing email content:

```bash
find output/teste/eml -type f -name '*.eml' | wc -l
find output/teste/pdf -type f -name '*.pdf' | wc -l
wc -l output/teste/manifest/teste.csv
```

Inspect logs for failures:

```bash
ls -lh logs/
```

Do not print EML or PDF contents in the terminal.

## Process Another PST Later

For another PST, choose a new output name:

```bash
scripts/extract_pst.sh input/another.pst output/another/eml
.venv/bin/python scripts/convert_eml_to_pdf.py \
  --source-pst input/another.pst \
  --eml-dir output/another/eml \
  --pdf-dir output/another/pdf \
  --manifest output/another/manifest/another.csv \
  --log-file logs/convert_another.log
```

## Fallback Note

If `readpst` cannot extract a specific PST, use `pffinfo` for diagnostics and consider `pffexport` as a fallback extractor. Keep fallback output under `output/<name>/` and do not commit generated data.

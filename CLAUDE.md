# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Development install (editable):**
```bash
pipx install --editable . --force
```

**Run the CLI wizard:**
```bash
pst-to-pdf
pst-to-pdf --dry-run
pst-to-pdf --validate-only
python3 -m pst_to_pdf.cli --help
```

**Run all tests:**
```bash
python3 -m pytest tests/
# or without pytest:
python3 -m unittest discover tests/
```

**Run a single test file:**
```bash
python3 -m pytest tests/test_html_text_extraction.py
python3 -m unittest tests.test_output_helpers
```

**Syntax-check all Python source files:**
```bash
python3 -m py_compile \
  pst_to_pdf/__init__.py \
  pst_to_pdf/cli.py \
  pst_to_pdf/processor.py \
  pst_to_pdf/converter.py \
  pst_to_pdf/validator.py \
  pst_to_pdf/extraction.py \
  pst_to_pdf/repair_manifest.py \
  pst_to_pdf/zip_pdfs.py \
  scripts/convert_eml_to_pdf.py \
  scripts/process_user_psts.py \
  scripts/validate_outputs.py \
  scripts/zip_pdfs.py
```

**Shell syntax check:**
```bash
bash -n scripts/check_environment.sh scripts/extract_pst.sh scripts/run_test_pipeline.sh
```

## Architecture

### Pipeline flow

```
pst-to-pdf (cli.py wizard)
  → copies PST files to case-dir/input/
  → processor.run_case()
      → extraction.extract_pst()       # runs readpst -e -D → output/<slug>/eml/
      → extraction.wait_for_stable_eml_tree()   # polls until readpst finishes
      → subprocess: python -m pst_to_pdf.converter   # parallel EML→PDF
      → validator.validate_output()    # checks EML/PDF/manifest consistency
```

### Module responsibilities

- **`pst_to_pdf/cli.py`** — 4-step interactive wizard (case dir → PST source → settings → confirm), chunked PST file copy with progress, calls `processor.run_case()`. Entry point registered as the `pst-to-pdf` console script.

- **`pst_to_pdf/processor.py`** — Pipeline orchestrator. Generates one `PstJob` per PST (with slug, output paths, log paths). Invokes extraction, EML stability wait, and conversion. Can also be called as a library via `run_case()`.

- **`pst_to_pdf/extraction.py`** — Wraps `readpst -e -D`. Polls the EML directory with `eml_tree_snapshot()` and `wait_for_stable_eml_tree()` to detect when readpst finishes writing. Skips extraction if EML files already exist (unless `--force-extract`).

- **`pst_to_pdf/converter.py`** — Parallel EML→PDF conversion using `multiprocessing.fork`. Two PDF engines: `fast` (ReportLab, default) and `weasyprint`. Writes a manifest CSV (`MANIFEST_FIELDS`) tracking every EML with status `ok`, `error`, or `timeout`. Includes `HTMLTextExtractor` that strips `style`, `script`, `head`, `title`, `noscript` tags and HTML comments before writing text to PDF.

- **`pst_to_pdf/validator.py`** — Computes `ValidationSummary` by cross-referencing EML files on disk, PDF files on disk, and manifest rows. `has_consistency_errors()` checks for duplicates, missing PDFs, and path mismatches.

- **`pst_to_pdf/repair_manifest.py`** — Safe manifest deduplication: removes duplicate `eml_path` rows (keeping the best-status row), creates a timestamped backup before writing, never deletes EML/PDF files. Default is dry-run; pass `--apply` to write.

- **`pst_to_pdf/zip_pdfs.py`** — Discovers every `output/<slug>/pdf/` folder in a case and zips each into `zipped/<slug>-pdfs.zip` (flat, PDFs only). Exposed as the `pst-to-pdf zip-pdfs --case-dir PATH [--dry-run]` subcommand (dispatched in `cli.py:main()` before the wizard's `parse_args()` runs) and as `python -m pst_to_pdf.zip_pdfs` / `scripts/zip_pdfs.py`. Always overwrites existing ZIPs; folders with zero PDFs are skipped, not treated as errors.

- **`pst_to_pdf/output.py`** — Shared CLI formatting: ANSI color helpers (`green`, `yellow`, `red`, `bold`), `print_section`/`print_kv` layout, and `write_dynamic_line`/`finish_dynamic_line` for in-place TTY progress (falls back to plain lines on non-TTY).

### Key design decisions

**Converter runs as a subprocess, not an import.** `processor.py` spawns `python -m pst_to_pdf.converter` as a child process rather than calling it directly. This gives `multiprocessing.fork` a clean process image and lets the wizard restore SIGINT handling after the subprocess exits.

**Privacy boundary.** Email bodies are parsed only inside `converter.py` worker processes to produce local PDFs. Bodies are never written to stdout, stderr, or log files anywhere in the codebase.

**Resume and idempotency.** The converter supports `--resume`: it reads the existing manifest, keeps `ok` rows, and skips EML paths that already have a matching PDF. Extraction is also skipped if EML files already exist.

**Case layout convention:**
```
case-dir/
  input/          ← PST files copied here
  output/<slug>/
    eml/          ← readpst output
    pdf/          ← generated PDFs
    manifest/     ← <slug>.csv
  logs/           ← extract and convert logs
  zipped/         ← <slug>-pdfs.zip, created by `pst-to-pdf zip-pdfs`
```

Slugs are derived from PST filenames: email addresses are collapsed to `local-NNN`, special characters replaced with `-`. Collisions get a SHA-256 suffix.

### System dependencies

- `readpst` (from `pst-utils`) is required for extraction. The converter checks availability at startup via `ensure_readpst_available()`.
- Python deps are `weasyprint>=66,<67` and `reportlab>=4.2,<5`. The venv is at `.venv/`.

# pst-to-pdf

Local command-line tooling for converting Outlook PST email exports into PDFs.

## What It Does

`pst-to-pdf` guides you through a local case setup, copies PST files into the
case `input/` folder, extracts PST messages to EML with `readpst`, converts EML
files to PDFs, and writes manifests and logs.

The tool does not use cloud services, online converters, or external APIs.
Attachment filenames are listed in the generated PDFs; attachment contents are
not embedded by default.

## Important Privacy Note

PSTs, EMLs, PDFs, manifests, and logs stay on the local machine. The interactive
wizard does not inspect or print email contents. Email bodies are parsed only by
the local conversion step when PDFs are generated.

Existing PSTs, EMLs, PDFs, manifests, logs, and output directories are not
deleted by the supported workflows.

## System Requirements

- Linux
- Python 3.10 or newer
- `pipx` for installing the CLI
- `readpst` from `pst-utils` for PST extraction

On Ubuntu/Debian, install the required system tools:

```bash
sudo apt update
sudo apt install pipx pst-utils
pipx ensurepath
```

If you use `zsh`, refresh your shell after `pipx ensurepath`:

```bash
exec zsh
```

Opening a new terminal works too.

Optional/developer tools used by legacy helpers or alternate PDF engines:

```bash
sudo apt install python3 python3-venv python3-pip pff-tools libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`readpst` is the primary extractor. `pffinfo` and `pffexport` from `pff-tools`
are fallback inspection/export tools only.

## Installation

Recommended installation after PyPI publication:

```bash
pipx install pst-to-pdf
```

`pipx` installs the Python application in an isolated environment and exposes
the `pst-to-pdf` command globally without activating a project virtual
environment.

Local development install from this repository:

```bash
cd /path/to/pst-to-pdf
pipx install --editable . --force
```

Test the installed command from anywhere:

```bash
cd /tmp
pst-to-pdf --help
```

Using `python3 -m pip install --user pst-to-pdf` is an advanced fallback, not
the recommended path. On modern Ubuntu/Debian systems, direct global/user pip
installs may be blocked by externally managed environment rules. Use `pipx` for
CLI tools.

## Usage

Run the interactive wizard:

```bash
pst-to-pdf
```

The wizard asks for:

- an existing case directory, or a new directory name such as `example-user`;
- a directory containing `*.pst`, or comma-separated `.pst` file paths;
- PDF mode, default `fast`;
- workers, default `8`;
- timeout seconds, default `60`.

Before processing starts, it shows a summary with the case directory, PST count,
`input/` destination, mode, workers, timeout, and a reminder that output stays
local. Extraction and conversion start only after final confirmation.

If a PST with the same name already exists in `input/`, the wizard skips it when
it appears to be the same file. If a different PST has the same name, it copies
to a unique numbered filename instead of overwriting existing data.

Preview the planned extraction/conversion commands without running them:

```bash
pst-to-pdf --dry-run
```

Run validation-only mode for a prepared case:

```bash
pst-to-pdf --validate-only
```

## Advanced Usage

The installable wizard is the primary workflow. Python wrappers are kept for
automation and compatibility when explicit paths are needed.

Expected case layout:

```text
/mnt/hd/pst-pdf/example-user/
├── input/
│   ├── example.user@example.local.001.pst
│   └── example.user@example.local.002.pst
├── output/
└── logs/
```

Process all PSTs in a prepared case directory:

```bash
python3 scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf/example-user"
```

Validate a prepared case without extraction or conversion:

```bash
python3 scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --validate-only
```

Preview processor commands without extraction or conversion:

```bash
python3 scripts/process_user_psts.py \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --dry-run
```

Convert one already-extracted EML tree:

```bash
python3 scripts/convert_eml_to_pdf.py \
  --source-pst input/sample.pst \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv \
  --log-file logs/convert_sample.log \
  --resume
```

Validate one output tree:

```bash
python3 scripts/validate_outputs.py \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv
```

The shell scripts in `scripts/` are legacy/developer helpers:

- `scripts/check_environment.sh` checks local command availability.
- `scripts/extract_pst.sh` extracts a single PST with `readpst`.
- `scripts/run_test_pipeline.sh` is an older developer helper and is not the
  recommended workflow for normal use.

They are kept for now because they preserve existing manual workflows, but the
preferred entry point is `pst-to-pdf`.

## Development

Safe syntax checks:

```bash
python3 -m py_compile \
  pst_to_pdf/__init__.py \
  pst_to_pdf/cli.py \
  pst_to_pdf/processor.py \
  pst_to_pdf/converter.py \
  pst_to_pdf/validator.py \
  pst_to_pdf/extraction.py \
  scripts/convert_eml_to_pdf.py \
  scripts/process_user_psts.py \
  scripts/validate_outputs.py
```

Shell syntax checks:

```bash
bash -n scripts/check_environment.sh scripts/extract_pst.sh scripts/run_test_pipeline.sh
```

Help checks:

```bash
pst-to-pdf --help
python3 -m pst_to_pdf.cli --help
```

## Publishing Checklist

Before publishing to PyPI:

- replace author and URL placeholders in `pyproject.toml`;
- confirm the intended license and add a license file;
- add automated tests for CLI prompts, PST copy collision handling, and dry-run
  behavior;
- build source and wheel distributions;
- run package validation such as `twine check`;
- publish to TestPyPI first.

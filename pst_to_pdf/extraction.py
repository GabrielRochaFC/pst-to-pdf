"""Local PST extraction helpers."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def count_files(root: Path, suffix: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() == suffix)


def has_eml_files(root: Path) -> bool:
    return count_files(root, ".eml") > 0


def ensure_readpst_available() -> None:
    if not shutil.which("readpst"):
        raise SystemExit("Missing readpst. Install it with: sudo apt install -y pst-utils")


def extract_pst(source_pst: Path, eml_dir: Path, extract_log: Path, label: str, force_extract: bool, dry_run: bool) -> tuple[bool, float]:
    if has_eml_files(eml_dir) and not force_extract:
        print(f"[{label}] extraction skipped: existing EML files found")
        return False, 0.0

    command = ["readpst", "-e", "-D", "-o", str(eml_dir), str(source_pst)]
    print(f"[{label}] extracting PST to {eml_dir}")
    if dry_run:
        print(f"[{label}] dry-run extract command: {' '.join(command)}")
        return False, 0.0

    eml_dir.mkdir(parents=True, exist_ok=True)
    extract_log.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    with extract_log.open("w", encoding="utf-8") as logfile:
        logfile.write(f"Source PST: {source_pst}\nOutput EML dir: {eml_dir}\n")
        result = subprocess.run(command, stdout=logfile, stderr=subprocess.STDOUT, check=False)
    elapsed = time.monotonic() - started_at
    if result.returncode != 0:
        raise RuntimeError(f"readpst failed for {source_pst}; see {extract_log}")
    print(f"[{label}] extraction finished elapsed={format_elapsed(elapsed)} log={extract_log}")
    return True, elapsed

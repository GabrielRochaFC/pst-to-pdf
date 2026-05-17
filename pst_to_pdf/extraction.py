"""Local PST extraction helpers."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from pst_to_pdf.output import (
    finish_dynamic_line,
    format_bytes,
    format_elapsed,
    format_number,
    print_kv,
    print_section,
    write_dynamic_line,
)


def count_files(root: Path, suffix: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() == suffix)


def has_eml_files(root: Path) -> bool:
    return count_files(root, ".eml") > 0


@dataclass(frozen=True)
class EmlTreeSnapshot:
    count: int
    total_size: int
    newest_mtime: float


def eml_tree_snapshot(root: Path) -> EmlTreeSnapshot:
    count = 0
    total_size = 0
    newest_mtime = 0.0
    if not root.exists():
        return EmlTreeSnapshot(count=0, total_size=0, newest_mtime=0.0)
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".eml":
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        count += 1
        total_size += stat.st_size
        newest_mtime = max(newest_mtime, stat.st_mtime)
    return EmlTreeSnapshot(count=count, total_size=total_size, newest_mtime=newest_mtime)


def wait_for_stable_eml_tree(
    root: Path,
    label: str,
    stable_seconds: int = 10,
    check_interval: int = 2,
    max_wait_seconds: int = 600,
    dry_run: bool = False,
) -> EmlTreeSnapshot:
    if stable_seconds <= 0:
        snapshot = eml_tree_snapshot(root)
        print(f"[{label}] EML stability check disabled count={snapshot.count} size={snapshot.total_size}")
        return snapshot
    if check_interval <= 0:
        raise SystemExit("--eml-stability-check-interval must be >= 1")
    if max_wait_seconds < stable_seconds:
        raise SystemExit("--eml-stability-max-wait must be >= --eml-stability-seconds")

    initial = eml_tree_snapshot(root)
    print_kv("Path", root)
    print_kv("Stable period", f"{format_number(stable_seconds)} seconds")
    print_kv("Check interval", f"{format_number(check_interval)} seconds")
    print_kv("Maximum wait", f"{format_number(max_wait_seconds)} seconds")
    print_kv("Initial EML count", format_number(initial.count))
    print_kv("Initial total size", f"{format_number(initial.total_size)} bytes")
    if dry_run:
        return initial

    started_at = time.monotonic()
    previous = initial
    stable_since = started_at
    while True:
        time.sleep(check_interval)
        current = eml_tree_snapshot(root)
        changed = current != previous
        now = time.monotonic()
        if changed:
            print(f"[{label}] EML tree changed: count={format_number(current.count)} size={format_number(current.total_size)} bytes")
            previous = current
            stable_since = now
        elif now - stable_since >= stable_seconds:
            print_kv("Final EML count", format_number(current.count))
            print_kv("Final total size", f"{format_number(current.total_size)} bytes")
            print_kv("Newest EML mtime", f"{current.newest_mtime:.6f}")
            print_kv("Waited", format_elapsed(now - started_at))
            return current

        if now - started_at >= max_wait_seconds:
            raise TimeoutError(
                f"EML tree did not become stable within {max_wait_seconds} seconds: "
                f"{root} count={current.count} size={current.total_size}"
            )


def ensure_readpst_available() -> None:
    if not shutil.which("readpst"):
        raise SystemExit("Missing readpst. Install it with: sudo apt install -y pst-utils")


@dataclass(frozen=True)
class ExtractionResult:
    ran: bool
    elapsed: float
    eml_count: int
    eml_size: int


_POLL_INTERVAL = 2.0  # seconds between progress updates during extraction


def extract_pst(
    source_pst: Path,
    eml_dir: Path,
    extract_log: Path,
    label: str,
    force_extract: bool,
    dry_run: bool,
) -> ExtractionResult:
    if has_eml_files(eml_dir) and not force_extract:
        snapshot = eml_tree_snapshot(eml_dir)
        print(
            f"[{label}] Extraction skipped — EML files already exist"
            f" ({format_number(snapshot.count)} files, {format_bytes(snapshot.total_size)})"
        )
        return ExtractionResult(ran=False, elapsed=0.0, eml_count=snapshot.count, eml_size=snapshot.total_size)

    command = ["readpst", "-e", "-D", "-o", str(eml_dir), str(source_pst)]
    print_kv("Source PST", source_pst)
    print_kv("EML dir", eml_dir)
    if dry_run:
        print_kv("Status", "planned")
        print_kv("Command", " ".join(command))
        return ExtractionResult(ran=False, elapsed=0.0, eml_count=0, eml_size=0)

    eml_dir.mkdir(parents=True, exist_ok=True)
    extract_log.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()

    with extract_log.open("w", encoding="utf-8") as logfile:
        logfile.write(f"Source PST: {source_pst}\nOutput EML dir: {eml_dir}\n")
        logfile.flush()
        proc = subprocess.Popen(command, stdout=logfile, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            elapsed = time.monotonic() - started_at
            snapshot = eml_tree_snapshot(eml_dir)
            write_dynamic_line(
                f"[{label}] Extracting PST"
                f" | elapsed {format_elapsed(elapsed)}"
                f" | EML files {format_number(snapshot.count)}"
                f" | size {format_bytes(snapshot.total_size)}"
            )
            time.sleep(_POLL_INTERVAL)

    finish_dynamic_line()
    elapsed = time.monotonic() - started_at

    if proc.returncode != 0:
        raise RuntimeError(f"readpst failed for {source_pst}; see {extract_log}")

    final = eml_tree_snapshot(eml_dir)
    print_section(f"Extraction completed — {label}")
    print_kv("EML files", format_number(final.count))
    print_kv("Size", format_bytes(final.total_size))
    print_kv("Elapsed", format_elapsed(elapsed))
    print_kv("Log", extract_log)

    return ExtractionResult(ran=True, elapsed=elapsed, eml_count=final.count, eml_size=final.total_size)

"""Interactive setup wizard for the local PST-to-PDF pipeline."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from pst_to_pdf import output
from pst_to_pdf.output import (
    bold,
    format_bool,
    format_bytes,
    format_elapsed,
    format_number,
    green,
    print_kv,
    print_path_block,
    print_section,
    yellow,
)
from pst_to_pdf.processor import run_case


DEFAULT_MODE = "fast"
DEFAULT_WORKERS = 8
DEFAULT_TIMEOUT_SECONDS = 60
_COPY_CHUNK = 4 * 1024 * 1024  # 4 MB per read


class GoBack(Exception):
    """Raised by prompt helpers when the user types b/back."""


@dataclass(frozen=True)
class CopiedPst:
    source: Path
    destination: Path
    copied: bool


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def _quit_wizard() -> None:
    print()
    print("Wizard cancelled. No PST files were copied.")
    sys.exit(0)


def _nav_hint(allow_back: bool) -> str:
    parts = ["b=back"] if allow_back else []
    parts.append("q=quit")
    return f"  [{', '.join(parts)}]"


# ---------------------------------------------------------------------------
# Prompt primitives
# ---------------------------------------------------------------------------

def prompt_text(
    message: str,
    default: str | None = None,
    allow_back: bool = False,
) -> str:
    suffix = f" [{default}]" if default is not None else ""
    hint = _nav_hint(allow_back)
    while True:
        value = input(f"{message}{suffix}{hint}: ").strip()
        lowered = value.lower()
        if lowered in {"q", "quit"}:
            _quit_wizard()
        if allow_back and lowered in {"b", "back"}:
            raise GoBack
        if value:
            return value
        if default is not None:
            return default
        return ""


def prompt_choice(
    message: str,
    choices: dict[str, str],
    default: str,
    compact: bool = True,
    allow_back: bool = False,
) -> str:
    labels = "/".join(key + ("*" if key == default else "") for key in choices)
    hint = _nav_hint(allow_back)
    while True:
        prompt = f"{message} ({labels}){hint}: " if compact else f"{message} [{default}]{hint}: "
        value = input(prompt).strip().lower() or default
        if value in {"q", "quit"}:
            _quit_wizard()
        if allow_back and value in {"b", "back"}:
            raise GoBack
        if value in choices:
            return value
        print(f"  Choose one of: {', '.join(choices)}")


def prompt_int(
    message: str,
    default: int,
    minimum: int = 0,
    allow_back: bool = False,
) -> int:
    while True:
        raw = prompt_text(message, str(default), allow_back=allow_back)
        try:
            value = int(raw)
        except ValueError:
            print("  Enter a whole number.")
            continue
        if value < minimum:
            print(f"  Enter a value >= {minimum}.")
            continue
        return value


def prompt_confirm(message: str, default: bool = True) -> bool:
    """Final confirmation prompt. Supports q=quit but not b=back."""
    label = bold("Y/n") if default else bold("y/N")
    while True:
        value = input(f"{message} [{label}, q=quit]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        if value in {"q", "quit"}:
            _quit_wizard()
        print("  Answer Y or n.")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_user_path(value: str, base: Path | None = None) -> Path:
    path = Path(os.path.expanduser(value.strip()))
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return path.resolve()


def can_write_dir(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return os.access(path, os.W_OK)


def same_file_content(left: Path, right: Path) -> bool:
    try:
        if left.samefile(right):
            return True
    except FileNotFoundError:
        return False
    except OSError:
        pass
    try:
        left_stat = left.stat()
        right_stat = right.stat()
    except OSError:
        return False
    return left_stat.st_size == right_stat.st_size


def unique_destination(input_dir: Path, source: Path) -> Path:
    candidate = input_dir / source.name
    if not candidate.exists() or same_file_content(source, candidate):
        return candidate
    stem = source.stem
    suffix = source.suffix
    counter = 2
    while True:
        candidate = input_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists() or same_file_content(source, candidate):
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Wizard steps
# ---------------------------------------------------------------------------

def choose_case_dir(allow_back: bool = False) -> Path:
    print_section("Step 1/4 - Case directory")
    print("Choose where this case's processing folder will be stored.")
    print()
    print("  [e] Use an existing case directory")
    print("  [n] Create a new case directory here")
    print()
    mode = prompt_choice("Selection", {"e": "existing", "n": "new"}, "n", compact=False, allow_back=allow_back)
    if mode == "e":
        while True:
            case_dir = resolve_user_path(prompt_text("Existing case directory path", allow_back=True))
            if case_dir.is_dir():
                return case_dir
            print(f"  Directory not found: {case_dir}")
    while True:
        name = prompt_text("New case directory name, for example example-user", allow_back=True)
        if not name or Path(name).is_absolute() or any(part == ".." for part in Path(name).parts):
            print("  Enter a relative directory name, for example: example-user")
            continue
        case_dir = (Path.cwd() / name).resolve()
        if case_dir.exists() and not case_dir.is_dir():
            print(f"  Path exists and is not a directory: {case_dir}")
            continue
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir


def discover_psts(raw: str) -> list[Path]:
    value = raw.strip()
    if not value:
        return []
    maybe_dir = resolve_user_path(value)
    if maybe_dir.is_dir():
        return sorted(path.resolve() for path in maybe_dir.glob("*.pst") if path.is_file())
    paths: list[Path] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        paths.append(resolve_user_path(item))
    return paths


def prompt_psts() -> tuple[list[Path], int]:
    """Returns (pst_paths, total_source_bytes). Does not copy files."""
    print_section("Step 2/4 - PST source")
    print("Enter either:")
    print("  - a folder containing .pst files")
    print("  - or comma-separated .pst file paths")
    print()
    while True:
        raw = prompt_text("PST source", allow_back=True)
        psts = discover_psts(raw)
        missing = [path for path in psts if not path.is_file()]
        wrong_suffix = [path for path in psts if path.suffix.lower() != ".pst"]
        if not psts:
            print("  No .pst files found. Enter a directory with .pst files or comma-separated file paths.")
            continue
        if missing:
            print(f"  File not found: {missing[0]}")
            continue
        if wrong_suffix:
            print(f"  Not a .pst file: {wrong_suffix[0]}")
            continue
        total_size = sum(path.stat().st_size for path in psts)
        print(f"  Found {format_number(len(psts))} PST file(s) — {format_bytes(total_size)}")
        return psts, total_size


def prompt_settings(
    default_mode: str = DEFAULT_MODE,
    default_workers: int = DEFAULT_WORKERS,
    default_timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str, int, int]:
    print_section("Step 3/4 - Conversion settings")
    mode = prompt_choice(
        "PDF mode",
        {"fast": "fast", "weasyprint": "weasyprint"},
        default_mode,
        compact=False,
        allow_back=True,
    )
    workers = prompt_int("Workers", default_workers, minimum=1, allow_back=True)
    timeout_seconds = prompt_int("Timeout per email in seconds", default_timeout, minimum=0, allow_back=True)
    return mode, workers, timeout_seconds


# ---------------------------------------------------------------------------
# Summary and copy
# ---------------------------------------------------------------------------

def print_pre_copy_summary(
    case_dir: Path,
    psts: list[Path],
    pst_total_size: int,
    mode: str,
    workers: int,
    timeout_seconds: int,
    dry_run: bool,
    validate_only: bool,
) -> None:
    print_kv("Case directory", case_dir)
    print_kv("PST files found", format_number(len(psts)))
    print_kv("Total source size", format_bytes(pst_total_size))
    print_kv("Input destination", case_dir / "input")
    print_kv("Output destination", case_dir / "output")
    print_kv("Logs destination", case_dir / "logs")
    print_kv("PDF mode", mode)
    print_kv("Workers", format_number(workers))
    print_kv("Timeout", f"{format_number(timeout_seconds)} seconds")
    if dry_run:
        print_kv("Dry run", yellow(format_bool(dry_run)))
    else:
        print_kv("Dry run", format_bool(dry_run))
    print_kv("Validation only", format_bool(validate_only))
    print()
    print("  No email body content will be printed.")
    print("  All output stays local.")


def _copy_file_with_progress(
    source: Path,
    destination: Path,
    file_index: int,
    total_files: int,
    bytes_before: int,
    total_bytes: int,
    started_at: float,
) -> int:
    """Chunked copy with inline progress. Returns bytes written."""
    file_size = source.stat().st_size
    written = 0
    is_tty = sys.stdout.isatty()
    last_print = 0.0

    with source.open("rb") as src, destination.open("wb") as dst:
        while True:
            chunk = src.read(_COPY_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            written += len(chunk)

            now = time.monotonic()
            if is_tty or now - last_print >= 3.0:
                elapsed = now - started_at
                total_done = bytes_before + written
                file_pct = written / file_size * 100 if file_size else 100.0
                total_pct = total_done / total_bytes * 100 if total_bytes else 100.0
                rate = total_done / elapsed if elapsed > 0 else 0.0
                remaining = total_bytes - total_done
                eta = (
                    format_elapsed(remaining / rate)
                    if rate > 0 and remaining > 0
                    else "--:--:--"
                )
                name = source.name[:35]
                line = (
                    f"  [{file_index}/{total_files}] {name:<35}"
                    f"  File: {file_pct:5.1f}%"
                    f"  Total: {format_bytes(total_done)}/{format_bytes(total_bytes)}"
                    f" ({total_pct:5.1f}%)"
                    f"  Elapsed: {format_elapsed(elapsed)}"
                    f"  ETA: {eta}"
                )
                if is_tty:
                    print(f"\r{line}", end="", flush=True)
                else:
                    print(line, flush=True)
                last_print = now

    shutil.copystat(source, destination)
    if is_tty:
        print()
    return written


def copy_psts(psts: list[Path], input_dir: Path) -> list[CopiedPst]:
    if not can_write_dir(input_dir):
        raise SystemExit(f"Cannot write to input directory: {input_dir}")

    # Pre-compute which files will actually be copied vs skipped
    plan: list[tuple[Path, Path, bool]] = []
    for source in psts:
        destination = unique_destination(input_dir, source)
        will_copy = not (destination.exists() and same_file_content(source, destination))
        plan.append((source, destination, will_copy))

    total_bytes_to_copy = sum(src.stat().st_size for src, _dst, will_copy in plan if will_copy)
    copy_total = sum(1 for _, _, will_copy in plan if will_copy)
    bytes_done = 0
    copy_index = 0
    started_at = time.monotonic()
    copied: list[CopiedPst] = []

    for i, (source, destination, will_copy) in enumerate(plan, start=1):
        if not will_copy:
            print(f"  [{i}/{len(plan)}] Skip (already in input): {source.name}")
            copied.append(CopiedPst(source=source, destination=destination, copied=False))
            continue
        copy_index += 1
        print(f"  [{copy_index}/{copy_total}] Copying: {source.name}")
        written = _copy_file_with_progress(
            source,
            destination,
            copy_index,
            copy_total,
            bytes_done,
            total_bytes_to_copy,
            started_at,
        )
        bytes_done += written
        copied.append(CopiedPst(source=source, destination=destination, copied=True))

    elapsed = time.monotonic() - started_at
    n_copied = sum(1 for c in copied if c.copied)
    n_skipped = len(copied) - n_copied
    print(
        f"  {green('Done')}: {format_number(n_copied)} copied,"
        f" {format_number(n_skipped)} skipped,"
        f" elapsed {format_elapsed(elapsed)}"
    )
    return copied


# ---------------------------------------------------------------------------
# CLI flags and intro
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive local PST to PDF conversion wizard.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned summary without copying, extracting, or converting.")
    parser.add_argument("--validate-only", action="store_true", help="Run validation after preparing the case directory; do not extract or convert.")
    parser.add_argument("--force-extract", action="store_true", help="Run readpst even when EML files already exist.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output.")
    return parser.parse_args()


def print_intro(dry_run: bool) -> None:
    print()
    print(bold("PST to PDF — Local Conversion Wizard"))
    print("=" * 38)
    print()
    print("This wizard will:")
    print("  1. Create or select a case directory.")
    print("  2. Discover PST files from the source you specify.")
    print("  3. Review settings and confirm before any files are copied.")
    print("  4. Copy PST files into the case input folder.")
    print("  5. Extract PST messages into local EML files.")
    print("  6. Convert EML messages into local PDF files.")
    print("  7. Generate manifests and logs.")
    print()
    print("Privacy:")
    print("  - Files stay local. No cloud services are used.")
    print("  - Email bodies are not printed to the terminal.")
    print("  - Original PST files are not modified.")
    if dry_run:
        print()
        print(yellow("DRY RUN MODE"))
        print("  PST files will not be copied.")
        print("  No extraction or conversion will run.")
        print("  Only the planned summary will be shown.")


def print_dry_run_plan(
    case_dir: Path,
    psts: list[Path],
    mode: str,
    workers: int,
    timeout_seconds: int,
) -> None:
    print_section("Dry run plan")
    print_kv("Case directory", case_dir)
    print_kv("Input destination", case_dir / "input")
    print_kv("Output destination", case_dir / "output")
    print_kv("Logs destination", case_dir / "logs")
    print_kv("PDF mode", mode)
    print_kv("Workers", format_number(workers))
    print_kv("Timeout", f"{format_number(timeout_seconds)} seconds")
    print()
    print("PST files that would be copied:")
    for pst in psts:
        dest = case_dir / "input" / pst.name
        print(f"  {pst}")
        print(f"    → {dest}")


# ---------------------------------------------------------------------------
# Main wizard loop
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    if args.no_color:
        os.environ["NO_COLOR"] = "1"

    previous_sigint_handler = signal.getsignal(signal.SIGINT)

    def handle_sigint(signum: int, frame: object) -> None:
        print()
        print("Interrupted.")
        print("No PST files were copied.")
        raise SystemExit(130)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        print_intro(args.dry_run)

        # Mutable state carried between steps
        case_dir: Path | None = None
        psts: list[Path] | None = None
        pst_total_size: int = 0
        mode = DEFAULT_MODE
        workers = DEFAULT_WORKERS
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        step = 1
        while step <= 4:
            try:
                if step == 1:
                    case_dir = choose_case_dir(allow_back=False)
                    step = 2

                elif step == 2:
                    psts, pst_total_size = prompt_psts()
                    step = 3

                elif step == 3:
                    mode, workers, timeout_seconds = prompt_settings(
                        default_mode=mode,
                        default_workers=workers,
                        default_timeout=timeout_seconds,
                    )
                    step = 4

                elif step == 4:
                    assert case_dir is not None
                    assert psts is not None
                    print_section("Step 4/4 - Review and confirm")
                    print_pre_copy_summary(
                        case_dir, psts, pst_total_size,
                        mode, workers, timeout_seconds,
                        args.dry_run, args.validate_only,
                    )
                    print()
                    confirmed = prompt_confirm("Start processing?", default=True)
                    if not confirmed:
                        print()
                        print("Processing not started. No PST files were copied.")
                        return 0
                    step = 5  # exit wizard loop

            except GoBack:
                step = max(1, step - 1)

        # --- Confirmation given — hand back SIGINT to the processing pipeline ---
        signal.signal(signal.SIGINT, previous_sigint_handler)

        assert case_dir is not None
        assert psts is not None

        if args.dry_run:
            print_dry_run_plan(case_dir, psts, mode, workers, timeout_seconds)
            print()
            print("Dry run completed.")
            print("No PST files were copied.")
            print("No extraction or conversion was run.")
            print()
            print("To process for real, run:")
            print("  pst-to-pdf")
            return 0

        print_section("Copying PST files")
        copy_psts(psts, case_dir / "input")

        print_section("Processing")
        return int(
            run_case(
                case_dir=case_dir,
                mode=mode,
                workers=workers,
                timeout_seconds=timeout_seconds,
                force_extract=args.force_extract,
                validate_only=args.validate_only,
                dry_run=False,
            )
        )

    except KeyboardInterrupt:
        print()
        print("Interrupted.")
        print("No PST files were copied.")
        return 130
    finally:
        signal.signal(signal.SIGINT, previous_sigint_handler)


if __name__ == "__main__":
    raise SystemExit(main())

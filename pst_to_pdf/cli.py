"""Interactive setup wizard for the local PST-to-PDF pipeline."""

from __future__ import annotations

import argparse
import os
import signal
import shutil
from dataclasses import dataclass
from pathlib import Path

from pst_to_pdf.output import format_bool, format_number, print_kv, print_path_block, print_section
from pst_to_pdf.processor import run_case


DEFAULT_MODE = "fast"
DEFAULT_WORKERS = 8
DEFAULT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class CopiedPst:
    source: Path
    destination: Path
    copied: bool


def prompt_text(message: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{message}{suffix}: ").strip()
    if value:
        return value
    if default is not None:
        return default
    return ""


def prompt_choice(message: str, choices: dict[str, str], default: str, compact: bool = True) -> str:
    labels = "/".join(f"{key}" + ("*" if key == default else "") for key in choices)
    while True:
        prompt = f"{message} ({labels}): " if compact else f"{message} [{default}]: "
        value = input(prompt).strip().lower() or default
        if value in choices:
            return value
        print(f"Choose one of: {', '.join(choices)}")


def prompt_int(message: str, default: int, minimum: int = 0) -> int:
    while True:
        raw = prompt_text(message, str(default))
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue
        if value < minimum:
            print(f"Enter a value >= {minimum}.")
            continue
        return value


def prompt_bool(message: str, default: bool = False) -> bool:
    default_text = "y" if default else "n"
    while True:
        value = input(f"{message} [y/n, default {default_text}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Answer y or n.")


def resolve_user_path(value: str, base: Path | None = None) -> Path:
    path = Path(os.path.expanduser(value.strip()))
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return path.resolve()


def choose_case_dir() -> Path:
    print_section("Step 1/5 - Case directory")
    print("Choose where this user's processing folder will be stored.")
    print()
    print("[e] Use an existing case directory")
    print("[n] Create a new case directory here")
    print()
    mode = prompt_choice("Selection", {"e": "existing", "n": "new"}, "n", compact=False)
    if mode == "e":
        while True:
            case_dir = resolve_user_path(prompt_text("Existing case directory path"))
            if case_dir.is_dir():
                return case_dir
            print(f"Directory not found: {case_dir}")

    while True:
        name = prompt_text("New case directory name, for example example-user")
        if not name or Path(name).is_absolute() or any(part == ".." for part in Path(name).parts):
            print("Enter a relative directory name, for example: example-user")
            continue
        case_dir = (Path.cwd() / name).resolve()
        if case_dir.exists() and not case_dir.is_dir():
            print(f"Path exists and is not a directory: {case_dir}")
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


def prompt_psts() -> list[Path]:
    print_section("Step 2/5 - PST source")
    print("Enter either:")
    print("- a folder containing .pst files")
    print("- or comma-separated .pst file paths")
    print()
    while True:
        raw = prompt_text("PST source")
        psts = discover_psts(raw)
        missing = [path for path in psts if not path.is_file()]
        wrong_suffix = [path for path in psts if path.suffix.lower() != ".pst"]
        if not psts:
            print("No .pst files found. Provide a directory containing .pst files or file paths separated by commas.")
            continue
        if missing:
            print(f"File not found: {missing[0]}")
            continue
        if wrong_suffix:
            print(f"Not a .pst file: {wrong_suffix[0]}")
            continue
        return psts


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


def copy_psts(psts: list[Path], input_dir: Path) -> list[CopiedPst]:
    if not can_write_dir(input_dir):
        raise SystemExit(f"Cannot write to input directory: {input_dir}")

    copied: list[CopiedPst] = []
    for source in psts:
        destination = unique_destination(input_dir, source)
        if destination.exists() and same_file_content(source, destination):
            copied.append(CopiedPst(source=source, destination=destination, copied=False))
            continue
        shutil.copy2(source, destination)
        copied.append(CopiedPst(source=source, destination=destination, copied=True))
    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive local PST to PDF conversion wizard.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare/copy PSTs and show planned commands without extraction or conversion.")
    parser.add_argument("--validate-only", action="store_true", help="Run validation after preparing the case directory; do not extract or convert.")
    parser.add_argument("--force-extract", action="store_true", help="Run readpst even when EML files already exist.")
    return parser.parse_args()


def print_summary(case_dir: Path, copied: list[CopiedPst], mode: str, workers: int, timeout_seconds: int, dry_run: bool, validate_only: bool) -> None:
    copied_count = sum(1 for item in copied if item.copied)
    skipped_count = len(copied) - copied_count
    print_section("Processing Summary")
    print_kv("Case directory", case_dir)
    print_kv("PST files", format_number(len(copied)))
    print_kv("Input folder", case_dir / "input")
    print_kv("Copied PSTs", format_number(copied_count))
    print_kv("Skipped PSTs", format_number(skipped_count))
    print_kv("PDF mode", mode)
    print_kv("Workers", format_number(workers))
    print_kv("Timeout", f"{format_number(timeout_seconds)} seconds")
    print_kv("Dry run", format_bool(dry_run))
    print_kv("Validation only", format_bool(validate_only))
    print_path_block("Output will be written under", case_dir / "output")
    print_path_block("Logs will be written under", case_dir / "logs")
    print()
    print("No email body content will be printed.")


def print_interrupted(copy_step_started: bool) -> None:
    print()
    print("Interrupted by user.")
    if copy_step_started:
        print("No extraction or conversion was started.")
        print("Any PST files already copied into the case input folder were left in place.")
    else:
        print("No processing was started.")


def print_intro(dry_run: bool) -> None:
    print()
    print("PST to PDF - Local Conversion Wizard")
    print("=" * 38)
    print()
    print("This tool will:")
    print("1. Create or use a case directory.")
    print("2. Copy PST files into the case input folder.")
    print("3. Extract PST messages into local EML files.")
    print("4. Convert EML messages into local PDF files.")
    print("5. Generate manifests and logs.")
    print()
    print("Privacy:")
    print("- Files stay local.")
    print("- Email bodies are not printed to the terminal.")
    print("- Original PST files are not modified.")
    if dry_run:
        print()
        print("DRY RUN MODE")
        print("No PST extraction will be run.")
        print("No EML to PDF conversion will be run.")
        print("No email contents will be read for conversion.")
        print("The tool may prepare/copy PST files into the case input folder.")


def main() -> int:
    args = parse_args()
    copy_step_started = False
    previous_sigint_handler = signal.getsignal(signal.SIGINT)

    def handle_sigint(signum: int, frame: object) -> None:
        print_interrupted(copy_step_started)
        raise SystemExit(130)

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        print_intro(args.dry_run)
        case_dir = choose_case_dir()
        psts = prompt_psts()
        copy_step_started = True
        copied = copy_psts(psts, case_dir / "input")

        print_section("Step 3/5 - Conversion settings")
        mode = prompt_choice("PDF mode", {"fast": "fast", "weasyprint": "weasyprint"}, DEFAULT_MODE, compact=False)
        workers = prompt_int("Workers", DEFAULT_WORKERS, minimum=1)
        timeout_seconds = prompt_int("Timeout per email in seconds", DEFAULT_TIMEOUT_SECONDS, minimum=0)

        print_section("Step 4/5 - Review")
        print_summary(case_dir, copied, mode, workers, timeout_seconds, args.dry_run, args.validate_only)
        if not prompt_bool("Start processing?", default=False):
            print("Processing not started. PST copies remain in input/.")
            return 0

        print_section("Step 5/5 - Processing")
        signal.signal(signal.SIGINT, previous_sigint_handler)
        result = int(
            run_case(
                case_dir=case_dir,
                mode=mode,
                workers=workers,
                timeout_seconds=timeout_seconds,
                force_extract=args.force_extract,
                validate_only=args.validate_only,
                dry_run=args.dry_run,
            )
        )
        if args.dry_run:
            print()
            print("Dry run completed.")
            print("Review the summary above. To process for real, run:")
            print()
            print("pst-to-pdf")
        return result
    except KeyboardInterrupt:
        print_interrupted(copy_step_started)
        return 130
    finally:
        signal.signal(signal.SIGINT, previous_sigint_handler)


if __name__ == "__main__":
    raise SystemExit(main())

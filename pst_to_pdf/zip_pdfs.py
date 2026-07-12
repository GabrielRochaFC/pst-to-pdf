"""Zip the PDF output of a case directory for delivery, one ZIP per PST."""

from __future__ import annotations

import argparse
import os
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pst_to_pdf.output import (
    format_elapsed,
    format_number,
    green,
    print_issues,
    print_kv,
    print_section,
    red,
    yellow,
)


@dataclass
class ZipResult:
    slug: str
    pdf_dir: Path
    zip_path: Path
    pdf_count: int
    status: str  # "ok" | "skipped" | "error"
    error: str | None = None


def discover_pdf_folders(case_dir: Path) -> list[tuple[str, Path]]:
    output_dir = case_dir / "output"
    if not output_dir.is_dir():
        return []
    return sorted(
        (pdf_dir.parent.name, pdf_dir)
        for pdf_dir in output_dir.glob("*/pdf")
        if pdf_dir.is_dir()
    )


def list_pdf_files(pdf_dir: Path) -> list[Path]:
    return sorted(
        path for path in pdf_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def zip_folder(slug: str, pdf_dir: Path, zip_path: Path) -> ZipResult:
    pdf_files = list_pdf_files(pdf_dir)
    if not pdf_files:
        return ZipResult(slug, pdf_dir, zip_path, pdf_count=0, status="skipped")

    tmp_path = zip_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdf_file in pdf_files:
                zf.write(pdf_file, arcname=pdf_file.name)
        os.replace(tmp_path, zip_path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        return ZipResult(slug, pdf_dir, zip_path, len(pdf_files), status="error", error=str(exc))

    return ZipResult(slug, pdf_dir, zip_path, len(pdf_files), status="ok")


def print_zip_intro(case_dir: Path, output_dir: Path, zipped_dir: Path, n_folders: int, dry_run: bool) -> None:
    print_section("ZIP PDF Export")
    print_kv("Case directory", case_dir)
    print_kv("Output directory", output_dir)
    print_kv("PDF folders found", format_number(n_folders))
    print_kv("Zip destination", zipped_dir)
    if dry_run:
        print_kv("Dry run", yellow("yes"))


def print_zip_result(index: int, total: int, result: ZipResult) -> None:
    print()
    print(f"[{index}/{total}] {result.slug}")
    print_kv("PDFs", format_number(result.pdf_count))
    print_kv("ZIP", result.zip_path.name)
    if result.status == "ok":
        print_kv("Status", green("OK"))
    elif result.status == "skipped":
        print_kv("Status", yellow("SKIPPED (0 PDFs)"))
    else:
        print_kv("Status", red(f"ERROR: {result.error}"))


def print_zip_summary(results: list[ZipResult], elapsed: float, zipped_dir: Path) -> None:
    n_ok = sum(1 for r in results if r.status == "ok")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    n_errors = sum(1 for r in results if r.status == "error")
    total_pdfs = sum(r.pdf_count for r in results if r.status == "ok")

    print_section("Zip Summary")
    print_kv("ZIPs created", format_number(n_ok))
    print_kv("ZIPs skipped", format_number(n_skipped))
    print_kv("PDFs zipped", format_number(total_pdfs))
    print_kv("Elapsed", format_elapsed(elapsed))
    print_kv("Destination", zipped_dir)
    print()
    if n_errors:
        print(f"Status: {yellow('NEEDS ATTENTION')}")
    else:
        print(f"Status: {green('PASS')}")
    print_issues([f"{r.slug}: {r.error}" for r in results if r.status == "error"])


def run(case_dir: Path, dry_run: bool = False) -> int:
    if not case_dir.exists():
        print(f"Case directory not found: {case_dir}")
        return 2
    if not case_dir.is_dir():
        print(f"Not a directory: {case_dir}")
        return 2

    output_dir = case_dir / "output"
    if not output_dir.is_dir():
        print(f"No output/ directory found in case: {case_dir}")
        print("Run the conversion pipeline first (pst-to-pdf).")
        return 2

    folders = discover_pdf_folders(case_dir)
    zipped_dir = case_dir / "zipped"

    print_zip_intro(case_dir, output_dir, zipped_dir, len(folders), dry_run)

    if not folders:
        print()
        print(f"No pdf/ folders found under {output_dir}.")
        return 0

    if dry_run:
        print_section("Planned ZIPs")
        for slug, pdf_dir in folders:
            pdf_count = len(list_pdf_files(pdf_dir))
            zip_path = zipped_dir / f"{slug}-pdfs.zip"
            print()
            print(f"{slug}")
            print_kv("PDFs", format_number(pdf_count))
            print_kv("Would create", zip_path)
        print()
        print("Dry run completed. No ZIP files were created.")
        return 0

    zipped_dir.mkdir(parents=True, exist_ok=True)

    print_section("Creating ZIPs")
    started_at = time.monotonic()
    results: list[ZipResult] = []
    for index, (slug, pdf_dir) in enumerate(folders, start=1):
        zip_path = zipped_dir / f"{slug}-pdfs.zip"
        result = zip_folder(slug, pdf_dir, zip_path)
        results.append(result)
        print_zip_result(index, len(folders), result)

    elapsed = time.monotonic() - started_at
    print_zip_summary(results, elapsed, zipped_dir)

    return 1 if any(r.status == "error" for r in results) else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zip PDF output folders (output/<slug>/pdf/) for delivery.",
    )
    parser.add_argument("--case-dir", required=True, type=Path, help="Case directory to scan for output/<slug>/pdf/ folders.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned ZIPs without writing any files.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.no_color:
        os.environ["NO_COLOR"] = "1"

    case_dir = Path(os.path.expanduser(str(args.case_dir))).resolve()
    return run(case_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

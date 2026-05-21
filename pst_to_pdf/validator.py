#!/usr/bin/env python3
"""Validate local PST-to-PDF output without printing email contents."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pst_to_pdf.output import format_number, green, print_issues, print_kv, print_section, yellow


@dataclass
class ValidationSummary:
    total_eml_files: int = 0
    total_pdf_files: int = 0
    total_manifest_rows: int = 0
    successful_rows: int = 0
    failed_rows: int = 0
    timeout_rows: int = 0
    filtered_rows: int = 0
    duplicate_eml_rows: int = 0
    missing_pdfs_for_successful_rows: int = 0
    eml_files_missing_manifest_rows: int = 0
    manifest_eml_paths_missing_on_disk: int = 0
    extra_pdf_files_not_referenced_by_manifest: int = 0

    def add(self, other: "ValidationSummary") -> None:
        self.total_eml_files += other.total_eml_files
        self.total_pdf_files += other.total_pdf_files
        self.total_manifest_rows += other.total_manifest_rows
        self.successful_rows += other.successful_rows
        self.failed_rows += other.failed_rows
        self.timeout_rows += other.timeout_rows
        self.filtered_rows += other.filtered_rows
        self.duplicate_eml_rows += other.duplicate_eml_rows
        self.missing_pdfs_for_successful_rows += other.missing_pdfs_for_successful_rows
        self.eml_files_missing_manifest_rows += other.eml_files_missing_manifest_rows
        self.manifest_eml_paths_missing_on_disk += other.manifest_eml_paths_missing_on_disk
        self.extra_pdf_files_not_referenced_by_manifest += other.extra_pdf_files_not_referenced_by_manifest

    def has_consistency_errors(self) -> bool:
        return any(
            [
                self.duplicate_eml_rows,
                self.missing_pdfs_for_successful_rows,
                self.eml_files_missing_manifest_rows,
                self.manifest_eml_paths_missing_on_disk,
            ]
        )


def count_files(root: Path, suffix: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() == suffix)


def paths_with_suffix(root: Path, suffix: str) -> set[str]:
    if not root.exists():
        return set()
    return {str(path) for path in root.rglob("*") if path.is_file() and path.suffix.lower() == suffix}


def read_manifest_rows(manifest: Path) -> list[dict[str, str]]:
    if not manifest.exists():
        return []
    with manifest.open("r", newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def validate_output(eml_dir: Path, pdf_dir: Path, manifest: Path) -> ValidationSummary:
    rows = read_manifest_rows(manifest)
    statuses = Counter(row.get("status", "") for row in rows)
    eml_counts = Counter(row.get("eml_path", "") for row in rows if row.get("eml_path"))
    manifest_eml_paths = set(eml_counts)
    eml_paths_on_disk = paths_with_suffix(eml_dir, ".eml")
    pdf_paths_on_disk = paths_with_suffix(pdf_dir, ".pdf")
    manifest_pdf_paths = {row.get("pdf_path", "") for row in rows if row.get("pdf_path")}
    duplicate_eml_rows = sum(count - 1 for count in eml_counts.values() if count > 1)
    missing_pdfs = sum(
        1
        for row in rows
        if row.get("status") == "ok" and (not row.get("pdf_path") or not Path(row["pdf_path"]).is_file())
    )
    return ValidationSummary(
        total_eml_files=len(eml_paths_on_disk),
        total_pdf_files=len(pdf_paths_on_disk),
        total_manifest_rows=len(rows),
        successful_rows=statuses.get("ok", 0),
        failed_rows=statuses.get("error", 0),
        timeout_rows=statuses.get("timeout", 0),
        filtered_rows=statuses.get("filtered", 0),
        duplicate_eml_rows=duplicate_eml_rows,
        missing_pdfs_for_successful_rows=missing_pdfs,
        eml_files_missing_manifest_rows=len(eml_paths_on_disk - manifest_eml_paths),
        manifest_eml_paths_missing_on_disk=len(manifest_eml_paths - eml_paths_on_disk),
        extra_pdf_files_not_referenced_by_manifest=len(pdf_paths_on_disk - manifest_pdf_paths),
    )


def print_summary(summary: ValidationSummary) -> None:
    print_validation_block("Output", summary)


def validation_issues(summary: ValidationSummary) -> list[str]:
    issues: list[str] = []
    if summary.duplicate_eml_rows:
        issues.append(f"{format_number(summary.duplicate_eml_rows)} duplicate EML rows found.")
    if summary.missing_pdfs_for_successful_rows:
        issues.append(f"{format_number(summary.missing_pdfs_for_successful_rows)} successful manifest rows are missing PDFs.")
    if summary.eml_files_missing_manifest_rows:
        issues.append(f"{format_number(summary.eml_files_missing_manifest_rows)} EML files are missing manifest rows.")
    if summary.manifest_eml_paths_missing_on_disk:
        issues.append(f"{format_number(summary.manifest_eml_paths_missing_on_disk)} manifest EML paths are missing on disk.")
    return issues


def print_validation_block(label: str, summary: ValidationSummary) -> None:
    print_section(f"Validation - {label}")
    print_kv("EML files", format_number(summary.total_eml_files))
    print_kv("PDF files", format_number(summary.total_pdf_files))
    print_kv("Manifest rows", format_number(summary.total_manifest_rows))
    print_kv("Successful rows", format_number(summary.successful_rows))
    print_kv("Failed rows", format_number(summary.failed_rows))
    print_kv("Timeout rows", format_number(summary.timeout_rows))
    print_kv("Filtered rows", format_number(summary.filtered_rows))
    print_kv("Duplicate EML rows", format_number(summary.duplicate_eml_rows))
    print_kv("Missing PDFs for OK rows", format_number(summary.missing_pdfs_for_successful_rows))
    print_kv("EMLs missing manifest rows", format_number(summary.eml_files_missing_manifest_rows))
    print_kv("Manifest EMLs missing on disk", format_number(summary.manifest_eml_paths_missing_on_disk))
    print_kv("Extra PDFs not in manifest", format_number(summary.extra_pdf_files_not_referenced_by_manifest))
    print()
    if summary.has_consistency_errors():
        print(f"Status: {yellow('NEEDS ATTENTION')}")
    else:
        print(f"Status: {green('PASS')}")
    print_issues(validation_issues(summary))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report output counts and manifest consistency.")
    parser.add_argument("--eml-dir", required=True, type=Path)
    parser.add_argument("--pdf-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = validate_output(args.eml_dir, args.pdf_dir, args.manifest)
    print_summary(summary)
    return 1 if summary.has_consistency_errors() else 0


if __name__ == "__main__":
    raise SystemExit(main())

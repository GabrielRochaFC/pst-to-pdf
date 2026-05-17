"""Safe manifest repair tooling.

This module only reads manifest CSV rows and filesystem metadata. It does not
open EML bodies or PDFs and never deletes EML/PDF files.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pst_to_pdf.converter import MANIFEST_FIELDS
from pst_to_pdf.validator import ValidationSummary, paths_with_suffix, read_manifest_rows, validate_output


@dataclass(frozen=True)
class RepairResult:
    slug: str
    manifest: Path
    backup: Path | None
    before: ValidationSummary
    after: ValidationSummary
    before_rows: int
    after_rows: int
    duplicate_extra_rows_removed: int
    eml_files_without_ok_manifest_rows: int
    applied: bool


def parse_slug_values(values: list[str]) -> list[str]:
    slugs: list[str] = []
    for value in values:
        for item in value.split(","):
            slug = item.strip()
            if slug:
                slugs.append(slug)
    return slugs


def row_sort_key(row: dict[str, str]) -> tuple[int, str, str, str]:
    status = row.get("status", "")
    pdf_path = row.get("pdf_path", "")
    pdf_exists = bool(pdf_path and Path(pdf_path).is_file())
    if status == "ok" and pdf_exists:
        rank = 0
    elif status == "ok":
        rank = 1
    elif status == "timeout":
        rank = 2
    elif status == "error":
        rank = 3
    else:
        rank = 4
    return (rank, pdf_path, row.get("error", ""), row.get("eml_path", ""))


def deduplicate_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    by_eml: dict[str, list[dict[str, str]]] = {}
    rows_without_eml: list[dict[str, str]] = []
    order: list[str] = []
    for row in rows:
        eml_path = row.get("eml_path", "")
        if not eml_path:
            rows_without_eml.append(row)
            continue
        if eml_path not in by_eml:
            order.append(eml_path)
            by_eml[eml_path] = []
        by_eml[eml_path].append(row)

    repaired: list[dict[str, str]] = []
    removed = 0
    for eml_path in order:
        candidates = sorted(by_eml[eml_path], key=row_sort_key)
        repaired.append(candidates[0])
        removed += len(candidates) - 1
    repaired.extend(rows_without_eml)
    return repaired, removed


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MANIFEST_FIELDS})


def backup_manifest(manifest: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = manifest.with_name(f"{manifest.name}.bak_{stamp}")
    shutil.copy2(manifest, backup)
    return backup


def summarize_rows(eml_dir: Path, pdf_dir: Path, rows: list[dict[str, str]]) -> ValidationSummary:
    statuses = Counter(row.get("status", "") for row in rows)
    eml_counts = Counter(row.get("eml_path", "") for row in rows if row.get("eml_path"))
    manifest_eml_paths = set(eml_counts)
    eml_paths_on_disk = paths_with_suffix(eml_dir, ".eml")
    manifest_pdf_paths = {row.get("pdf_path", "") for row in rows if row.get("pdf_path")}
    duplicate_eml_rows = sum(count - 1 for count in eml_counts.values() if count > 1)
    missing_pdfs = sum(
        1
        for row in rows
        if row.get("status") == "ok" and (not row.get("pdf_path") or not Path(row["pdf_path"]).is_file())
    )
    pdf_paths_on_disk = paths_with_suffix(pdf_dir, ".pdf")
    return ValidationSummary(
        total_eml_files=len(eml_paths_on_disk),
        total_pdf_files=len(pdf_paths_on_disk),
        total_manifest_rows=len(rows),
        successful_rows=statuses.get("ok", 0),
        failed_rows=statuses.get("error", 0),
        timeout_rows=statuses.get("timeout", 0),
        duplicate_eml_rows=duplicate_eml_rows,
        missing_pdfs_for_successful_rows=missing_pdfs,
        eml_files_missing_manifest_rows=len(eml_paths_on_disk - manifest_eml_paths),
        manifest_eml_paths_missing_on_disk=len(manifest_eml_paths - eml_paths_on_disk),
        extra_pdf_files_not_referenced_by_manifest=len(pdf_paths_on_disk - manifest_pdf_paths),
    )


def repair_slug(case_dir: Path, slug: str, apply: bool) -> RepairResult:
    root = case_dir / "output" / slug
    eml_dir = root / "eml"
    pdf_dir = root / "pdf"
    manifest = root / "manifest" / f"{slug}.csv"
    if not manifest.is_file():
        raise SystemExit(f"Manifest not found for {slug}: {manifest}")

    before = validate_output(eml_dir, pdf_dir, manifest)
    rows = read_manifest_rows(manifest)
    repaired_rows, removed = deduplicate_rows(rows)
    after = summarize_rows(eml_dir, pdf_dir, repaired_rows)
    ok_eml_paths = {row.get("eml_path", "") for row in repaired_rows if row.get("status") == "ok" and row.get("eml_path")}
    eml_without_ok = len(paths_with_suffix(eml_dir, ".eml") - ok_eml_paths)

    backup = None
    if apply:
        backup = backup_manifest(manifest)
        write_manifest(manifest, repaired_rows)
        after = validate_output(eml_dir, pdf_dir, manifest)
        ok_eml_paths = {row.get("eml_path", "") for row in repaired_rows if row.get("status") == "ok" and row.get("eml_path")}
        eml_without_ok = len(paths_with_suffix(eml_dir, ".eml") - ok_eml_paths)

    return RepairResult(
        slug=slug,
        manifest=manifest,
        backup=backup,
        before=before,
        after=after,
        before_rows=len(rows),
        after_rows=len(repaired_rows),
        duplicate_extra_rows_removed=removed,
        eml_files_without_ok_manifest_rows=eml_without_ok,
        applied=apply,
    )


def print_result(result: RepairResult) -> None:
    mode = "APPLIED" if result.applied else "DRY-RUN"
    print(f"[{result.slug}] manifest_repair {mode}")
    print(f"[{result.slug}] manifest={result.manifest}")
    if result.backup:
        print(f"[{result.slug}] backup={result.backup}")
    print(
        f"[{result.slug}] before rows={result.before_rows} duplicate_eml_rows={result.before.duplicate_eml_rows} "
        f"eml_missing_manifest={result.before.eml_files_missing_manifest_rows} "
        f"extra_pdfs={result.before.extra_pdf_files_not_referenced_by_manifest}"
    )
    print(
        f"[{result.slug}] after rows={result.after_rows} duplicate_eml_rows={result.after.duplicate_eml_rows} "
        f"eml_missing_manifest={result.after.eml_files_missing_manifest_rows} "
        f"extra_pdfs={result.after.extra_pdf_files_not_referenced_by_manifest}"
    )
    print(f"[{result.slug}] duplicate_extra_rows_removed={result.duplicate_extra_rows_removed}")
    print(f"[{result.slug}] eml_files_without_ok_manifest_rows={result.eml_files_without_ok_manifest_rows}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely deduplicate PST-to-PDF manifest rows without deleting EML/PDF files.")
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--slug", action="append", required=True, help="Output slug to repair. May be repeated or comma-separated.")
    parser.add_argument("--apply", action="store_true", help="Write repaired manifests after timestamped backups. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Preview repair counts without writing. This is the default.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    slugs = parse_slug_values(args.slug)
    if not slugs:
        raise SystemExit("At least one --slug is required")
    if args.apply and args.dry_run:
        raise SystemExit("Use either --apply or --dry-run, not both")

    for slug in slugs:
        print_result(repair_slug(args.case_dir, slug, apply=args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

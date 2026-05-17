#!/usr/bin/env python3
"""Validate local PST-to-PDF output without printing email contents."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def count_files(root: Path, suffix: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() == suffix)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report output counts and manifest consistency.")
    parser.add_argument("--eml-dir", required=True, type=Path)
    parser.add_argument("--pdf-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows: list[dict[str, str]] = []
    if args.manifest.exists():
        with args.manifest.open("r", newline="", encoding="utf-8") as csvfile:
            rows = list(csv.DictReader(csvfile))

    statuses = Counter(row.get("status", "") for row in rows)
    eml_counts = Counter(row.get("eml_path", "") for row in rows if row.get("eml_path"))
    duplicate_eml_rows = sum(count - 1 for count in eml_counts.values() if count > 1)
    missing_pdfs = sum(
        1
        for row in rows
        if row.get("status") == "ok" and (not row.get("pdf_path") or not Path(row["pdf_path"]).is_file())
    )

    print(f"total_eml_files={count_files(args.eml_dir, '.eml')}")
    print(f"total_pdf_files={count_files(args.pdf_dir, '.pdf')}")
    print(f"total_manifest_rows={len(rows)}")
    print(f"successful_rows={statuses.get('ok', 0)}")
    print(f"failed_rows={statuses.get('error', 0)}")
    print(f"timeout_rows={statuses.get('timeout', 0)}")
    print(f"duplicate_eml_rows={duplicate_eml_rows}")
    print(f"missing_pdfs_for_successful_rows={missing_pdfs}")
    return 1 if duplicate_eml_rows or missing_pdfs else 0


if __name__ == "__main__":
    raise SystemExit(main())

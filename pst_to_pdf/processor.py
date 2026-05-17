#!/usr/bin/env python3
"""Process all PST files for one user/case directory.

Expected layout:
  case-dir/
    input/*.pst
    output/<pst-slug>/{eml,pdf,manifest}
    logs/

This script orchestrates local extraction, conversion, and validation. It does
not print email body content.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


from pst_to_pdf.extraction import ensure_readpst_available, extract_pst, wait_for_stable_eml_tree
from pst_to_pdf.validator import ValidationSummary, validate_output


@dataclass(frozen=True)
class PstJob:
    pst_path: Path
    slug: str
    eml_dir: Path
    pdf_dir: Path
    manifest: Path
    extract_log: Path
    convert_log: Path


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def pst_slug(path: Path) -> str:
    stem = path.stem.lower()
    if "@" in stem:
        local, rest = stem.split("@", 1)
        suffix_match = re.search(r"(?:^|[._-])(\d+)$", rest)
        stem = f"{local}-{suffix_match.group(1)}" if suffix_match else local
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "pst"


def unique_slug(path: Path, used: set[str]) -> str:
    slug = pst_slug(path)
    if slug not in used:
        used.add(slug)
        return slug
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:8]
    slug = f"{slug}-{digest}"
    used.add(slug)
    return slug


def build_jobs(args: argparse.Namespace) -> list[PstJob]:
    input_dir = args.case_dir / "input"
    output_dir = args.case_dir / "output"
    logs_dir = args.case_dir / "logs"
    pst_paths = sorted(input_dir.glob("*.pst"))
    used_slugs: set[str] = set()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobs: list[PstJob] = []
    for pst_path in pst_paths:
        slug = unique_slug(pst_path, used_slugs)
        job_output = output_dir / slug
        jobs.append(
            PstJob(
                pst_path=pst_path,
                slug=slug,
                eml_dir=job_output / "eml",
                pdf_dir=job_output / "pdf",
                manifest=job_output / "manifest" / f"{slug}.csv",
                extract_log=logs_dir / f"extract_{slug}_{stamp}.log",
                convert_log=logs_dir / f"convert_{slug}_{stamp}.log",
            )
        )
    return jobs


def run_extraction(job: PstJob, force_extract: bool, dry_run: bool) -> tuple[bool, float]:
    return extract_pst(job.pst_path, job.eml_dir, job.extract_log, job.slug, force_extract, dry_run)


def run_conversion(job: PstJob, args: argparse.Namespace) -> float:
    command = [
        sys.executable,
        "-m",
        "pst_to_pdf.converter",
        "--source-pst",
        str(job.pst_path),
        "--eml-dir",
        str(job.eml_dir),
        "--pdf-dir",
        str(job.pdf_dir),
        "--manifest",
        str(job.manifest),
        "--log-file",
        str(job.convert_log),
        "--resume",
        "--mode",
        args.mode,
        "--workers",
        str(args.workers),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--eml-stability-seconds",
        str(args.eml_stability_seconds),
        "--eml-stability-check-interval",
        str(args.eml_stability_check_interval),
        "--eml-stability-max-wait",
        str(args.eml_stability_max_wait),
    ]
    print(f"[{job.slug}] converting EML to PDF")
    if args.dry_run:
        print(f"[{job.slug}] dry-run convert command: {' '.join(command)}")
        return 0.0

    job.pdf_dir.mkdir(parents=True, exist_ok=True)
    job.manifest.parent.mkdir(parents=True, exist_ok=True)
    job.convert_log.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    result = subprocess.run(command, check=False)
    elapsed = time.monotonic() - started_at
    if result.returncode == 130:
        raise KeyboardInterrupt
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"conversion command failed for {job.pst_path}; see {job.convert_log}")
    print(f"[{job.slug}] conversion finished elapsed={format_elapsed(elapsed)} log={job.convert_log}")
    return elapsed


def print_validation(label: str, summary: ValidationSummary) -> None:
    print(
        f"[{label}] validation "
        f"eml={summary.total_eml_files} pdf={summary.total_pdf_files} manifest_rows={summary.total_manifest_rows} "
        f"ok={summary.successful_rows} failed={summary.failed_rows} timeout={summary.timeout_rows} "
        f"duplicate_eml_rows={summary.duplicate_eml_rows} missing_pdfs={summary.missing_pdfs_for_successful_rows} "
        f"eml_files_missing_manifest_rows={summary.eml_files_missing_manifest_rows} "
        f"manifest_eml_missing_on_disk={summary.manifest_eml_paths_missing_on_disk} "
        f"extra_pdf_files_not_referenced_by_manifest={summary.extra_pdf_files_not_referenced_by_manifest}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process all PSTs in a case directory with standard local output paths.")
    parser.add_argument("--case-dir", required=True, type=Path, help="Directory containing input/*.pst and receiving output/ and logs/.")
    parser.add_argument("--mode", choices=["fast", "weasyprint"], default="fast")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--force-extract", action="store_true", help="Run readpst even when EML files already exist.")
    parser.add_argument("--validate-only", action="store_true", help="Only print validation summaries for discovered PST outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned paths and commands without creating files or running conversion.")
    parser.add_argument("--eml-stability-seconds", type=int, default=10, help="Seconds the EML tree must stay unchanged before conversion.")
    parser.add_argument("--eml-stability-check-interval", type=int, default=2, help="Seconds between EML tree stability checks.")
    parser.add_argument("--eml-stability-max-wait", type=int, default=600, help="Maximum seconds to wait for EML tree stability.")
    return parser.parse_args()


def run_case(
    case_dir: Path,
    mode: str = "fast",
    workers: int = 8,
    timeout_seconds: int = 60,
    force_extract: bool = False,
    validate_only: bool = False,
    dry_run: bool = False,
    eml_stability_seconds: int = 10,
    eml_stability_check_interval: int = 2,
    eml_stability_max_wait: int = 600,
) -> int:
    """Run the standard local PST processing workflow for one case directory."""
    args = argparse.Namespace(
        case_dir=case_dir,
        mode=mode,
        workers=workers,
        timeout_seconds=timeout_seconds,
        force_extract=force_extract,
        validate_only=validate_only,
        dry_run=dry_run,
        eml_stability_seconds=eml_stability_seconds,
        eml_stability_check_interval=eml_stability_check_interval,
        eml_stability_max_wait=eml_stability_max_wait,
    )
    started_at = time.monotonic()

    if args.mode not in {"fast", "weasyprint"}:
        raise SystemExit("--mode must be one of: fast, weasyprint")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if args.timeout_seconds < 0:
        raise SystemExit("--timeout-seconds must be >= 0")
    if args.eml_stability_seconds < 0:
        raise SystemExit("--eml-stability-seconds must be >= 0")
    if not args.validate_only:
        ensure_readpst_available()

    input_dir = args.case_dir / "input"
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    jobs = build_jobs(args)
    if not jobs:
        raise SystemExit(f"No .pst files found in {input_dir}")

    print(f"case_dir={args.case_dir}")
    print(f"psts_found={len(jobs)} mode={args.mode} workers={args.workers} timeout_seconds={args.timeout_seconds}")
    for job in jobs:
        print(f"[{job.slug}] pst={job.pst_path}")
        print(f"[{job.slug}] output={job.eml_dir.parent}")

    if args.dry_run:
        for job in jobs:
            run_extraction(job, args.force_extract, dry_run=True)
            run_conversion(job, args)
        return 0

    total_extract = 0.0
    total_convert = 0.0
    total_summary = ValidationSummary()

    try:
        for job in jobs:
            if not args.validate_only:
                _ran, elapsed = run_extraction(job, args.force_extract, dry_run=False)
                total_extract += elapsed
                wait_for_stable_eml_tree(
                    job.eml_dir,
                    job.slug,
                    stable_seconds=args.eml_stability_seconds,
                    check_interval=args.eml_stability_check_interval,
                    max_wait_seconds=args.eml_stability_max_wait,
                )
                total_convert += run_conversion(job, args)
            summary = validate_output(job.eml_dir, job.pdf_dir, job.manifest)
            total_summary.add(summary)
            print_validation(job.slug, summary)
    except KeyboardInterrupt:
        elapsed = format_elapsed(time.monotonic() - started_at)
        print(f"Interrupted. Existing files kept. Re-run the same command to resume. elapsed={elapsed}")
        return 130

    total_elapsed = time.monotonic() - started_at
    print_validation("total", total_summary)
    print(
        f"timing total={format_elapsed(total_elapsed)} "
        f"extraction={format_elapsed(total_extract)} conversion={format_elapsed(total_convert)}"
    )
    if total_summary.has_consistency_errors():
        return 1
    return 0


def main() -> int:
    args = parse_args()
    return run_case(
        case_dir=args.case_dir,
        mode=args.mode,
        workers=args.workers,
        timeout_seconds=args.timeout_seconds,
        force_extract=args.force_extract,
        validate_only=args.validate_only,
        dry_run=args.dry_run,
        eml_stability_seconds=args.eml_stability_seconds,
        eml_stability_check_interval=args.eml_stability_check_interval,
        eml_stability_max_wait=args.eml_stability_max_wait,
    )


if __name__ == "__main__":
    raise SystemExit(main())

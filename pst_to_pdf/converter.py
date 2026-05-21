#!/usr/bin/env python3
"""Convert extracted EML files to local PDF files and a manifest CSV.

Privacy boundary:
  - Email bodies are parsed only to generate local PDFs.
  - Email bodies are never printed to stdout/stderr or logs.
  - Manifest writing happens only in the main process.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import logging
import multiprocessing as mp
import re
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, cast

from pst_to_pdf.extraction import wait_for_stable_eml_tree
from pst_to_pdf.output import finish_dynamic_line, format_number, print_kv, print_section, write_dynamic_line


MANIFEST_FIELDS = [
    "source_pst_path",
    "source_pst_sha256",
    "eml_path",
    "pdf_path",
    "subject",
    "from",
    "to",
    "cc",
    "bcc",
    "date",
    "message_id",
    "attachment_filenames",
    "status",
    "error",
]

HEADER_LABELS = [
    "Subject",
    "From",
    "To",
    "Cc",
    "Bcc",
    "Date",
    "Message-ID",
    "Source EML path",
    "Attachment filenames",
]


class HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "table",
        "tr",
    }
    SKIP_TAGS = {"style", "script", "head", "title", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self.SKIP_TAGS:
            self._skip_depth += 1
        if t in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if t in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        pass

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in raw.splitlines()]
        compact: list[str] = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank:
                    compact.append("")
                previous_blank = True
                continue
            compact.append(line)
            previous_blank = False
        return "\n".join(compact).strip()


@dataclass(frozen=True)
class Task:
    index: int
    eml_path: Path
    pdf_path: Path


@dataclass
class RunningTask:
    task: Task
    process: mp.Process
    queue: mp.Queue
    started_at: float


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_eml_files(root: Path) -> Iterable[Path]:
    yield from sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".eml")


def header_value(message: Message, name: str) -> str:
    value = message.get(name, "")
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def part_filename(part: Message) -> str | None:
    filename = part.get_filename()
    return Path(filename).name if filename else None


def attachment_filenames(message: Message) -> list[str]:
    names: list[str] = []
    for part in message.walk() if message.is_multipart() else [message]:
        disposition = part.get_content_disposition()
        filename = part_filename(part)
        if filename and disposition in {"attachment", "inline"}:
            names.append(filename)
    return names


def decode_text_part(part: Message) -> str:
    payload = cast(bytes | None, part.get_payload(decode=True))
    charset = part.get_content_charset() or "utf-8"
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    return payload.decode(charset, errors="replace")


def html_to_text(value: str) -> str:
    parser = HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def message_body_text(message: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(decode_text_part(part))
        elif content_type == "text/html":
            html_parts.append(html_to_text(decode_text_part(part)))
    if plain_parts:
        return "\n\n".join(text.strip() for text in plain_parts if text.strip()).strip()
    return "\n\n".join(text.strip() for text in html_parts if text.strip()).strip()


def output_pdf_name(index: int, eml_path: Path, eml_root: Path) -> str:
    rel = eml_path.relative_to(eml_root).as_posix()
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", eml_path.stem)[:80] or "email"
    return f"{index:08d}_{stem}_{digest}.pdf"


def parse_message(eml_path: Path) -> tuple[dict[str, str], str]:
    with eml_path.open("rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle)
    attachments = attachment_filenames(message)
    metadata = {
        "Subject": header_value(message, "subject"),
        "From": header_value(message, "from"),
        "To": header_value(message, "to"),
        "Cc": header_value(message, "cc"),
        "Bcc": header_value(message, "bcc"),
        "Date": header_value(message, "date"),
        "Message-ID": header_value(message, "message-id"),
        "Source EML path": str(eml_path),
        "Attachment filenames": "; ".join(attachments),
    }
    return metadata, message_body_text(message)


def display_eml_path(eml_path: Path, case_dir: Path | None) -> str:
    """Return a display path for the PDF: relative to case_dir.parent when possible.

    Keeps the case directory name in the displayed path so the reader can
    identify which case the email belongs to without exposing the full host path.
    Falls back to the absolute path if case_dir is None or the EML path is
    not under case_dir.parent.
    """
    if case_dir is not None:
        try:
            return str(eml_path.relative_to(case_dir.parent))
        except ValueError:
            pass
    return str(eml_path)


def block_external_fetches(url: str, *args: object, **kwargs: object) -> dict[str, bytes | str]:
    raise ValueError(f"External resource loading is disabled for PDF generation: {url}")


def pdf_html(metadata: dict[str, str], body: str) -> str:
    rows = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(metadata.get(label, ''))}</td></tr>"
        for label in HEADER_LABELS
    )
    safe_body = html.escape(body or "[No text body found]")
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 18mm 15mm; }}
    body {{ font-family: sans-serif; font-size: 11pt; line-height: 1.45; color: #111; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 16pt; table-layout: fixed; }}
    th, td {{ border: 1px solid #bbb; padding: 5pt; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ width: 28%; background: #f2f2f2; text-align: left; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-family: sans-serif; }}
  </style>
</head>
<body>
  <table>{rows}</table>
  <pre>{safe_body}</pre>
</body>
</html>"""


def write_weasy_pdf(pdf_path: Path, metadata: dict[str, str], body: str) -> None:
    from weasyprint import HTML

    HTML(string=pdf_html(metadata, body), base_url=str(pdf_path.parent), url_fetcher=block_external_fetches).write_pdf(pdf_path)


def reportlab_text(value: str) -> str:
    return html.escape(value or "").replace("\n", "<br/>")


def sanitize_header_value(value: str) -> str:
    """Collapse CR/LF/tab to spaces so long address fields don't break ReportLab."""
    return re.sub(r"[\r\n\t]+", " ", value or "").strip()


def write_fast_pdf(pdf_path: Path, metadata: dict[str, str], body: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("EmailNormal", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12)
    label_style = ParagraphStyle("EmailLabel", parent=normal, fontName="Helvetica-Bold", spaceBefore=4)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story: list = []

    for name in HEADER_LABELS:
        raw = sanitize_header_value(metadata.get(name, ""))
        story.append(Paragraph(html.escape(name) + ":", label_style))
        story.append(Paragraph(html.escape(raw) if raw else "[none]", normal))

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5))
    story.append(Spacer(1, 4 * mm))

    for chunk in (body or "[No text body found]").split("\n\n"):
        story.append(Paragraph(reportlab_text(chunk), normal))
        story.append(Spacer(1, 3 * mm))

    doc.build(story)


def base_row(source_pst: Path, pst_sha256: str, eml_path: Path, pdf_path: Path, metadata: dict[str, str]) -> dict[str, str]:
    return {
        "source_pst_path": str(source_pst),
        "source_pst_sha256": pst_sha256,
        "eml_path": str(eml_path),
        "pdf_path": str(pdf_path),
        "subject": metadata["Subject"],
        "from": metadata["From"],
        "to": metadata["To"],
        "cc": metadata["Cc"],
        "bcc": metadata["Bcc"],
        "date": metadata["Date"],
        "message_id": metadata["Message-ID"],
        "attachment_filenames": metadata["Attachment filenames"].replace("; ", "|"),
        "status": "ok",
        "error": "",
    }


def status_row(source_pst: Path, pst_sha256: str, eml_path: Path, pdf_path: Path, status: str, error: str) -> dict[str, str]:
    return {
        "source_pst_path": str(source_pst),
        "source_pst_sha256": pst_sha256,
        "eml_path": str(eml_path),
        "pdf_path": str(pdf_path) if pdf_path else "",
        "subject": "",
        "from": "",
        "to": "",
        "cc": "",
        "bcc": "",
        "date": "",
        "message_id": "",
        "attachment_filenames": "",
        "status": status,
        "error": error,
    }


def filtered_row(
    source_pst: Path,
    pst_sha256: str,
    eml_path: Path,
    metadata: dict[str, str],
) -> dict[str, str]:
    """Manifest row for an EML skipped by the participant filter.

    Records participant headers so the filter decision is auditable from the
    manifest alone. No body content is included.
    """
    return {
        "source_pst_path": str(source_pst),
        "source_pst_sha256": pst_sha256,
        "eml_path": str(eml_path),
        "pdf_path": "",
        "subject": metadata.get("Subject", ""),
        "from": metadata.get("From", ""),
        "to": metadata.get("To", ""),
        "cc": metadata.get("Cc", ""),
        "bcc": metadata.get("Bcc", ""),
        "date": metadata.get("Date", ""),
        "message_id": metadata.get("Message-ID", ""),
        "attachment_filenames": "",
        "status": "filtered",
        "error": "filtered by email participant",
    }


def filter_check_eml(
    eml_path: Path,
    filter_set: frozenset[str],
) -> tuple[bool, dict[str, str]]:
    """Header-only filter check.

    Parses just the EML headers — never the body. Returns (matched, metadata)
    where `metadata` carries the participant + audit headers needed to write
    either a `filtered` manifest row or a normal one.
    """
    from pst_to_pdf.filter_emails import message_matches

    with eml_path.open("rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle, headersonly=True)
    metadata = {
        "Subject": header_value(message, "subject"),
        "From":    header_value(message, "from"),
        "To":      header_value(message, "to"),
        "Cc":      header_value(message, "cc"),
        "Bcc":     header_value(message, "bcc"),
        "Date":    header_value(message, "date"),
        "Message-ID": header_value(message, "message-id"),
    }
    return message_matches(message, filter_set), metadata


def convert_task(task: Task, eml_root: Path, source_pst: Path, pst_sha256: str, mode: str, case_dir: Path | None = None) -> dict[str, str]:
    metadata, body = parse_message(task.eml_path)
    display_metadata = dict(metadata)
    display_metadata["Source EML path"] = display_eml_path(task.eml_path, case_dir)
    if mode == "weasyprint":
        write_weasy_pdf(task.pdf_path, display_metadata, body)
    else:
        write_fast_pdf(task.pdf_path, display_metadata, body)
    return base_row(source_pst, pst_sha256, task.eml_path, task.pdf_path, metadata)


def recover_existing_pdf_row(task: Task, source_pst: Path, pst_sha256: str) -> dict[str, str]:
    metadata, _body = parse_message(task.eml_path)
    return base_row(source_pst, pst_sha256, task.eml_path, task.pdf_path, metadata)


def worker_main(queue: mp.Queue, task: Task, eml_root: str, source_pst: str, pst_sha256: str, mode: str, case_dir_str: str = "") -> None:
    try:
        case_dir = Path(case_dir_str) if case_dir_str else None
        row = convert_task(task, Path(eml_root), Path(source_pst), pst_sha256, mode, case_dir)
    except Exception as exc:  # noqa: BLE001 - main process records failure row
        row = status_row(Path(source_pst), pst_sha256, task.eml_path, task.pdf_path, "error", f"{type(exc).__name__}: {exc}")
    queue.put(row)


def read_manifest_rows(manifest: Path) -> list[dict[str, str]]:
    if not manifest.exists():
        return []
    with manifest.open("r", newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def preferred_row(existing: dict[str, str] | None, candidate: dict[str, str]) -> dict[str, str]:
    if existing is None:
        return candidate
    if existing.get("status") == "ok":
        return existing
    if candidate.get("status") == "ok":
        return candidate
    return candidate


def deduplicate_manifest_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_eml: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in rows:
        eml_path = row.get("eml_path", "")
        if not eml_path:
            continue
        if eml_path not in by_eml:
            order.append(eml_path)
        by_eml[eml_path] = preferred_row(by_eml.get(eml_path), row)
    return [by_eml[eml_path] for eml_path in order]


def backup_manifest(manifest: Path) -> Path | None:
    if not manifest.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = manifest.with_name(f"{manifest.name}.bak_{stamp}")
    shutil.copy2(manifest, backup)
    return backup


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MANIFEST_FIELDS})


def prepare_manifest(manifest: Path, resume: bool) -> tuple[set[str], set[str], int, Path | None]:
    """Prepare manifest for resume.

    Returns (successful_paths, filtered_paths, kept_row_count, backup). On resume,
    both `ok` and `filtered` rows are retained — filtered rows represent
    intentional skips that don't need to be redone. `error` and `timeout` rows
    are dropped so the converter can retry them.
    """
    rows = read_manifest_rows(manifest)
    backup = None
    if rows and resume:
        compact = deduplicate_manifest_rows(rows)
        backup = backup_manifest(manifest)
        rows = [row for row in compact if row.get("status") in {"ok", "filtered"}]
        write_manifest(manifest, rows)
    successful = {row["eml_path"] for row in rows if row.get("status") == "ok" and row.get("eml_path")}
    filtered = {row["eml_path"] for row in rows if row.get("status") == "filtered" and row.get("eml_path")}
    return successful, filtered, len(rows), backup


def ensure_safe_outputs(pdf_dir: Path, manifest: Path, force: bool, resume: bool) -> None:
    if resume:
        return
    if pdf_dir.exists() and any(pdf_dir.iterdir()) and not force:
        raise SystemExit(f"PDF output directory is not empty: {pdf_dir}. Re-run with --resume or --force.")
    if manifest.exists() and not force:
        raise SystemExit(f"Manifest already exists: {manifest}. Re-run with --resume or --force.")


def start_task(context: Any, task: Task, args: argparse.Namespace, pst_sha256: str) -> RunningTask:
    queue: mp.Queue = context.Queue(maxsize=1)
    case_dir_str = str(args.case_dir) if getattr(args, "case_dir", None) else ""
    process = context.Process(
        target=worker_main,
        args=(queue, task, str(args.eml_dir), str(args.source_pst), pst_sha256, args.mode, case_dir_str),
    )
    process.start()
    return RunningTask(task=task, process=process, queue=queue, started_at=time.monotonic())


def collect_finished(running: list[RunningTask], args: argparse.Namespace, pst_sha256: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    still_running: list[RunningTask] = []
    now = time.monotonic()
    for item in running:
        timed_out = args.timeout_seconds > 0 and now - item.started_at > args.timeout_seconds
        if timed_out:
            item.process.terminate()
            item.process.join(5)
            if item.process.is_alive():
                item.process.kill()
                item.process.join()
            rows.append(status_row(args.source_pst, pst_sha256, item.task.eml_path, item.task.pdf_path, "timeout", f"Timeout after {args.timeout_seconds} seconds"))
            continue
        if item.process.is_alive():
            still_running.append(item)
            continue
        item.process.join()
        if not item.queue.empty():
            rows.append(item.queue.get())
        else:
            rows.append(status_row(args.source_pst, pst_sha256, item.task.eml_path, item.task.pdf_path, "error", f"Worker exited with code {item.process.exitcode}"))
    running[:] = still_running
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert local EML files to PDFs and a manifest CSV.")
    parser.add_argument("--source-pst", required=True, type=Path)
    parser.add_argument("--eml-dir", required=True, type=Path)
    parser.add_argument("--pdf-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--log-file", required=True, type=Path)
    parser.add_argument("--case-dir", type=Path, default=None, help="Case directory. EML paths shown in PDFs are made relative to its parent.")
    parser.add_argument("--force", action="store_true", help="Allow writing into existing output without resume.")
    parser.add_argument("--resume", action="store_true", help="Skip successful manifest rows and append only remaining work.")
    parser.add_argument("--mode", choices=["fast", "weasyprint"], default="fast", help="PDF engine. fast uses ReportLab; weasyprint renders constructed HTML.")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel conversion workers.")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Per-message timeout. Use 0 to disable.")
    parser.add_argument("--eml-stability-seconds", type=int, default=10, help="Seconds the EML tree must stay unchanged before task enumeration.")
    parser.add_argument("--eml-stability-check-interval", type=int, default=2, help="Seconds between EML tree stability checks.")
    parser.add_argument("--eml-stability-max-wait", type=int, default=600, help="Maximum seconds to wait for EML tree stability.")
    parser.add_argument(
        "--filter-file",
        type=Path,
        default=None,
        help="Path to a file containing one normalized email address per line. "
             "When set, only EMLs whose participant headers contain at least "
             "one of these addresses produce PDFs; others get status=filtered.",
    )
    parser.add_argument(
        "--filter-email",
        action="append",
        default=[],
        help="Email address to include in the participant filter. Repeatable. "
             "Merged with --filter-file if both are provided.",
    )
    return parser.parse_args()


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _conversion_progress_line(
    label: str,
    processed: int,
    total: int,
    converted: int,
    recovered: int,
    skipped: int,
    filtered: int,
    failed: int,
    timed_out: int,
    started_at: float,
) -> str:
    """Single-line summary for TTY dynamic output."""
    elapsed_seconds = time.monotonic() - started_at
    pct = processed / total * 100.0 if total > 0 else 0.0
    rate_per_sec = processed / elapsed_seconds if elapsed_seconds > 0 else 0.0
    remaining = total - processed
    eta = format_elapsed(remaining / rate_per_sec) if rate_per_sec > 0 and remaining > 0 else "--:--:--"
    ok = converted + recovered
    return (
        f"[{label}] {format_number(processed)}/{format_number(total)} ({pct:.1f}%)"
        f" | ok {format_number(ok)}"
        f" | filtered {format_number(filtered)}"
        f" | skip {format_number(skipped)}"
        f" | fail {format_number(failed)}"
        f" | t/o {format_number(timed_out)}"
        f" | {format_elapsed(elapsed_seconds)}"
        f" | ETA {eta}"
    )


def print_conversion_progress(
    label: str,
    processed: int,
    total: int,
    converted: int,
    recovered: int,
    skipped: int,
    filtered: int,
    failed: int,
    timed_out: int,
    started_at: float,
) -> None:
    """Block-style progress for non-TTY output (piped / logged)."""
    elapsed_seconds = time.monotonic() - started_at
    rate = (processed / elapsed_seconds * 60) if elapsed_seconds > 0 else 0.0
    pct = processed / total * 100.0 if total > 0 else 0.0
    remaining = total - processed
    rate_per_sec = processed / elapsed_seconds if elapsed_seconds > 0 else 0.0
    eta = format_elapsed(remaining / rate_per_sec) if rate_per_sec > 0 and remaining > 0 else "--:--:--"
    print_section(f"[{label}] Conversion progress")
    print_kv("Progress", f"{format_number(processed)} / {format_number(total)} ({pct:.1f}%)")
    print_kv("Converted", format_number(converted))
    print_kv("Recovered", format_number(recovered))
    print_kv("Filtered", format_number(filtered))
    print_kv("Skipped", format_number(skipped))
    print_kv("Failed", format_number(failed))
    print_kv("Timeout", format_number(timed_out))
    print_kv("Remaining", format_number(remaining))
    print_kv("Elapsed", format_elapsed(elapsed_seconds))
    print_kv("Rate/min", format_number(rate))
    print_kv("ETA", eta)


def main() -> int:
    started_at = time.monotonic()
    args = parse_args()
    if not args.source_pst.is_file():
        raise SystemExit(f"Source PST not found: {args.source_pst}")
    if not args.eml_dir.is_dir():
        raise SystemExit(f"EML directory not found: {args.eml_dir}")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if args.eml_stability_seconds < 0:
        raise SystemExit("--eml-stability-seconds must be >= 0")

    from pst_to_pdf.filter_emails import load_filter_file, parse_email_list

    filter_emails_list: list[str] = []
    if args.filter_file is not None:
        if not args.filter_file.is_file():
            raise SystemExit(f"Filter file not found: {args.filter_file}")
        filter_emails_list.extend(load_filter_file(args.filter_file))
    if args.filter_email:
        filter_emails_list.extend(parse_email_list(",".join(args.filter_email)))
    seen_filter: set[str] = set()
    deduped_filter: list[str] = []
    for e in filter_emails_list:
        if e and e not in seen_filter:
            seen_filter.add(e)
            deduped_filter.append(e)
    filter_set: frozenset[str] = frozenset(deduped_filter)
    if (args.filter_file or args.filter_email) and not filter_set:
        raise SystemExit("Filter requested but no valid email addresses provided.")

    ensure_safe_outputs(args.pdf_dir, args.manifest, args.force, args.resume)
    args.pdf_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(filename=args.log_file, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Starting conversion source=%s eml_dir=%s pdf_dir=%s mode=%s workers=%s", args.source_pst, args.eml_dir, args.pdf_dir, args.mode, args.workers)
    label = args.manifest.stem
    print_section("Waiting for stable EML output")
    snapshot = wait_for_stable_eml_tree(
        args.eml_dir,
        label,
        stable_seconds=args.eml_stability_seconds,
        check_interval=args.eml_stability_check_interval,
        max_wait_seconds=args.eml_stability_max_wait,
    )
    logging.info("EML tree stable count=%s size=%s newest_mtime=%s", snapshot.count, snapshot.total_size, snapshot.newest_mtime)

    pst_sha256 = sha256_file(args.source_pst)
    successful_paths, filtered_paths, existing_rows, backup = prepare_manifest(args.manifest, args.resume)
    if backup:
        logging.info("Backed up manifest to %s", backup)

    all_tasks = [
        Task(index=index, eml_path=eml_path, pdf_path=args.pdf_dir / output_pdf_name(index, eml_path, args.eml_dir))
        for index, eml_path in enumerate(iter_eml_files(args.eml_dir), start=1)
    ]
    total = len(all_tasks)
    skipped = 0
    recovered = 0
    converted = 0
    failed = 0
    timed_out = 0
    filtered = 0
    processed = 0
    last_progress_logged = 0   # for log-every-100
    last_block_reported = 0    # for non-TTY block-every-100
    last_dynamic_update = 0.0  # for TTY dynamic line (seconds)

    manifest_mode = "a" if args.resume and args.manifest.exists() else "w"
    context = mp.get_context("fork")
    running: list[RunningTask] = []
    is_tty = sys.stdout.isatty()

    try:
        with args.manifest.open(manifest_mode, newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=MANIFEST_FIELDS)
            if manifest_mode == "w":
                writer.writeheader()

            pending = iter(all_tasks)
            exhausted = False
            while not exhausted or running:
                while not exhausted and len(running) < args.workers:
                    try:
                        task = next(pending)
                    except StopIteration:
                        exhausted = True
                        break

                    if str(task.eml_path) in successful_paths:
                        skipped += 1
                        processed += 1
                        continue

                    if filter_set and str(task.eml_path) in filtered_paths:
                        skipped += 1
                        processed += 1
                        continue

                    if args.resume and task.pdf_path.exists():
                        row = recover_existing_pdf_row(task, args.source_pst, pst_sha256)
                        successful_paths.add(str(task.eml_path))
                        writer.writerow(row)
                        csvfile.flush()
                        recovered += 1
                        processed += 1
                        continue

                    if filter_set:
                        try:
                            matched, header_metadata = filter_check_eml(task.eml_path, filter_set)
                        except Exception as exc:  # noqa: BLE001
                            logging.warning(
                                "Filter header parse failed eml=%s err=%s",
                                task.eml_path, exc,
                            )
                            running.append(start_task(context, task, args, pst_sha256))
                            continue
                        if not matched:
                            row = filtered_row(
                                args.source_pst, pst_sha256,
                                task.eml_path, header_metadata,
                            )
                            filtered_paths.add(str(task.eml_path))
                            writer.writerow(row)
                            csvfile.flush()
                            filtered += 1
                            processed += 1
                            continue

                    running.append(start_task(context, task, args, pst_sha256))

                for row in collect_finished(running, args, pst_sha256):
                    writer.writerow(row)
                    csvfile.flush()
                    processed += 1
                    status = row.get("status")
                    if status == "ok":
                        converted += 1
                        successful_paths.add(row["eml_path"])
                    elif status == "timeout":
                        timed_out += 1
                        logging.error("Timed out EML path=%s error=%s", row.get("eml_path"), row.get("error"))
                    else:
                        failed += 1
                        logging.error("Failed EML path=%s error=%s", row.get("eml_path"), row.get("error"))

                progress_bucket = processed // 100
                # Always log at 100-message intervals
                if progress_bucket > last_progress_logged:
                    last_progress_logged = progress_bucket
                    logging.info(
                        "Progress processed=%s converted=%s recovered=%s filtered=%s skipped=%s failed=%s timeout=%s remaining=%s elapsed=%s",
                        processed, converted, recovered, filtered, skipped, failed, timed_out,
                        total - processed, format_elapsed(time.monotonic() - started_at),
                    )

                now = time.monotonic()
                if is_tty:
                    if now - last_dynamic_update >= 1.0:
                        write_dynamic_line(_conversion_progress_line(label, processed, total, converted, recovered, skipped, filtered, failed, timed_out, started_at))
                        last_dynamic_update = now
                else:
                    if progress_bucket > last_block_reported:
                        last_block_reported = progress_bucket
                        print_conversion_progress(label, processed, total, converted, recovered, skipped, filtered, failed, timed_out, started_at)

                if running and (exhausted or len(running) >= args.workers):
                    time.sleep(0.2)
    except KeyboardInterrupt:
        if is_tty:
            finish_dynamic_line()
        for item in running:
            if item.process.is_alive():
                item.process.terminate()
                item.process.join(5)
                if item.process.is_alive():
                    item.process.kill()
                    item.process.join()
        elapsed = format_elapsed(time.monotonic() - started_at)
        print(f"Interrupted. Partial manifest kept at {args.manifest}. Resume with --resume. elapsed={elapsed}", flush=True)
        logging.warning("Interrupted by user elapsed=%s processed=%s converted=%s recovered=%s filtered=%s skipped=%s failed=%s timeout=%s", elapsed, processed, converted, recovered, filtered, skipped, failed, timed_out)
        return 130

    if is_tty:
        finish_dynamic_line()

    final = Counter(row.get("status", "") for row in read_manifest_rows(args.manifest))
    elapsed_seconds = time.monotonic() - started_at
    elapsed = format_elapsed(elapsed_seconds)
    rate = (processed / elapsed_seconds * 60) if elapsed_seconds > 0 else 0.0
    logging.info("Finished conversion converted=%s recovered=%s filtered=%s skipped=%s failed=%s timeout=%s manifest_statuses=%s existing_rows_before=%s elapsed=%s rate_per_min=%.2f", converted, recovered, filtered, skipped, failed, timed_out, dict(final), existing_rows, elapsed, rate)
    print_section(f"Conversion finished — {label}")
    print_kv("Processed", format_number(processed))
    print_kv("Converted", format_number(converted))
    print_kv("Recovered", format_number(recovered))
    print_kv("Filtered", format_number(filtered))
    print_kv("Skipped", format_number(skipped))
    print_kv("Failed", format_number(failed))
    print_kv("Timeout", format_number(timed_out))
    print_kv("Elapsed", elapsed)
    print_kv("Rate/min", format_number(rate))
    print_kv("Manifest", args.manifest)
    return 0 if failed == 0 and timed_out == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Convert extracted EML files to local PDF files and a manifest CSV.

This script never prints email body content. Conversion errors are logged per
message so one bad EML does not stop the whole run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import logging
import multiprocessing as mp
import re
import sys
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage, Message
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

try:
    from weasyprint import HTML
except ImportError as exc:  # pragma: no cover - exercised by environment
    raise SystemExit(
        "Missing Python package 'weasyprint'. Create .venv and install requirements.txt first."
    ) from exc


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


class HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {"address", "article", "aside", "blockquote", "br", "div", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "p", "pre", "section", "table", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

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
    if filename:
        return Path(filename).name
    return None


def attachment_filenames(message: Message) -> list[str]:
    names: list[str] = []
    for part in message.walk() if message.is_multipart() else [message]:
        disposition = part.get_content_disposition()
        filename = part_filename(part)
        if filename and disposition in {"attachment", "inline"}:
            names.append(filename)
    return names


def decode_text_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
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
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(decode_text_part(part))
        elif content_type == "text/html":
            html_parts.append(html_to_text(decode_text_part(part)))

    if plain_parts:
        return "\n\n".join(text.strip() for text in plain_parts if text.strip()).strip()
    return "\n\n".join(text.strip() for text in html_parts if text.strip()).strip()


def block_external_fetches(url: str, *args: object, **kwargs: object) -> dict[str, bytes | str]:
    raise ValueError(f"External resource loading is disabled for PDF generation: {url}")


def pdf_html(metadata: dict[str, str], body: str) -> str:
    rows = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value or '')}</td></tr>"
        for label, value in metadata.items()
    )
    safe_body = html.escape(body or "[No text body found]")
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 18mm 15mm; }}
    body {{ font-family: sans-serif; font-size: 11pt; line-height: 1.45; color: #111; }}
    h1 {{ font-size: 16pt; margin: 0 0 12pt; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 16pt; table-layout: fixed; }}
    th, td {{ border: 1px solid #bbb; padding: 5pt; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ width: 28%; background: #f2f2f2; text-align: left; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-family: sans-serif; }}
  </style>
</head>
<body>
  <h1>Email PDF Export</h1>
  <table>{rows}</table>
  <pre>{safe_body}</pre>
</body>
</html>"""


def output_pdf_name(index: int, eml_path: Path, eml_root: Path) -> str:
    rel = eml_path.relative_to(eml_root).as_posix()
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", eml_path.stem)[:80] or "email"
    return f"{index:08d}_{stem}_{digest}.pdf"


def convert_one(index: int, eml_path: Path, eml_root: Path, pdf_dir: Path, source_pst: Path, pst_sha256: str) -> dict[str, str]:
    with eml_path.open("rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle)

    attachments = attachment_filenames(message)
    pdf_path = pdf_dir / output_pdf_name(index, eml_path, eml_root)

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
    body = message_body_text(message)

    HTML(string=pdf_html(metadata, body), base_url=str(pdf_dir), url_fetcher=block_external_fetches).write_pdf(pdf_path)

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
        "attachment_filenames": "|".join(attachments),
        "status": "ok",
        "error": "",
    }


def failed_row(source_pst: Path, pst_sha256: str, eml_path: Path, error: str) -> dict[str, str]:
    return {
        "source_pst_path": str(source_pst),
        "source_pst_sha256": pst_sha256,
        "eml_path": str(eml_path),
        "pdf_path": "",
        "subject": "",
        "from": "",
        "to": "",
        "cc": "",
        "bcc": "",
        "date": "",
        "message_id": "",
        "attachment_filenames": "",
        "status": "error",
        "error": error,
    }


def convert_worker(
    queue: mp.Queue,
    index: int,
    eml_path: str,
    eml_root: str,
    pdf_dir: str,
    source_pst: str,
    pst_sha256: str,
) -> None:
    path = Path(eml_path)
    pst = Path(source_pst)
    try:
        row = convert_one(index, path, Path(eml_root), Path(pdf_dir), pst, pst_sha256)
    except Exception as exc:  # noqa: BLE001 - error is recorded in manifest
        row = failed_row(pst, pst_sha256, path, f"{type(exc).__name__}: {exc}")
    queue.put(row)


def convert_with_timeout(
    index: int,
    eml_path: Path,
    eml_root: Path,
    pdf_dir: Path,
    source_pst: Path,
    pst_sha256: str,
    timeout_seconds: int,
) -> dict[str, str]:
    if timeout_seconds <= 0:
        try:
            return convert_one(index, eml_path, eml_root, pdf_dir, source_pst, pst_sha256)
        except Exception as exc:  # noqa: BLE001 - error is recorded in manifest
            return failed_row(source_pst, pst_sha256, eml_path, f"{type(exc).__name__}: {exc}")

    context = mp.get_context("fork")
    queue: mp.Queue = context.Queue(maxsize=1)
    process = context.Process(
        target=convert_worker,
        args=(queue, index, str(eml_path), str(eml_root), str(pdf_dir), str(source_pst), pst_sha256),
    )
    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()
        return failed_row(source_pst, pst_sha256, eml_path, f"Timeout after {timeout_seconds} seconds")

    if process.exitcode != 0 and queue.empty():
        return failed_row(source_pst, pst_sha256, eml_path, f"Worker exited with code {process.exitcode}")

    if queue.empty():
        return failed_row(source_pst, pst_sha256, eml_path, "Worker exited without returning a result")

    return queue.get()


def load_existing_manifest_rows(manifest: Path) -> set[str]:
    if not manifest.exists():
        return set()
    with manifest.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        return {row["eml_path"] for row in reader if row.get("eml_path")}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert local EML files to PDFs and a manifest CSV.")
    parser.add_argument("--source-pst", required=True, type=Path)
    parser.add_argument("--eml-dir", required=True, type=Path)
    parser.add_argument("--pdf-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--log-file", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="Allow writing into existing non-empty PDF/manifest locations.")
    parser.add_argument("--resume", action="store_true", help="Append to an existing manifest and skip EML paths already listed there.")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Per-message conversion timeout. Use 0 to disable.")
    return parser.parse_args()


def ensure_safe_outputs(pdf_dir: Path, manifest: Path, force: bool, resume: bool) -> None:
    if resume:
        return
    if pdf_dir.exists() and any(pdf_dir.iterdir()) and not force:
        raise SystemExit(f"PDF output directory is not empty: {pdf_dir}. Re-run with --force to allow writing into it.")
    if manifest.exists() and not force:
        raise SystemExit(f"Manifest already exists: {manifest}. Re-run with --force to replace it.")


def main() -> int:
    args = parse_args()
    if not args.source_pst.is_file():
        raise SystemExit(f"Source PST not found: {args.source_pst}")
    if not args.eml_dir.is_dir():
        raise SystemExit(f"EML directory not found: {args.eml_dir}")

    ensure_safe_outputs(args.pdf_dir, args.manifest, args.force, args.resume)
    args.pdf_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=args.log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("Starting conversion. Source PST=%s EML dir=%s PDF dir=%s", args.source_pst, args.eml_dir, args.pdf_dir)

    pst_sha256 = sha256_file(args.source_pst)
    processed_paths = load_existing_manifest_rows(args.manifest) if args.resume else set()
    converted = 0
    failed = 0
    skipped = 0

    manifest_exists = args.manifest.exists()
    manifest_mode = "a" if args.resume and manifest_exists else "w"
    with args.manifest.open(manifest_mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=MANIFEST_FIELDS)
        if manifest_mode == "w":
            writer.writeheader()
        for index, eml_path in enumerate(iter_eml_files(args.eml_dir), start=1):
            if str(eml_path) in processed_paths:
                skipped += 1
                continue

            logging.info("Converting index=%s eml_path=%s", index, eml_path)
            row = convert_with_timeout(
                index,
                eml_path,
                args.eml_dir,
                args.pdf_dir,
                args.source_pst,
                pst_sha256,
                args.timeout_seconds,
            )
            if row["status"] == "ok":
                converted += 1
            else:
                failed += 1
                logging.error("Failed to convert EML path=%s error=%s", eml_path, row["error"])
            writer.writerow(row)
            csvfile.flush()

    logging.info("Finished conversion. converted=%s failed=%s skipped=%s", converted, failed, skipped)
    print(f"Conversion finished. converted={converted} failed={failed} skipped={skipped} manifest={args.manifest}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

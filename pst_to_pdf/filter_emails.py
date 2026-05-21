"""Email filtering by participant headers.

Owns parsing, normalization, fingerprinting, and matching for the optional
email-participant filter feature. No body content is ever inspected here.
"""

from __future__ import annotations

import hashlib
from email.message import Message
from email.utils import getaddresses
from pathlib import Path


FILTER_HEADERS: tuple[str, ...] = (
    "From",
    "To",
    "Cc",
    "Bcc",
    "Reply-To",
    "Sender",
)


def normalize_email(raw: str) -> str | None:
    """Lowercase + strip. Return None if the value doesn't look like an email."""
    if not raw:
        return None
    value = raw.strip().lower()
    if "@" not in value:
        return None
    local, _, domain = value.partition("@")
    if not local or not domain:
        return None
    return value


def parse_email_list(raw: str) -> list[str]:
    """Split raw input on commas and newlines, normalize, dedupe (first-seen order)."""
    if not raw:
        return []
    pieces: list[str] = []
    for line in raw.splitlines():
        for part in line.split(","):
            pieces.append(part)
    out: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        normalized = normalize_email(piece)
        if normalized is None:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def load_filter_file(path: Path) -> list[str]:
    """Read a filter file: one email per line; blank lines and `#` comments ignored."""
    raw = path.read_text(encoding="utf-8")
    out: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = normalize_email(stripped)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def write_filter_file(path: Path, emails: list[str]) -> None:
    """Write one normalized email per line. Creates parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(emails) + ("\n" if emails else ""), encoding="utf-8")


def filter_fingerprint(emails: list[str]) -> str:
    """Stable sha256 of the sorted, deduped, lowercased filter set.

    Order, casing, and duplicates in the input do not affect the output.
    """
    normalized = sorted({n for n in (normalize_email(e) for e in emails) if n is not None})
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()
    return digest


def extract_participant_addresses(message: Message) -> set[str]:
    """Return the set of normalized email addresses found in participant headers.

    Reads only the six headers in `FILTER_HEADERS`. Display-name formats,
    multi-address headers, and repeated headers are all handled by
    `email.utils.getaddresses`.
    """
    addresses: set[str] = set()
    for header in FILTER_HEADERS:
        values = message.get_all(header) or []
        try:
            pairs = getaddresses(values)
        except Exception:  # noqa: BLE001 - malformed header => skip this header
            continue
        for _name, addr in pairs:
            if not addr:
                continue
            addr_norm = addr.strip().lower()
            if "@" not in addr_norm:
                continue
            addresses.add(addr_norm)
    return addresses


def message_matches(message: Message, filter_set: frozenset[str]) -> bool:
    """True iff the message has any participant address in `filter_set`."""
    if not filter_set:
        return False
    return bool(extract_participant_addresses(message) & filter_set)

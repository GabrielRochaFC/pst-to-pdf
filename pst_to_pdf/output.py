"""Small terminal formatting helpers for human-readable CLI output."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


RULE = "-" * 40

# ANSI codes — only emitted when colors are on
_RESET = "\033[0m"
_BOLD_CYAN = "\033[1;36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"

_color_override: bool | None = None  # None = auto-detect from TTY + NO_COLOR


def set_color(enabled: bool) -> None:
    """Override automatic TTY / NO_COLOR detection for this process."""
    global _color_override
    _color_override = enabled


def _colors_on() -> bool:
    if _color_override is not None:
        return _color_override
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _colors_on() else text


def green(text: str) -> str:
    return _c(_GREEN, text)


def yellow(text: str) -> str:
    return _c(_YELLOW, text)


def red(text: str) -> str:
    return _c(_RED, text)


def bold(text: str) -> str:
    return _c(_BOLD, text)


def format_number(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}"


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def format_path(path: str | Path) -> str:
    return str(path)


def format_bytes(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:,.1f} PB"


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def print_section(title: str) -> None:
    print()
    print(_c(_BOLD_CYAN, title))
    print(RULE)


def print_kv(label: str, value: Any) -> None:
    print(f"{label:<29}: {value}")


def print_path_block(title: str, path: str | Path) -> None:
    print()
    print(f"{title}:")
    print(f"  {format_path(path)}")


def print_issues(issues: list[str]) -> None:
    if not issues:
        return
    print()
    print("Issues:")
    for issue in issues:
        print(f"- {issue}")


# ---------------------------------------------------------------------------
# Dynamic single-line progress helpers
# ---------------------------------------------------------------------------

_CLEAR_LINE = "\r\033[K"  # carriage return + erase to end of line


def write_dynamic_line(text: str) -> None:
    """Write a status line that overwrites itself on TTY.

    On non-TTY stdout the text is printed as a normal line so it appears in
    piped / logged output without ANSI escape codes.
    """
    if sys.stdout.isatty():
        print(f"{_CLEAR_LINE}{text}", end="", flush=True)
    else:
        print(text, flush=True)


def finish_dynamic_line() -> None:
    """End the dynamic-line section with a newline (TTY only)."""
    if sys.stdout.isatty():
        print(flush=True)

"""Small terminal formatting helpers for human-readable CLI output."""

from __future__ import annotations

from pathlib import Path
from typing import Any


RULE = "-" * 40


def format_number(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}"


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def format_path(path: str | Path) -> str:
    return str(path)


def print_section(title: str) -> None:
    print()
    print(title)
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

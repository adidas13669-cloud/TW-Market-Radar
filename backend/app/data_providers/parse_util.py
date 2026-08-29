"""Shared JSON table helpers. Never coerce '--' / blank to zero."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import ProviderParseError
from app.data_providers.dates import parse_number


def normalize_field_name(name: object) -> str:
    return str(name).replace("<br>", " ").replace("<BR>", " ").replace("&nbsp;", " ").strip()


def field_map(fields: list[Any], raw: list[Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for i, field in enumerate(fields):
        key = normalize_field_name(field)
        mapped[key] = raw[i] if i < len(raw) else None
    return mapped


def pick(row: dict[str, Any], *names: str) -> Any:
    normalized = {normalize_field_name(k): v for k, v in row.items()}
    for name in names:
        key = normalize_field_name(name)
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    for key, value in normalized.items():
        for name in names:
            if normalize_field_name(name) in key and value not in (None, ""):
                return value
    return None


def safe_num(value: object) -> float | None:
    try:
        return parse_number(value)
    except ValueError as exc:
        raise ProviderParseError(str(exc)) from exc


def strip_code(value: object) -> str:
    return str(value).strip()


def sum_present(*parts: float | None) -> float | None:
    present = [p for p in parts if p is not None]
    if not present:
        return None
    return float(sum(present))

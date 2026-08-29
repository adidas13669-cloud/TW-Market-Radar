from datetime import date


def to_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def to_roc_slash(value: date) -> str:
    return f"{value.year - 1911}/{value.month:02d}/{value.day:02d}"


def parse_number(value: object) -> float | None:
    """Parse TWSE/TPEx numeric fields. Empty / '--' -> None, never coerced to 0."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("+", "")
    if text == "" or text in {"--", "---", "null", "None", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Unparseable numeric field: {value!r}") from exc

from pathlib import Path

import pandas as pd

from app.data_providers.base import ThemeMappingRecord
from app.data_providers.tpex import TpexProvider
from app.data_providers.twse import TwseProvider


def load_theme_mapping_csv(path: str | Path) -> list[ThemeMappingRecord]:
    frame = pd.read_csv(path, dtype=str)
    required = {"security_id", "theme_id"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"theme mapping CSV missing columns: {sorted(missing)}")
    records: list[ThemeMappingRecord] = []
    for _, row in frame.iterrows():
        theme_name = None
        if "theme_name" in frame.columns and pd.notna(row.get("theme_name")):
            theme_name = str(row["theme_name"]).strip()
        records.append(
            ThemeMappingRecord(
                security_id=str(row["security_id"]).strip(),
                theme_id=str(row["theme_id"]).strip(),
                theme_name=theme_name,
            )
        )
    return records


def default_providers() -> dict[str, object]:
    return {"TWSE": TwseProvider(), "TPEX": TpexProvider()}

"""Load versioned taxonomy from catalog + optional on-disk CSV mirror."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from app.taxonomy.flatten import MemberDef, ThemeDef, expand_membership, flatten_themes

CURRENT_MAPPING_VERSION = "v2-tax-1"
TAXONOMY_DIR = Path("data/theme_mapping/v2")


@dataclass(frozen=True)
class TaxonomyBundle:
    mapping_version: str
    mapping_source: str
    effective_from: date
    effective_to: date | None
    production_ready: bool
    notes: str
    themes: list[ThemeDef]
    members: list[MemberDef]


def default_meta() -> dict:
    return {
        "mapping_version": CURRENT_MAPPING_VERSION,
        "mapping_source": str(TAXONOMY_DIR),
        "effective_from": "2026-06-01",
        "effective_to": None,
        "production_ready": False,
        "notes": (
            "Hierarchical Taiwan equity taxonomy (L1 industry / L2 supply chain / "
            "L3 investment theme). Many-to-many membership. Not an official TWSE/TPEx file."
        ),
    }


def load_taxonomy_bundle(path: Path | None = None) -> TaxonomyBundle:
    directory = path or TAXONOMY_DIR
    meta = default_meta()
    meta_path = directory / "mapping_meta.json" if directory.is_dir() else directory.with_name("mapping_meta.json")
    if path is not None and path.is_file() and path.suffix == ".json":
        meta_path = path
    if meta_path.exists():
        meta = {**meta, **json.loads(meta_path.read_text(encoding="utf-8"))}
    themes = flatten_themes()
    members = expand_membership(themes)
    csv_themes = directory / "themes.csv" if directory.is_dir() else None
    csv_members = directory / "membership.csv" if directory.is_dir() else None
    if csv_themes and csv_themes.exists():
        themes = _themes_from_csv(csv_themes)
    if csv_members and csv_members.exists():
        members = _members_from_csv(csv_members)
    effective_to = meta.get("effective_to")
    return TaxonomyBundle(
        mapping_version=str(meta.get("mapping_version") or CURRENT_MAPPING_VERSION),
        mapping_source=str(meta.get("mapping_source") or directory),
        effective_from=date.fromisoformat(str(meta.get("effective_from") or "2026-06-01")),
        effective_to=date.fromisoformat(str(effective_to)) if effective_to else None,
        production_ready=bool(meta.get("production_ready")),
        notes=str(meta.get("notes") or ""),
        themes=themes,
        members=members,
    )


def mapping_effective_on(asof: date, *, effective_from: date, effective_to: date | None) -> bool:
    if asof < effective_from:
        return False
    if effective_to is not None and asof > effective_to:
        return False
    return True


def bundle_to_frames(bundle: TaxonomyBundle) -> tuple[pd.DataFrame, pd.DataFrame]:
    themes = pd.DataFrame(
        [
            {
                "theme_id": t.theme_id,
                "name": t.name,
                "theme_name": t.name,
                "theme_level": t.theme_level,
                "parent_theme_id": t.parent_theme_id,
                "theme_category": t.theme_category,
                "concentrated_ok": t.concentrated_ok,
            }
            for t in bundle.themes
        ]
    )
    mapping = pd.DataFrame(
        [
            {
                "security_id": m.security_id,
                "theme_id": m.theme_id,
                "confidence": m.confidence,
                "rationale": m.rationale,
                "source": m.source,
                "inherited": m.inherited,
            }
            for m in bundle.members
        ]
    )
    return themes, mapping


def _themes_from_csv(path: Path) -> list[ThemeDef]:
    frame = pd.read_csv(path, dtype=str)
    rows: list[ThemeDef] = []
    for _, row in frame.iterrows():
        parent = row.get("parent_theme_id")
        parent_s = None if parent is None or str(parent) in {"", "nan", "None"} else str(parent)
        concentrated = str(row.get("concentrated_ok", "")).strip().lower() in {"1", "true", "yes"}
        rows.append(
            ThemeDef(
                theme_id=str(row["theme_id"]).strip(),
                name=str(row["name"]).strip(),
                theme_level=int(row["theme_level"]),
                parent_theme_id=parent_s,
                theme_category=str(row.get("theme_category") or "other"),
                concentrated_ok=concentrated,
            )
        )
    return rows


def _members_from_csv(path: Path) -> list[MemberDef]:
    frame = pd.read_csv(path, dtype=str)
    rows: list[MemberDef] = []
    for _, row in frame.iterrows():
        rows.append(
            MemberDef(
                security_id=str(row["security_id"]).strip(),
                theme_id=str(row["theme_id"]).strip(),
                confidence=float(row.get("confidence") or 0.75),
                rationale=str(row.get("rationale") or ""),
                source=str(row.get("source") or ""),
                inherited=str(row.get("inherited", "")).strip().lower() in {"1", "true", "yes"},
            )
        )
    return rows

"""Flatten nested theme tree and roll membership up the hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.taxonomy.coverage import COVERAGE_SOURCE, coverage_assignments
from app.taxonomy.v2_catalog import CONCENTRATED_CONFIDENCE, DEFAULT_CONFIDENCE, MEMBERS, SOURCE, TREE


@dataclass(frozen=True)
class ThemeDef:
    theme_id: str
    name: str
    theme_level: int
    parent_theme_id: str | None
    theme_category: str
    concentrated_ok: bool


@dataclass(frozen=True)
class MemberDef:
    security_id: str
    theme_id: str
    confidence: float
    rationale: str
    source: str
    inherited: bool = False


def flatten_themes(tree: dict | None = None) -> list[ThemeDef]:
    tree = tree if tree is not None else TREE
    out: list[ThemeDef] = []

    def walk(nodes: dict, parent_id: str | None, level: int, category: str) -> None:
        for theme_id, spec in nodes.items():
            cat = str(spec.get("category") or category)
            concentrated = bool(spec.get("concentrated", False))
            out.append(
                ThemeDef(
                    theme_id=theme_id,
                    name=str(spec["name"]),
                    theme_level=level,
                    parent_theme_id=parent_id,
                    theme_category=cat,
                    concentrated_ok=concentrated,
                )
            )
            children = spec.get("children") or {}
            if children:
                walk(children, theme_id, level + 1, cat)

    walk(tree, None, 1, "other")
    return out


def _parents(theme_id: str, by_id: dict[str, ThemeDef]) -> list[str]:
    chain: list[str] = []
    current = by_id[theme_id].parent_theme_id
    while current:
        chain.append(current)
        current = by_id[current].parent_theme_id
    return chain


def _append_chain(
    *,
    rows: list[MemberDef],
    seen: set[tuple[str, str]],
    by_id: dict[str, ThemeDef],
    theme_id: str,
    security_id: str,
    confidence: float,
    rationale: str,
    source: str,
) -> None:
    if theme_id not in by_id:
        raise ValueError(f"membership references unknown theme {theme_id}")
    theme = by_id[theme_id]
    targets = [theme_id, *_parents(theme_id, by_id)]
    for idx, tid in enumerate(targets):
        key = (security_id, tid)
        if key in seen:
            continue
        seen.add(key)
        inherited = idx > 0
        rows.append(
            MemberDef(
                security_id=security_id,
                theme_id=tid,
                confidence=confidence,
                rationale=(f"inherited from {theme_id}" if inherited else rationale),
                source=source,
                inherited=inherited,
            )
        )


def expand_membership(
    themes: list[ThemeDef] | None = None,
    members: dict[str, tuple[str, ...]] | None = None,
    universe: list[tuple[str, str]] | None = None,
    include_coverage: bool = True,
) -> list[MemberDef]:
    themes = themes if themes is not None else flatten_themes()
    members = members if members is not None else MEMBERS
    by_id = {t.theme_id: t for t in themes}
    rows: list[MemberDef] = []
    seen: set[tuple[str, str]] = set()
    curated_ids: set[str] = set()
    for theme_id, tickers in members.items():
        theme = by_id[theme_id] if theme_id in by_id else None
        conf = CONCENTRATED_CONFIDENCE if theme and theme.concentrated_ok else DEFAULT_CONFIDENCE
        primary = f"primary mapping to {theme_id} ({theme.name})" if theme else f"primary mapping to {theme_id}"
        for sid in tickers:
            sid = str(sid).strip()
            curated_ids.add(sid)
            _append_chain(
                rows=rows,
                seen=seen,
                by_id=by_id,
                theme_id=theme_id,
                security_id=sid,
                confidence=conf,
                rationale=primary,
                source=SOURCE,
            )
    if include_coverage:
        extra = coverage_assignments(curated_ids, universe=universe)
        for theme_id, assignments in extra.items():
            if theme_id not in by_id:
                continue
            for sid, rationale, conf in assignments:
                _append_chain(
                    rows=rows,
                    seen=seen,
                    by_id=by_id,
                    theme_id=theme_id,
                    security_id=sid,
                    confidence=conf,
                    rationale=rationale,
                    source=COVERAGE_SOURCE,
                )
    return rows


def theme_index() -> dict[str, ThemeDef]:
    return {t.theme_id: t for t in flatten_themes()}

"""Taxonomy structural validation. Offline; optional universe of known tickers."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.taxonomy.flatten import MemberDef, ThemeDef
from app.taxonomy.loader import TaxonomyBundle


@dataclass
class TaxonomyReport:
    theme_count: int = 0
    l1: int = 0
    l2: int = 0
    l3: int = 0
    mapped_securities: int = 0
    issues: list[str] = field(default_factory=list)
    below_min_members: list[str] = field(default_factory=list)
    concentrated_exceptions: list[str] = field(default_factory=list)
    duplicate_pairs: list[tuple[str, str]] = field(default_factory=list)
    invalid_tickers: list[str] = field(default_factory=list)
    unknown_parents: list[str] = field(default_factory=list)
    level_mismatch: list[str] = field(default_factory=list)
    member_counts: dict[str, int] = field(default_factory=dict)
    multi_theme_histogram: dict[int, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_taxonomy(
    bundle: TaxonomyBundle,
    *,
    known_tickers: set[str] | None = None,
    min_members: int | None = None,
) -> TaxonomyReport:
    settings = get_settings()
    min_n = min_members if min_members is not None else settings.min_theme_members
    report = TaxonomyReport()
    themes = bundle.themes
    members = bundle.members
    report.theme_count = len(themes)
    report.l1 = sum(1 for t in themes if t.theme_level == 1)
    report.l2 = sum(1 for t in themes if t.theme_level == 2)
    report.l3 = sum(1 for t in themes if t.theme_level == 3)

    by_id = {t.theme_id: t for t in themes}
    if len(by_id) != len(themes):
        report.issues.append("duplicate theme_id in catalog")

    for t in themes:
        if t.theme_level not in {1, 2, 3}:
            report.issues.append(f"{t.theme_id} has invalid theme_level {t.theme_level}")
        if t.theme_level == 1 and t.parent_theme_id:
            report.issues.append(f"L1 {t.theme_id} must not have parent")
        if t.theme_level > 1:
            if not t.parent_theme_id:
                report.unknown_parents.append(t.theme_id)
                report.issues.append(f"{t.theme_id} missing parent_theme_id")
            elif t.parent_theme_id not in by_id:
                report.unknown_parents.append(t.theme_id)
                report.issues.append(f"{t.theme_id} parent {t.parent_theme_id} does not exist")
            else:
                parent = by_id[t.parent_theme_id]
                if t.theme_level != parent.theme_level + 1:
                    report.level_mismatch.append(t.theme_id)
                    report.issues.append(
                        f"{t.theme_id} level {t.theme_level} inconsistent with parent {parent.theme_id} level {parent.theme_level}"
                    )

    pair_counts = Counter((m.security_id, m.theme_id) for m in members)
    for pair, n in pair_counts.items():
        if n > 1:
            report.duplicate_pairs.append(pair)
            report.issues.append(f"duplicate membership {pair[0]}->{pair[1]} x{n}")

    counts: dict[str, set[str]] = defaultdict(set)
    per_stock: dict[str, set[str]] = defaultdict(set)
    for m in members:
        if m.theme_id not in by_id:
            report.issues.append(f"member {m.security_id} maps to unknown theme {m.theme_id}")
            continue
        counts[m.theme_id].add(m.security_id)
        per_stock[m.security_id].add(m.theme_id)

    report.mapped_securities = len(per_stock)
    report.member_counts = {k: len(v) for k, v in sorted(counts.items())}
    histo: dict[int, int] = defaultdict(int)
    for themes_for_stock in per_stock.values():
        histo[len(themes_for_stock)] += 1
    report.multi_theme_histogram = dict(sorted(histo.items()))

    for t in themes:
        n = report.member_counts.get(t.theme_id, 0)
        if n < min_n:
            if t.concentrated_ok:
                report.concentrated_exceptions.append(t.theme_id)
            else:
                report.below_min_members.append(t.theme_id)

    if known_tickers is not None:
        report.invalid_tickers = sorted(sid for sid in per_stock if sid not in known_tickers)
    return report

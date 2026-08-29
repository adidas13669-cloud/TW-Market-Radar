"""Offline-friendly audit of ingested SQLite snapshots."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    DailyInstitutionalFlow,
    DailyMargin,
    DailyQuote,
    IngestRun,
    MappingCatalog,
    SectorDailyMetric,
    Security,
    SecurityTheme,
    StockDailyMetric,
    Theme,
)
from app.core.securities import is_common_stock
from app.services.invariants import validate_sector_invariants
from app.services.persistence import current_mapping_version
from app.services.ranking_engine import rank_divergence, rank_emerging, rank_sectors
from app.taxonomy.loader import load_taxonomy_bundle
from app.taxonomy.validate import validate_taxonomy


def mapping_audit(session: Session, asof: date | None = None) -> dict:
    asof = asof or session.execute(select(func.max(DailyQuote.trade_date))).scalar()
    version = current_mapping_version(session, asof=asof)
    catalog = session.get(MappingCatalog, version) if version else None
    mapped = session.execute(select(SecurityTheme).where(SecurityTheme.mapping_version == version)).scalars().all() if version else session.execute(select(SecurityTheme)).scalars().all()
    mapped_ids = {m.security_id for m in mapped}
    quoted_any = set(session.execute(select(DailyQuote.security_id).distinct()).scalars().all())
    invalid = sorted(sid for sid in mapped_ids if sid not in quoted_any)

    quoted = set()
    if asof is not None:
        quoted = set(
            session.execute(select(DailyQuote.security_id).where(DailyQuote.trade_date == asof)).scalars().all()
        )
    missing_latest = sorted(sid for sid in mapped_ids if sid not in quoted)
    unmapped = sorted(sid for sid in quoted if sid not in mapped_ids)
    common_quoted = {sid for sid in quoted if is_common_stock(sid)}
    common_mapped = {sid for sid in mapped_ids if sid in common_quoted}
    coverage_pct = (len(common_mapped) / len(common_quoted) * 100.0) if common_quoted else None
    multi: dict[str, list[str]] = {}
    for link in mapped:
        multi.setdefault(link.security_id, []).append(link.theme_id)
    multi_theme = {k: sorted(v) for k, v in multi.items() if len(v) > 1}
    histo: dict[int, int] = {}
    for themes in multi.values():
        histo[len(themes)] = histo.get(len(themes), 0) + 1

    return {
        "mapping_version": catalog.mapping_version if catalog else version,
        "mapping_source": catalog.mapping_source if catalog else None,
        "effective_from": catalog.effective_from.isoformat() if catalog and catalog.effective_from else None,
        "effective_to": catalog.effective_to.isoformat() if catalog and catalog.effective_to else None,
        "production_ready": catalog.production_ready if catalog else False,
        "mapped_tickers": len(mapped_ids),
        "mapped_common_stocks_on_asof": len(common_mapped),
        "common_stocks_quoted_on_asof": len(common_quoted),
        "common_stock_coverage_pct": round(coverage_pct, 2) if coverage_pct is not None else None,
        "invalid_tickers": invalid,
        "delisted_or_missing_on_asof": missing_latest,
        "unmapped_securities_on_asof": len(unmapped),
        "unmapped_sample": unmapped[:25],
        "multi_theme_histogram": dict(sorted(histo.items())),
        "multi_theme_sample": dict(list(multi_theme.items())[:15]),
        "asof": asof.isoformat() if asof else None,
        "note": catalog.notes if catalog else None,
    }


def build_audit_report(session: Session, asof: date | None = None) -> dict:
    dates = sorted(session.execute(select(DailyQuote.trade_date).distinct()).scalars().all())
    asof = asof or (dates[-1] if dates else None)
    twse_n = session.execute(select(func.count()).select_from(Security).where(Security.market == "TWSE")).scalar() or 0
    tpex_n = session.execute(select(func.count()).select_from(Security).where(Security.market == "TPEX")).scalar() or 0
    flow_q = select(DailyInstitutionalFlow).where(DailyInstitutionalFlow.trade_date == asof) if asof else select(DailyInstitutionalFlow)
    flows = session.execute(flow_q).scalars().all()
    estimated = sum(1 for f in flows if f.amount_estimated)
    actual = sum(1 for f in flows if f.flow_unit == "twd_notional" and not f.amount_estimated)
    missing_close = 0
    if asof:
        quotes = {
            q.security_id: q
            for q in session.execute(select(DailyQuote).where(DailyQuote.trade_date == asof)).scalars()
        }
        for f in flows:
            if f.raw_net_shares is not None and (f.estimated_net_amount is None) and quotes.get(f.security_id) and quotes[f.security_id].close is None:
                missing_close += 1
            elif f.raw_net_shares is not None and f.estimated_net_amount is None:
                q = quotes.get(f.security_id)
                if q is None or q.close is None:
                    missing_close += 1

    metrics = []
    version = current_mapping_version(session, asof=asof)
    if asof:
        mq = select(SectorDailyMetric).where(SectorDailyMetric.trade_date == asof)
        if version:
            mq = mq.where(SectorDailyMetric.mapping_version == version)
        metrics = session.execute(mq).scalars().all()
    all_q = select(SectorDailyMetric)
    if version:
        all_q = all_q.where(SectorDailyMetric.mapping_version == version)
    all_metrics = session.execute(all_q).scalars().all()
    frame = _metrics_frame(all_metrics)
    theme_rows = session.execute(select(Theme)).scalars().all()
    theme_frame = pd.DataFrame(
        [
            {
                "theme_id": t.id,
                "theme_name": t.name,
                "theme_level": t.theme_level,
                "concentrated_ok": bool(t.concentrated_ok),
            }
            for t in theme_rows
        ]
    )
    if not frame.empty and not theme_frame.empty:
        frame = frame.merge(theme_frame, on="theme_id", how="left")
    complete_20 = 0
    if asof and not frame.empty:
        day = frame[frame["trade_date"].map(lambda d: pd.Timestamp(d).date() == asof)]
        complete_20 = int(day["avg_20d"].notna().sum())

    stock_n = 0
    if asof:
        stock_n = session.execute(
            select(func.count()).select_from(StockDailyMetric).where(StockDailyMetric.trade_date == asof)
        ).scalar() or 0

    quadrants = Counter(m.quadrant for m in metrics if m.quadrant)
    lifecycles = Counter(m.lifecycle for m in metrics if m.lifecycle)

    if not frame.empty:
        try:
            validate_sector_invariants(frame, session_count=len(dates))
            invariant_ok = True
            invariant_error = None
        except Exception as exc:
            invariant_ok = False
            invariant_error = str(exc)
    else:
        invariant_ok = True
        invariant_error = None

    top = rank_sectors(frame, asof=asof).head(20) if not frame.empty else pd.DataFrame()
    emerging = rank_emerging(frame, asof=asof).head(20) if not frame.empty else pd.DataFrame()
    div = rank_divergence(frame, asof=asof).head(20) if not frame.empty else pd.DataFrame()

    excluded = []
    if not frame.empty and asof is not None:
        day = frame[frame["trade_date"].map(lambda d: pd.Timestamp(d).date() == asof)]
        if "rank_excluded" in day.columns:
            excluded = day[day["rank_excluded"] == True]["theme_id"].tolist()  # noqa: E712
        elif "thin_membership" in day.columns:
            thin = day["thin_membership"] == True  # noqa: E712
            concentrated = day["concentrated_ok"] if "concentrated_ok" in day.columns else False
            low = day["low_coverage"] == True if "low_coverage" in day.columns else False  # noqa: E712
            excluded = day.loc[(thin & ~pd.Series(concentrated, index=day.index).fillna(False)) | low, "theme_id"].tolist()

    history_table = _history_table(frame, n_sessions=10)

    runs = session.execute(select(IngestRun).order_by(IngestRun.trade_date)).scalars().all()
    status_counts = Counter(r.status for r in runs)

    return {
        "asof": asof.isoformat() if asof else None,
        "sessions_available": len(dates),
        "session_range": [dates[0].isoformat(), dates[-1].isoformat()] if dates else None,
        "securities": {"TWSE": twse_n, "TPEX": tpex_n},
        "institutional_on_asof": {
            "rows": len(flows),
            "estimated_twd": estimated,
            "non_estimated_twd": actual,
            "missing_close_conversion_failures": missing_close,
        },
        "themes_calculated": len(metrics),
        "themes_with_complete_20d": complete_20,
        "stock_metrics_on_asof": stock_n,
        "quadrant_counts": dict(quadrants),
        "lifecycle_counts": dict(lifecycles),
        "top_rotation": _rows(top),
        "top_emerging": _rows(emerging),
        "top_divergence": _rows(div),
        "rank_excluded_themes": excluded,
        "taxonomy": _taxonomy_summary(session, asof),
        "invariants_ok": invariant_ok,
        "invariant_error": invariant_error,
        "mapping": mapping_audit(session, asof=asof),
        "ingest_status_counts": dict(status_counts),
        "history_last_10": history_table,
        "raw_counts": {
            "quotes": session.execute(select(func.count()).select_from(DailyQuote)).scalar(),
            "flows": session.execute(select(func.count()).select_from(DailyInstitutionalFlow)).scalar(),
            "margins": session.execute(select(func.count()).select_from(DailyMargin)).scalar(),
        },
    }


def _metrics_frame(rows: list[SectorDailyMetric]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "theme_id": r.theme_id,
                "trade_date": r.trade_date,
                "flow_5d": _f(r.flow_5d),
                "avg_5d": _f(r.avg_5d),
                "avg_20d": _f(r.avg_20d),
                "acceleration": _f(r.acceleration),
                "normalized_flow": _f(r.normalized_flow),
                "price_momentum": _f(r.price_momentum),
                "volume_expansion": _f(r.volume_expansion),
                "rotation_score": _f(r.rotation_score),
                "emerging_metric": _f(r.emerging_metric),
                "quadrant": r.quadrant,
                "lifecycle": r.lifecycle,
                "divergence_flag": r.divergence_flag,
                "low_coverage": r.low_coverage,
                "thin_membership": r.thin_membership,
                "rank_excluded": r.rank_excluded,
                "coverage_ratio": _f(r.coverage_ratio),
                "member_count": r.member_count,
                "mapping_version": r.mapping_version,
            }
            for r in rows
        ]
    )


def _history_table(frame: pd.DataFrame, n_sessions: int = 10) -> list[dict]:
    if frame.empty:
        return []
    dates = sorted(pd.to_datetime(frame["trade_date"]).dt.date.unique())[-n_sessions:]
    subset = frame[frame["trade_date"].map(lambda d: pd.Timestamp(d).date() in set(dates))]
    cols = [
        "trade_date",
        "theme_id",
        "flow_5d",
        "avg_5d",
        "avg_20d",
        "acceleration",
        "normalized_flow",
        "price_momentum",
        "rotation_score",
        "emerging_metric",
        "quadrant",
        "lifecycle",
    ]
    keep = [c for c in cols if c in subset.columns]
    out = subset[keep].sort_values(["trade_date", "theme_id"])
    records = []
    for rec in out.to_dict(orient="records"):
        if hasattr(rec.get("trade_date"), "isoformat"):
            rec["trade_date"] = rec["trade_date"].isoformat()
        records.append(rec)
    return records


def _rows(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    keep = [c for c in ("theme_id", "theme_name", "theme_level", "rotation_score", "emerging_metric", "acceleration", "quadrant", "low_coverage", "thin_membership", "member_count") if c in frame.columns]
    return json.loads(frame[keep].head(20).to_json(orient="records"))


def _taxonomy_summary(session: Session, asof: date | None) -> dict:
    quoted: set[str] = set()
    if asof is not None:
        quoted = set(session.execute(select(DailyQuote.security_id).where(DailyQuote.trade_date == asof)).scalars().all())
    bundle = load_taxonomy_bundle()
    report = validate_taxonomy(bundle, known_tickers=quoted or None)
    levels = session.execute(select(Theme.theme_level, func.count()).group_by(Theme.theme_level)).all()
    return {
        "theme_count": report.theme_count,
        "l1": report.l1,
        "l2": report.l2,
        "l3": report.l3,
        "db_level_counts": {str(k): int(v) for k, v in levels if k is not None},
        "mapped_securities": report.mapped_securities,
        "below_min_members": report.below_min_members,
        "concentrated_exceptions": report.concentrated_exceptions,
        "invalid_vs_asof_universe": report.invalid_tickers[:40],
        "multi_theme_histogram": report.multi_theme_histogram,
    }


def _f(value) -> float | None:
    if value is None:
        return None
    return float(value)


def write_audit(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def format_audit_report(report: dict) -> str:
    mapping = report.get("mapping") or {}
    lines = [
        f"as-of: {report.get('asof')}",
        f"1. sessions available: {report.get('sessions_available')} range={report.get('session_range')}",
        f"2. TWSE / TPEx securities ingested: {report.get('securities')}",
        f"3. institutional records with actual/estimated TWD: {report.get('institutional_on_asof')}",
        f"4. missing-close conversion failures: {(report.get('institutional_on_asof') or {}).get('missing_close_conversion_failures')}",
        f"5. themes calculated: {report.get('themes_calculated')}",
        f"6. themes with complete 20-session windows: {report.get('themes_with_complete_20d')}",
        f"7. stock metrics generated: {report.get('stock_metrics_on_asof')}",
        f"8. quadrant counts: {report.get('quadrant_counts')}",
        f"9. lifecycle counts: {report.get('lifecycle_counts')}",
        f"10. top Rotation Score sectors: {report.get('top_rotation')}",
        f"11. top Emerging Rotation sectors: {report.get('top_emerging')}",
        f"12. top divergence sectors: {report.get('top_divergence')}",
        f"invariants_ok: {report.get('invariants_ok')} {report.get('invariant_error') or ''}".rstrip(),
        f"ingest_status_counts: {report.get('ingest_status_counts')}",
        f"raw_counts: {report.get('raw_counts')}",
        f"mapping_version={mapping.get('mapping_version')} source={mapping.get('mapping_source')} "
        f"effective_from={mapping.get('effective_from')} production_ready={mapping.get('production_ready')}",
        f"invalid_tickers: {mapping.get('invalid_tickers')}",
        f"delisted_or_missing_on_asof: {mapping.get('delisted_or_missing_on_asof')}",
        f"unmapped_securities_on_asof: {mapping.get('unmapped_securities_on_asof')} sample={mapping.get('unmapped_sample')}",
        f"common_stock_coverage_pct: {mapping.get('common_stock_coverage_pct')}",
        f"multi_theme_histogram: {mapping.get('multi_theme_histogram')}",
        f"rank_excluded_themes: {report.get('rank_excluded_themes')}",
        f"taxonomy: {report.get('taxonomy')}",
        mapping.get("note") or "",
        "",
        "history (latest 10 sessions):",
        "date | theme | flow_5d | avg_5d | avg_20d | acceleration | normalized_flow | price_momentum | rotation_score | emerging_metric | quadrant | lifecycle",
    ]
    for row in report.get("history_last_10") or []:
        lines.append(
            " | ".join(
                str(row.get(k) if row.get(k) is not None else "")
                for k in (
                    "trade_date",
                    "theme_id",
                    "flow_5d",
                    "avg_5d",
                    "avg_20d",
                    "acceleration",
                    "normalized_flow",
                    "price_momentum",
                    "rotation_score",
                    "emerging_metric",
                    "quadrant",
                    "lifecycle",
                )
            )
        )
    return "\n".join(lines)

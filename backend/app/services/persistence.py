from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    DailyInstitutionalFlow,
    DailyMargin,
    DailyQuote,
    MappingCatalog,
    SectorDailyMetric,
    SecurityTheme,
    StockDailyMetric,
    Theme,
)
from app.services.pipeline import CalculationResult, MarketSnapshot, run_calculation
from app.taxonomy.loader import CURRENT_MAPPING_VERSION, mapping_effective_on


def current_mapping_version(session: Session, asof: date | None = None) -> str | None:
    rows = session.execute(select(MappingCatalog)).scalars().all()
    if not rows:
        versions = [v for v in session.execute(select(SecurityTheme.mapping_version).distinct()).scalars().all() if v]
        return versions[0] if versions else None
    if asof is None:
        asof = session.execute(select(func.max(DailyQuote.trade_date))).scalar()
    effective = [
        r
        for r in rows
        if asof is None or mapping_effective_on(asof, effective_from=r.effective_from, effective_to=r.effective_to)
    ]
    if not effective:
        effective = list(rows)
    effective.sort(key=lambda r: r.effective_from, reverse=True)
    return effective[0].mapping_version


def snapshot_from_db(session: Session, asof: date | None = None, mapping_version: str | None = None) -> MarketSnapshot:
    asof = asof or session.execute(select(func.max(DailyQuote.trade_date))).scalar()
    version = mapping_version or current_mapping_version(session, asof=asof)
    mapping_q = select(SecurityTheme)
    if version:
        mapping_q = mapping_q.where(SecurityTheme.mapping_version == version)
    mapping_rows = session.execute(mapping_q).scalars().all()
    if asof is not None:
        kept = []
        for r in mapping_rows:
            start = r.effective_from
            end = r.effective_to
            if start and asof < start:
                continue
            if end and asof > end:
                continue
            kept.append(r)
        mapping_rows = kept
    mapping = pd.DataFrame(
        [{"security_id": r.security_id, "theme_id": r.theme_id} for r in mapping_rows]
    )
    theme_rows = session.execute(select(Theme)).scalars().all()
    themes = pd.DataFrame(
        [
            {
                "theme_id": t.id,
                "name": t.name,
                "theme_name": t.name,
                "theme_level": t.theme_level,
                "parent_theme_id": t.parent_theme_id,
                "theme_category": t.theme_category,
                "concentrated_ok": bool(t.concentrated_ok),
            }
            for t in theme_rows
        ]
    )
    flows = pd.DataFrame(
        [
            {
                "security_id": r.security_id,
                "trade_date": r.trade_date,
                "foreign_net_amount": _f(r.foreign_net_amount),
                "investment_trust_net_amount": _f(r.investment_trust_net_amount),
                "dealer_net_amount": _f(r.dealer_net_amount),
                "foreign_net_shares": _f(r.foreign_net_shares),
                "investment_trust_net_shares": _f(r.investment_trust_net_shares),
                "dealer_net_shares": _f(r.dealer_net_shares),
                "source_unit": r.source_unit or "twd_notional",
                "flow_unit": r.flow_unit,
                "amount_estimated": r.amount_estimated,
            }
            for r in session.execute(select(DailyInstitutionalFlow)).scalars().all()
        ]
    )
    quotes = pd.DataFrame(
        [
            {
                "security_id": r.security_id,
                "trade_date": r.trade_date,
                "close": _f(r.close),
                "volume": _f(r.volume),
                "trading_value": _f(r.trading_value),
            }
            for r in session.execute(select(DailyQuote)).scalars().all()
        ]
    )
    margins = pd.DataFrame(
        [
            {
                "security_id": r.security_id,
                "trade_date": r.trade_date,
                "margin_buy_change": _f(r.margin_buy_change),
                "margin_buy_balance": _f(r.margin_buy_balance),
                "margin_buy_change_lots": _f(r.margin_buy_change_lots),
                "margin_notional_change": _f(r.margin_notional_change),
                "source_unit": r.source_unit or "lots",
            }
            for r in session.execute(select(DailyMargin)).scalars().all()
        ]
    )
    return MarketSnapshot(mapping=mapping, flows=flows, quotes=quotes, margins=margins, themes=themes)


def persist_calculation(session: Session, result: CalculationResult, mapping_version: str | None = None) -> None:
    version = mapping_version or CURRENT_MAPPING_VERSION
    session.execute(delete(SectorDailyMetric).where(SectorDailyMetric.mapping_version == version))
    session.execute(delete(SectorDailyMetric).where(SectorDailyMetric.mapping_version.is_(None)))
    session.execute(delete(StockDailyMetric))
    for _, row in result.sector_metrics.iterrows():
        session.add(
            SectorDailyMetric(
                theme_id=str(row["theme_id"]),
                trade_date=_date(row["trade_date"]),
                institutional_flow=_dec(row.get("institutional_flow")),
                flow_5d=_dec(row.get("flow_5d")),
                avg_5d=_dec(row.get("avg_5d")),
                avg_20d=_dec(row.get("avg_20d")),
                acceleration=_dec(row.get("acceleration")),
                trading_value=_dec(row.get("trading_value")),
                trading_value_avg_20d=_dec(row.get("trading_value_avg_20d")),
                normalized_flow=_dec(row.get("normalized_flow")),
                price_momentum=_dec(row.get("price_momentum")),
                volume_expansion=_dec(row.get("volume_expansion")),
                continuity=_dec(row.get("continuity")),
                margin_signal=_dec(row.get("margin_signal")),
                quadrant=_str_enum(row.get("quadrant")),
                lifecycle=_str_enum(row.get("lifecycle")),
                rotation_score=_dec(row.get("rotation_score")),
                emerging_metric=_dec(row.get("emerging_metric")),
                divergence_flag=bool(row.get("divergence_flag") is True or row.get("divergence_flag") == 1),
                member_count=_int(row.get("member_count")),
                priced_member_count=_int(row.get("priced_member_count")),
                flow_member_count=_int(row.get("flow_member_count")),
                coverage_ratio=_dec(row.get("coverage_ratio")),
                low_coverage=bool(row.get("low_coverage") is True or row.get("low_coverage") == 1),
                thin_membership=bool(row.get("thin_membership") is True or row.get("thin_membership") == 1),
                rank_excluded=bool(row.get("rank_excluded") is True or row.get("rank_excluded") == 1),
                mapping_version=version,
            )
        )
    for _, row in result.stock_metrics.iterrows():
        session.add(
            StockDailyMetric(
                security_id=str(row["security_id"]),
                trade_date=_date(row["trade_date"]),
                institutional_flow=_dec(row.get("institutional_flow")),
                flow_5d=_dec(row.get("flow_5d")),
                avg_5d=_dec(row.get("avg_5d")),
                avg_20d=_dec(row.get("avg_20d")),
                acceleration=_dec(row.get("acceleration")),
                trading_value_avg_20d=_dec(row.get("trading_value_avg_20d")),
                normalized_flow=_dec(row.get("normalized_flow")),
                price_momentum=_dec(row.get("price_momentum")),
                volume_expansion=_dec(row.get("volume_expansion")),
                continuity=_dec(row.get("continuity")),
                margin_signal=_dec(row.get("margin_signal")),
                rotation_score=_dec(row.get("rotation_score")),
                divergence_flag=bool(row.get("divergence_flag") is True or row.get("divergence_flag") == 1),
            )
        )
    session.flush()


def recompute(session: Session, asof: date | None = None, mapping_version: str | None = None) -> CalculationResult:
    version = mapping_version or current_mapping_version(session, asof=asof) or CURRENT_MAPPING_VERSION
    result = run_calculation(snapshot_from_db(session, asof=asof, mapping_version=version))
    persist_calculation(session, result, mapping_version=version)
    return result


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return Decimal(str(float(value)))


def _int(value: object) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return int(value)


def _date(value: object) -> date:
    ts = pd.Timestamp(value)
    return ts.date()


def _str_enum(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return str(value)

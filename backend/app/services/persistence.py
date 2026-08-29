from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    DailyInstitutionalFlow,
    DailyMargin,
    DailyQuote,
    SectorDailyMetric,
    SecurityTheme,
    StockDailyMetric,
    Theme,
)
from app.services.pipeline import CalculationResult, MarketSnapshot, run_calculation


def snapshot_from_db(session: Session) -> MarketSnapshot:
    mapping_rows = session.execute(select(SecurityTheme)).scalars().all()
    mapping = pd.DataFrame(
        [{"security_id": r.security_id, "theme_id": r.theme_id} for r in mapping_rows]
    )
    themes = pd.DataFrame(
        [{"theme_id": t.id, "name": t.name} for t in session.execute(select(Theme)).scalars().all()]
    )
    flows = pd.DataFrame(
        [
            {
                "security_id": r.security_id,
                "trade_date": r.trade_date,
                "foreign_net_amount": _f(r.foreign_net_amount),
                "investment_trust_net_amount": _f(r.investment_trust_net_amount),
                "dealer_net_amount": _f(r.dealer_net_amount),
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
            }
            for r in session.execute(select(DailyMargin)).scalars().all()
        ]
    )
    return MarketSnapshot(mapping=mapping, flows=flows, quotes=quotes, margins=margins, themes=themes)


def persist_calculation(session: Session, result: CalculationResult) -> None:
    session.execute(delete(SectorDailyMetric))
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


def recompute(session: Session) -> CalculationResult:
    result = run_calculation(snapshot_from_db(session))
    persist_calculation(session, result)
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

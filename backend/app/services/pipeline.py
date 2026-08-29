"""Compose mapping + flow + quotes + margin into scored sector/stock tables."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.core.config import ScoreWeights
from app.services.institutional_flow import add_institutional_flow_column, aggregate_sector_daily_flow
from app.services.ranking_engine import rank_divergence, rank_emerging, rank_sectors
from app.services.rotation_engine import (
    aggregate_sector_activity,
    aggregate_sector_margin,
    compute_entity_timeseries_metrics,
    equal_weight_index_return,
)
from app.services.scoring_engine import attach_emerging_metric, score_cross_section


@dataclass(frozen=True)
class MarketSnapshot:
    mapping: pd.DataFrame
    flows: pd.DataFrame
    quotes: pd.DataFrame
    margins: pd.DataFrame | None = None
    themes: pd.DataFrame | None = None


@dataclass(frozen=True)
class CalculationResult:
    stock_daily: pd.DataFrame
    sector_daily: pd.DataFrame
    stock_metrics: pd.DataFrame
    sector_metrics: pd.DataFrame


def run_calculation(
    snapshot: MarketSnapshot,
    weights: ScoreWeights | None = None,
    emerging_lag: int = 5,
) -> CalculationResult:
    weights = weights or ScoreWeights()
    stock_daily = add_institutional_flow_column(snapshot.flows)
    if snapshot.quotes is not None and not snapshot.quotes.empty:
        quote_cols = [c for c in ("open", "high", "low", "close", "volume", "trading_value") if c in snapshot.quotes.columns]
        stock_daily = stock_daily.merge(
            snapshot.quotes[["trade_date", "security_id", *quote_cols]],
            on=["trade_date", "security_id"],
            how="left",
        )
    if snapshot.margins is not None and not snapshot.margins.empty:
        mcols = [c for c in ("margin_buy_change", "margin_buy_balance") if c in snapshot.margins.columns]
        stock_daily = stock_daily.merge(
            snapshot.margins[["trade_date", "security_id", *mcols]],
            on=["trade_date", "security_id"],
            how="left",
        )

    stock_metrics = compute_entity_timeseries_metrics(stock_daily, "security_id")
    stock_metrics = score_cross_section(stock_metrics, weights=weights)
    stock_metrics = attach_emerging_metric(stock_metrics, entity_col="security_id", lag=emerging_lag)

    sector_flow = aggregate_sector_daily_flow(stock_daily, snapshot.mapping)
    activity = aggregate_sector_activity(
        snapshot.quotes if snapshot.quotes is not None else pd.DataFrame(),
        snapshot.mapping,
    )
    sector_daily = sector_flow.merge(activity, on=["trade_date", "theme_id"], how="left")
    momentum = equal_weight_index_return(
        snapshot.quotes if snapshot.quotes is not None else pd.DataFrame(),
        snapshot.mapping,
    )
    if not momentum.empty:
        sector_daily = sector_daily.merge(momentum, on=["trade_date", "theme_id"], how="left")

    if snapshot.margins is not None and not snapshot.margins.empty:
        sector_m = aggregate_sector_margin(snapshot.margins, snapshot.mapping)
        sector_daily = sector_daily.merge(sector_m, on=["trade_date", "theme_id"], how="left")

    sector_metrics = compute_entity_timeseries_metrics(sector_daily, "theme_id")
    sector_metrics = score_cross_section(sector_metrics, weights=weights)
    sector_metrics = attach_emerging_metric(sector_metrics, entity_col="theme_id", lag=emerging_lag)

    if snapshot.themes is not None and not snapshot.themes.empty:
        name_col = "name" if "name" in snapshot.themes.columns else "theme_name"
        themes = snapshot.themes.rename(columns={name_col: "theme_name"})
        keep = [c for c in ("theme_id", "theme_name") if c in themes.columns]
        if "theme_id" not in themes.columns and "id" in snapshot.themes.columns:
            themes = snapshot.themes.rename(columns={"id": "theme_id", "name": "theme_name"})
            keep = ["theme_id", "theme_name"]
        sector_metrics = sector_metrics.merge(themes[keep], on="theme_id", how="left")

    return CalculationResult(
        stock_daily=stock_daily,
        sector_daily=sector_daily,
        stock_metrics=stock_metrics,
        sector_metrics=sector_metrics,
    )


def radar_views(result: CalculationResult, asof=None) -> dict[str, pd.DataFrame]:
    return {
        "sectors": rank_sectors(result.sector_metrics, asof=asof),
        "emerging": rank_emerging(result.sector_metrics, asof=asof),
        "divergence": rank_divergence(result.sector_metrics, asof=asof),
    }

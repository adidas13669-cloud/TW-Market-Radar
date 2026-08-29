"""Sector/stock rolling metrics, quadrants, lifecycle, and divergence.

All functions are pure (pandas in, pandas/scalars out). Providers never run here.
"""

from __future__ import annotations

import math

import pandas as pd

from app.core.enums import Lifecycle, Quadrant

PRICE_STALE_THRESHOLD = 0.02
CROWDED_SCORE = 65.0
CONFIRMED_SCORE = 55.0
VOLUME_CROWD_THRESHOLD = 1.5
CONTINUITY_LOOKBACK = 10
MOMENTUM_LOOKBACK = 5
FLOW_SHORT = 5
FLOW_LONG = 20


def classify_quadrant(flow_5d: float | None, acceleration: float | None) -> Quadrant | None:
    """Four-quadrant state including zero boundaries.

    flow_5d > 0 and acceleration > 0  -> STRONG_INFLOW
    flow_5d > 0 and acceleration <= 0 -> SLOWING_INFLOW
    flow_5d <= 0 and acceleration > 0 -> IMPROVING_OUTFLOW
    flow_5d <= 0 and acceleration <= 0 -> ACCELERATING_OUTFLOW
    """
    if flow_5d is None or acceleration is None or _is_nan(flow_5d) or _is_nan(acceleration):
        return None
    if flow_5d > 0 and acceleration > 0:
        return Quadrant.STRONG_INFLOW
    if flow_5d > 0 and acceleration <= 0:
        return Quadrant.SLOWING_INFLOW
    if flow_5d <= 0 and acceleration > 0:
        return Quadrant.IMPROVING_OUTFLOW
    return Quadrant.ACCELERATING_OUTFLOW


def classify_lifecycle(
    quadrant: Quadrant | None,
    rotation_score: float | None,
    price_momentum: float | None,
    volume_expansion: float | None,
    acceleration: float | None,
) -> Lifecycle | None:
    """Rule-based lifecycle. Thresholds are documented in docs/formula_spec.md."""
    if quadrant is None:
        return None

    score = rotation_score if rotation_score is not None and not _is_nan(rotation_score) else None
    momentum = price_momentum if price_momentum is not None and not _is_nan(price_momentum) else None
    vol_exp = volume_expansion if volume_expansion is not None and not _is_nan(volume_expansion) else None
    acc = acceleration if acceleration is not None and not _is_nan(acceleration) else None

    if quadrant == Quadrant.ACCELERATING_OUTFLOW:
        return Lifecycle.EXIT

    crowded = (
        quadrant == Quadrant.SLOWING_INFLOW
        and score is not None
        and score >= CROWDED_SCORE
        and (vol_exp is None or vol_exp >= VOLUME_CROWD_THRESHOLD or (acc is not None and acc <= 0))
    )
    if crowded:
        return Lifecycle.CROWDED

    if (
        quadrant == Quadrant.STRONG_INFLOW
        and score is not None
        and score >= CONFIRMED_SCORE
        and momentum is not None
        and momentum > PRICE_STALE_THRESHOLD
    ):
        return Lifecycle.CONFIRMED

    if quadrant in {Quadrant.STRONG_INFLOW, Quadrant.IMPROVING_OUTFLOW}:
        return Lifecycle.EARLY

    if quadrant == Quadrant.SLOWING_INFLOW:
        if score is not None and score >= CONFIRMED_SCORE:
            return Lifecycle.CONFIRMED
        return Lifecycle.EXIT

    return Lifecycle.EXIT


def is_flow_price_divergence(
    acceleration: float | None,
    flow_5d: float | None,
    price_momentum: float | None,
    *,
    price_threshold: float = PRICE_STALE_THRESHOLD,
) -> bool:
    """True when institutional flow is accelerating and price has not moved much."""
    if acceleration is None or flow_5d is None or price_momentum is None:
        return False
    if _is_nan(acceleration) or _is_nan(flow_5d) or _is_nan(price_momentum):
        return False
    return acceleration > 0 and flow_5d > 0 and abs(price_momentum) <= price_threshold


def normalized_flow(flow_5d: float | None, trading_value_avg_20d: float | None) -> float | None:
    """flow_5d / 20d average trading value. None if denominator is missing or zero."""
    if flow_5d is None or trading_value_avg_20d is None:
        return None
    if _is_nan(flow_5d) or _is_nan(trading_value_avg_20d) or trading_value_avg_20d == 0:
        return None
    return float(flow_5d) / float(trading_value_avg_20d)


def window_flow_metrics(daily_flow: pd.Series, short: int = FLOW_SHORT, long: int = FLOW_LONG) -> pd.DataFrame:
    """Rolling flow_5d, avg_5d, avg_20d, acceleration. Incomplete windows are NA."""
    flow = pd.to_numeric(daily_flow, errors="coerce")
    flow_short = flow.rolling(short, min_periods=short).sum()
    avg_short = flow_short / short
    avg_long = flow.rolling(long, min_periods=long).mean()
    return pd.DataFrame(
        {
            "institutional_flow": flow,
            "flow_5d": flow_short,
            "avg_5d": avg_short,
            "avg_20d": avg_long,
            "acceleration": avg_short - avg_long,
        }
    )


def price_momentum_from_close(close: pd.Series, lookback: int = MOMENTUM_LOOKBACK) -> pd.Series:
    """close_t / close_{t-lookback} - 1. None when either close is missing or lookback close is 0."""
    c = pd.to_numeric(close, errors="coerce")
    lagged = c.shift(lookback)
    out = c / lagged - 1.0
    out = out.where(lagged.notna() & (lagged != 0) & c.notna())
    return out


def volume_expansion_ratio(volume: pd.Series, short: int = FLOW_SHORT, long: int = FLOW_LONG) -> pd.Series:
    avg_s = pd.to_numeric(volume, errors="coerce").rolling(short, min_periods=short).mean()
    avg_l = pd.to_numeric(volume, errors="coerce").rolling(long, min_periods=long).mean()
    ratio = avg_s / avg_l
    return ratio.where(avg_l.notna() & (avg_l != 0))


def buying_continuity(daily_flow: pd.Series, lookback: int = CONTINUITY_LOOKBACK) -> pd.Series:
    """0.6 * share of positive days + 0.4 * capped consecutive positive streak / lookback."""
    flow = pd.to_numeric(daily_flow, errors="coerce")
    positive = (flow > 0).astype(float)
    pos_share = positive.rolling(lookback, min_periods=lookback).mean()

    streak = _positive_streak(flow)
    streak_norm = (streak.clip(upper=lookback) / lookback).where(flow.notna())
    # Streak is defined even before lookback fills; require lookback for the blended metric.
    blended = 0.6 * pos_share + 0.4 * streak_norm
    return blended.where(pos_share.notna())


def margin_signal_series(
    margin_change: pd.Series,
    trading_value: pd.Series,
    short: int = FLOW_SHORT,
    long: int = FLOW_LONG,
) -> pd.Series:
    """Sum of short-window margin-balance change / 20d average trading value."""
    chg = pd.to_numeric(margin_change, errors="coerce")
    tv = pd.to_numeric(trading_value, errors="coerce")
    num = chg.rolling(short, min_periods=short).sum()
    den = tv.rolling(long, min_periods=long).mean()
    return (num / den).where(den.notna() & (den != 0) & num.notna())


def equal_weight_index_return(
    prices: pd.DataFrame,
    mapping: pd.DataFrame,
    lookback: int = MOMENTUM_LOOKBACK,
) -> pd.DataFrame:
    """Equal-weight average of member 5-session returns by theme/date.

    Stocks with missing closes are omitted from that theme's average (not filled).
    """
    if prices.empty or mapping.empty:
        return pd.DataFrame(columns=["trade_date", "theme_id", "price_momentum"])

    px = prices.sort_values(["security_id", "trade_date"]).copy()
    px["price_momentum"] = px.groupby("security_id", group_keys=False)["close"].transform(
        lambda s: price_momentum_from_close(s, lookback)
    )
    joined = mapping.merge(px[["trade_date", "security_id", "price_momentum"]], on="security_id", how="inner")
    out = (
        joined.dropna(subset=["price_momentum"])
        .groupby(["trade_date", "theme_id"], as_index=False)["price_momentum"]
        .mean()
    )
    return out


def aggregate_sector_activity(
    quotes: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    """Sum trading value and volume to theme/date. Multi-theme stocks are counted in each theme."""
    if quotes.empty or mapping.empty:
        return pd.DataFrame(columns=["trade_date", "theme_id", "trading_value", "volume"])
    joined = mapping.merge(
        quotes[["trade_date", "security_id", "trading_value", "volume"]],
        on="security_id",
        how="inner",
    )
    return joined.groupby(["trade_date", "theme_id"], as_index=False).agg(
        trading_value=("trading_value", "sum"),
        volume=("volume", "sum"),
    )


def aggregate_sector_margin(
    margins: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    if margins.empty or mapping.empty:
        return pd.DataFrame(columns=["trade_date", "theme_id", "margin_buy_change"])
    cols = ["trade_date", "security_id"]
    extra = [c for c in ("margin_buy_change",) if c in margins.columns]
    joined = mapping.merge(margins[cols + extra], on="security_id", how="inner")
    if "margin_buy_change" not in joined.columns:
        joined["margin_buy_change"] = pd.NA
    return joined.groupby(["trade_date", "theme_id"], as_index=False).agg(
        margin_buy_change=("margin_buy_change", "sum"),
    )


def compute_entity_timeseries_metrics(daily: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """Rolling metrics for each entity (theme_id or security_id).

    `daily` must include trade_date, entity_col, institutional_flow, and optionally
    trading_value, volume, close, margin_buy_change, price_momentum (precomputed).
    """
    if daily.empty:
        return daily.copy()

    frames: list[pd.DataFrame] = []
    for entity_id, grp in daily.sort_values("trade_date").groupby(entity_col, sort=False):
        g = grp.sort_values("trade_date").copy()
        flow_m = window_flow_metrics(g["institutional_flow"])
        for col in ("flow_5d", "avg_5d", "avg_20d", "acceleration"):
            g[col] = flow_m[col].values

        if "trading_value" in g.columns:
            tv = pd.to_numeric(g["trading_value"], errors="coerce")
            g["trading_value_avg_20d"] = tv.rolling(FLOW_LONG, min_periods=FLOW_LONG).mean()
            g["normalized_flow"] = [
                normalized_flow(_num(f), _num(d))
                for f, d in zip(g["flow_5d"], g["trading_value_avg_20d"], strict=True)
            ]
        else:
            g["trading_value_avg_20d"] = pd.NA
            g["normalized_flow"] = pd.NA

        if "price_momentum" not in g.columns:
            if "close" in g.columns:
                g["price_momentum"] = price_momentum_from_close(g["close"]).values
            else:
                g["price_momentum"] = pd.NA

        if "volume" in g.columns:
            g["volume_expansion"] = volume_expansion_ratio(g["volume"]).values
        else:
            g["volume_expansion"] = pd.NA

        g["continuity"] = buying_continuity(g["institutional_flow"]).values

        if "margin_buy_change" in g.columns and "trading_value" in g.columns:
            g["margin_signal"] = margin_signal_series(g["margin_buy_change"], g["trading_value"]).values
        else:
            g["margin_signal"] = pd.NA

        g[entity_col] = entity_id
        frames.append(g)

    out = pd.concat(frames, ignore_index=True)
    out["quadrant"] = [
        classify_quadrant(_num(f), _num(a))
        for f, a in zip(out["flow_5d"], out["acceleration"], strict=True)
    ]
    out["divergence_flag"] = [
        is_flow_price_divergence(_num(a), _num(f), _num(p))
        for a, f, p in zip(out["acceleration"], out["flow_5d"], out["price_momentum"], strict=True)
    ]
    return out


def _positive_streak(flow: pd.Series) -> pd.Series:
    streak = []
    run = 0
    for value in flow:
        if pd.isna(value):
            run = 0
            streak.append(pd.NA)
            continue
        if value > 0:
            run += 1
        else:
            run = 0
        streak.append(run)
    return pd.Series(streak, index=flow.index, dtype="Float64")


def _is_nan(value: float) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _num(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)

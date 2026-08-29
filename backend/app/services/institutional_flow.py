"""Pure institutional-flow arithmetic. No I/O."""

from __future__ import annotations

import pandas as pd


FLOW_COMPONENTS = (
    "foreign_net_amount",
    "investment_trust_net_amount",
    "dealer_net_amount",
)


def institutional_flow(
    foreign_net_amount: float | None,
    investment_trust_net_amount: float | None,
    dealer_net_amount: float | None,
) -> float | None:
    """Sum of the three institutional legs.

    Returns None if every component is missing. Present components that are
    None are not replaced with zero — only missing-all is None so a partial
    print is still usable, while a fully absent row stays absent.
    """
    parts = [foreign_net_amount, investment_trust_net_amount, dealer_net_amount]
    if all(p is None for p in parts):
        return None
    return float(sum(0.0 if p is None else p for p in parts))


def add_institutional_flow_column(frame: pd.DataFrame) -> pd.DataFrame:
    """Add `institutional_flow` from the three net-amount columns."""
    required = set(FLOW_COMPONENTS)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Flow frame missing columns: {sorted(missing)}")

    out = frame.copy()
    component = out[list(FLOW_COMPONENTS)]
    all_missing = component.isna().all(axis=1)
    out["institutional_flow"] = component.fillna(0.0).sum(axis=1)
    out.loc[all_missing, "institutional_flow"] = pd.NA
    return out


def aggregate_sector_daily_flow(
    stock_daily: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    """Sum stock institutional flow into each theme for each session.

    A security mapped to N themes contributes its full flow to each of those
    N themes. Rows are not globally deduplicated before the join.
    """
    if mapping.empty:
        return pd.DataFrame(
            columns=["trade_date", "theme_id", "institutional_flow", "member_count"]
        )

    needed = {"trade_date", "security_id", "institutional_flow"}
    if not needed.issubset(stock_daily.columns):
        raise ValueError(f"stock_daily missing columns: {sorted(needed - set(stock_daily.columns))}")
    if not {"security_id", "theme_id"}.issubset(mapping.columns):
        raise ValueError("mapping requires security_id and theme_id")

    joined = mapping.merge(stock_daily, on="security_id", how="inner")
    grouped = (
        joined.groupby(["trade_date", "theme_id"], as_index=False)
        .agg(
            institutional_flow=("institutional_flow", "sum"),
            member_count=("security_id", "nunique"),
        )
    )
    return grouped

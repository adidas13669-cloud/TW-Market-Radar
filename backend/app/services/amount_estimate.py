"""Estimate notional flow from shares * close when the source only prints volume.

Callers must persist amount_estimated=True and estimation_method. Scoring never
invents this itself.
"""

from __future__ import annotations

import pandas as pd

from app.core.units import ESTIMATION_SHARES_TIMES_CLOSE
from app.services.institutional_flow import FLOW_COMPONENTS


def estimate_amounts_from_shares(flows: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    out = flows.copy()
    if out.empty:
        return out
    if quotes is None or quotes.empty:
        px = pd.DataFrame(columns=["trade_date", "security_id", "close"])
    else:
        px = quotes[["trade_date", "security_id", "close"]]
    merged = out.merge(px, on=["trade_date", "security_id"], how="left")
    share_legs = (
        ("foreign_net_shares", "foreign_net_amount"),
        ("investment_trust_net_shares", "investment_trust_net_amount"),
        ("dealer_net_shares", "dealer_net_amount"),
    )
    estimated = pd.Series(False, index=merged.index)
    for share_col, amount_col in share_legs:
        if share_col not in merged.columns:
            continue
        if amount_col not in merged.columns:
            merged[amount_col] = pd.NA
        need = merged[amount_col].isna() & merged[share_col].notna() & merged["close"].notna()
        if need.any():
            merged.loc[need, amount_col] = merged.loc[need, share_col] * merged.loc[need, "close"]
            estimated |= need
    if "estimation_method" not in merged.columns:
        merged["estimation_method"] = pd.Series([pd.NA] * len(merged), dtype="object")
    if "amount_estimated" not in merged.columns:
        merged["amount_estimated"] = False
    if estimated.any():
        merged.loc[estimated, "estimation_method"] = ESTIMATION_SHARES_TIMES_CLOSE
        merged.loc[estimated, "amount_estimated"] = True
    share_cols = [c for c, _ in share_legs if c in merged.columns]
    if share_cols:
        all_share_missing = merged[share_cols].isna().all(axis=1)
        merged["raw_net_shares"] = merged[share_cols].fillna(0).sum(axis=1)
        merged.loc[all_share_missing, "raw_net_shares"] = pd.NA
    amount_cols = [c for c in FLOW_COMPONENTS if c in merged.columns]
    if amount_cols:
        all_amt_missing = merged[amount_cols].isna().all(axis=1)
        merged["estimated_net_amount"] = merged[amount_cols].fillna(0).sum(axis=1)
        merged.loc[all_amt_missing, "estimated_net_amount"] = pd.NA
    return merged.drop(columns=["close"], errors="ignore")

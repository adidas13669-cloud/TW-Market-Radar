"""Estimate notional flow from shares * close when the source only prints volume.

Callers must persist amount_estimated=True. Scoring never invents this itself.
"""

from __future__ import annotations

import pandas as pd


def estimate_amounts_from_shares(flows: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    out = flows.copy()
    if out.empty or quotes.empty:
        return out
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
        merged.loc[need, amount_col] = merged.loc[need, share_col] * merged.loc[need, "close"]
        estimated |= need
    merged["amount_estimated"] = estimated
    return merged.drop(columns=["close"])

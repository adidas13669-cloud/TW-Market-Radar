"""Sector member coverage. Low coverage stays stored but is excluded from default ranks."""

from __future__ import annotations

import pandas as pd

from app.core.config import get_settings


def attach_coverage(
    sector_metrics: pd.DataFrame,
    mapping: pd.DataFrame,
    quotes: pd.DataFrame,
    stock_daily: pd.DataFrame,
    min_coverage: float | None = None,
) -> pd.DataFrame:
    if sector_metrics.empty or mapping.empty:
        out = sector_metrics.copy()
        out["member_count"] = 0
        out["priced_member_count"] = 0
        out["flow_member_count"] = 0
        out["coverage_ratio"] = pd.NA
        out["low_coverage"] = True
        out["thin_membership"] = True
        out["rank_excluded"] = True
        return out

    threshold = min_coverage if min_coverage is not None else get_settings().min_coverage_ratio
    members = mapping[["security_id", "theme_id"]].drop_duplicates()
    roster = members.groupby("theme_id", as_index=False).agg(member_count=("security_id", "nunique"))

    q = quotes.copy() if quotes is not None else pd.DataFrame()
    if not q.empty:
        q["trade_date"] = pd.to_datetime(q["trade_date"]).dt.date
        priced = members.merge(q, on="security_id", how="inner")
        priced = priced[priced["close"].notna()] if "close" in priced.columns else priced.iloc[0:0]
        priced_ct = priced.groupby(["trade_date", "theme_id"], as_index=False).agg(
            priced_member_count=("security_id", "nunique")
        )
    else:
        priced_ct = pd.DataFrame(columns=["trade_date", "theme_id", "priced_member_count"])

    sd = stock_daily.copy()
    if not sd.empty:
        sd["trade_date"] = pd.to_datetime(sd["trade_date"]).dt.date
        flowed = members.merge(sd, on="security_id", how="inner")
        if "institutional_flow" in flowed.columns:
            flowed = flowed[flowed["institutional_flow"].notna()]
        flow_ct = flowed.groupby(["trade_date", "theme_id"], as_index=False).agg(
            flow_member_count=("security_id", "nunique")
        )
    else:
        flow_ct = pd.DataFrame(columns=["trade_date", "theme_id", "flow_member_count"])

    out = sector_metrics.copy()
    for col in (
        "member_count",
        "priced_member_count",
        "flow_member_count",
        "coverage_ratio",
        "low_coverage",
    ):
        if col in out.columns:
            out = out.drop(columns=[col])
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out = out.merge(roster, on="theme_id", how="left")
    out = out.merge(priced_ct, on=["trade_date", "theme_id"], how="left")
    out = out.merge(flow_ct, on=["trade_date", "theme_id"], how="left")
    out["member_count"] = out["member_count"].fillna(0).astype(int)
    out["priced_member_count"] = out["priced_member_count"].fillna(0).astype(int)
    out["flow_member_count"] = out["flow_member_count"].fillna(0).astype(int)
    denom = out["member_count"].replace(0, pd.NA)
    priced_r = out["priced_member_count"] / denom
    flow_r = out["flow_member_count"] / denom
    out["coverage_ratio"] = pd.concat([priced_r, flow_r], axis=1).min(axis=1)
    out["low_coverage"] = out["coverage_ratio"].fillna(0) < threshold
    min_members = get_settings().min_theme_members
    out["thin_membership"] = out["member_count"] < min_members
    if "concentrated_ok" not in out.columns:
        out["concentrated_ok"] = False
    else:
        out["concentrated_ok"] = out["concentrated_ok"].fillna(False).astype(bool)
    if "theme_level" in out.columns and out["theme_level"].notna().any():
        out["rank_excluded"] = out["low_coverage"] | (out["thin_membership"] & ~out["concentrated_ok"])
    else:
        out["rank_excluded"] = out["low_coverage"]
    return out

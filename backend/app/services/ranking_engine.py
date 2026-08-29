"""Deterministic ranking helpers on already-scored frames."""

from __future__ import annotations

import pandas as pd


def rank_descending(frame: pd.DataFrame, column: str, rank_col: str = "rank") -> pd.DataFrame:
    out = frame.copy()
    out[rank_col] = pd.to_numeric(out[column], errors="coerce").rank(
        method="min", ascending=False, na_option="keep"
    )
    return out.sort_values(by=[column, rank_col], ascending=[False, True], na_position="last")


def latest_asof(frame: pd.DataFrame, asof=None) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    dates = pd.to_datetime(frame["trade_date"])
    if asof is None:
        target = dates.max()
    else:
        target = pd.Timestamp(asof)
        available = dates[dates <= target]
        if available.empty:
            return frame.iloc[0:0].copy()
        target = available.max()
    return frame.loc[dates == target].copy()


def rank_sectors(frame: pd.DataFrame, asof=None) -> pd.DataFrame:
    snap = latest_asof(frame, asof)
    return rank_descending(snap, "rotation_score")


def rank_emerging(frame: pd.DataFrame, asof=None) -> pd.DataFrame:
    snap = latest_asof(frame, asof)
    out = rank_descending(snap, "emerging_metric")
    if "rotation_score" in out.columns:
        out = out.sort_values(
            by=["emerging_metric", "rotation_score"],
            ascending=[False, False],
            na_position="last",
        )
    return out


def rank_divergence(frame: pd.DataFrame, asof=None) -> pd.DataFrame:
    snap = latest_asof(frame, asof)
    flagged = snap[snap["divergence_flag"] == True]  # noqa: E712
    return rank_descending(flagged, "acceleration")


def rank_constituents(frame: pd.DataFrame, asof=None) -> pd.DataFrame:
    snap = latest_asof(frame, asof)
    return rank_descending(snap, "rotation_score")

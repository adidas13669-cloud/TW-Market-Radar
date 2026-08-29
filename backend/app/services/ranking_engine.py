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


def _eligible(
    snap: pd.DataFrame,
    include_low_coverage: bool,
    include_thin: bool = False,
    rank_levels: tuple[int, ...] | None = (2, 3),
) -> pd.DataFrame:
    out = snap
    if out.empty:
        return out
    if not include_low_coverage and "low_coverage" in out.columns:
        out = out[out["low_coverage"] != True].copy()  # noqa: E712
    has_levels = "theme_level" in out.columns and out["theme_level"].notna().any()
    if not include_thin and has_levels and "thin_membership" in out.columns:
        concentrated = out["concentrated_ok"] if "concentrated_ok" in out.columns else False
        drop_thin = out["thin_membership"] & ~pd.Series(concentrated, index=out.index).fillna(False)
        out = out[~drop_thin].copy()
    if rank_levels and has_levels:
        level = pd.to_numeric(out["theme_level"], errors="coerce")
        out = out[level.isna() | level.isin(rank_levels)].copy()
    return out


def rank_sectors(
    frame: pd.DataFrame,
    asof=None,
    include_low_coverage: bool = False,
    include_thin: bool = False,
    rank_levels: tuple[int, ...] | None = (2, 3),
) -> pd.DataFrame:
    snap = _eligible(latest_asof(frame, asof), include_low_coverage, include_thin, rank_levels)
    return rank_descending(snap, "rotation_score")


def rank_emerging(
    frame: pd.DataFrame,
    asof=None,
    include_low_coverage: bool = False,
    include_thin: bool = False,
    rank_levels: tuple[int, ...] | None = (2, 3),
) -> pd.DataFrame:
    snap = _eligible(latest_asof(frame, asof), include_low_coverage, include_thin, rank_levels)
    out = rank_descending(snap, "emerging_metric")
    if "rotation_score" in out.columns:
        out = out.sort_values(
            by=["emerging_metric", "rotation_score"],
            ascending=[False, False],
            na_position="last",
        )
    return out


def rank_divergence(
    frame: pd.DataFrame,
    asof=None,
    include_low_coverage: bool = False,
    include_thin: bool = False,
    rank_levels: tuple[int, ...] | None = (2, 3),
) -> pd.DataFrame:
    snap = _eligible(latest_asof(frame, asof), include_low_coverage, include_thin, rank_levels)
    flagged = snap[snap["divergence_flag"] == True]  # noqa: E712
    return rank_descending(flagged, "acceleration")


def rank_constituents(frame: pd.DataFrame, asof=None) -> pd.DataFrame:
    snap = latest_asof(frame, asof)
    return rank_descending(snap, "rotation_score")

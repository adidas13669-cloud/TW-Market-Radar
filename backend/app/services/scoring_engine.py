"""Cross-sectional Rotation Score and Emerging Rotation metric.

Factors are percentile-ranked within a comparison universe (typically all
themes on one trade_date) before weighting so units never mix.
"""

from __future__ import annotations

import pandas as pd

from app.core.config import ScoreWeights
from app.core.enums import Lifecycle, Quadrant
from app.services.rotation_engine import classify_lifecycle

FACTOR_COLUMNS = (
    "normalized_flow",
    "acceleration",
    "price_momentum",
    "volume_expansion",
    "continuity",
    "margin_signal",
)


def percentile_rank(series: pd.Series) -> pd.Series:
    """Average-rank percentile in (0, 1]. Ties share a rank. All-NA stays NA."""
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return s.astype("Float64")
    return s.rank(method="average", pct=True, na_option="keep")


def normalize_factors(frame: pd.DataFrame, columns: tuple[str, ...] = FACTOR_COLUMNS) -> pd.DataFrame:
    out = frame.copy()
    for col in columns:
        if col not in out.columns:
            out[f"{col}_pct"] = pd.NA
            continue
        out[f"{col}_pct"] = percentile_rank(out[col])
    return out


def rotation_score_row(
    percentiles: dict[str, float | None],
    weights: ScoreWeights,
) -> float | None:
    """Weighted sum of available percentile factors, weights re-normalized.

    Missing factors are skipped (not filled). If none are present, score is None.
    Result is clipped to [0, 100].
    """
    weight_map = weights.as_dict()
    used = 0.0
    acc = 0.0
    for name, weight in weight_map.items():
        value = percentiles.get(name)
        if value is None or pd.isna(value):
            continue
        acc += weight * float(value)
        used += weight
    if used == 0:
        return None
    score = 100.0 * (acc / used)
    return max(0.0, min(100.0, score))


def score_cross_section(
    frame: pd.DataFrame,
    weights: ScoreWeights | None = None,
    universe_key: str = "trade_date",
) -> pd.DataFrame:
    """Attach rotation_score for each row relative to peers sharing universe_key."""
    weights = weights or ScoreWeights()
    if frame.empty:
        out = frame.copy()
        out["rotation_score"] = pd.Series(dtype="float64")
        return out

    pieces: list[pd.DataFrame] = []
    for _, grp in frame.groupby(universe_key, sort=False):
        ranked = normalize_factors(grp)
        scores: list[float | None] = []
        for _, row in ranked.iterrows():
            percentiles = {name: _opt_float(row.get(f"{name}_pct")) for name in weights.as_dict()}
            scores.append(rotation_score_row(percentiles, weights))
        ranked = ranked.copy()
        ranked["rotation_score"] = scores
        pieces.append(ranked)
    out = pd.concat(pieces, ignore_index=True)
    out["lifecycle"] = [
        classify_lifecycle(
            _quadrant(row.get("quadrant")),
            _opt_float(row.get("rotation_score")),
            _opt_float(row.get("price_momentum")),
            _opt_float(row.get("volume_expansion")),
            _opt_float(row.get("acceleration")),
        )
        for _, row in out.iterrows()
    ]
    return out


def emerging_metric_from_scores(score_by_date: pd.Series, lag: int = 5) -> pd.Series:
    """Reward positive score path (e.g. 50 -> 65 -> 78), not just a high print.

    emerging = (score_t - score_{t-lag}) + 0.5 * max(convexity, 0)
    convexity uses the midpoint of the lag window when enough history exists.
    """
    s = pd.to_numeric(score_by_date, errors="coerce")
    change = s - s.shift(lag)
    half = max(lag // 2, 1)
    convexity = (s - s.shift(half)) - (s.shift(half) - s.shift(lag))
    convexity = convexity.where(s.shift(lag).notna())
    bonus = convexity.clip(lower=0) * 0.5
    return (change + bonus.fillna(0)).where(change.notna())


def attach_emerging_metric(
    scored: pd.DataFrame,
    entity_col: str = "theme_id",
    lag: int = 5,
) -> pd.DataFrame:
    if scored.empty:
        out = scored.copy()
        out["emerging_metric"] = pd.Series(dtype="float64")
        return out

    frames: list[pd.DataFrame] = []
    for _, grp in scored.sort_values("trade_date").groupby(entity_col, sort=False):
        g = grp.sort_values("trade_date").copy()
        g["emerging_metric"] = emerging_metric_from_scores(g["rotation_score"], lag=lag).values
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        return None
    return float(value)


def _quadrant(value: object) -> Quadrant | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, Quadrant):
        return value
    try:
        return Quadrant(str(value))
    except ValueError:
        return None


def _lifecycle(value: object) -> Lifecycle | None:
    if value is None:
        return None
    if isinstance(value, Lifecycle):
        return value
    try:
        return Lifecycle(str(value))
    except ValueError:
        return None

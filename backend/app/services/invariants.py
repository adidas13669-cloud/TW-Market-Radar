"""Market sanity checks used by audit CLI and unit tests (offline-safe)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from app.core.enums import Lifecycle, Quadrant
from app.services.rotation_engine import FLOW_LONG, classify_lifecycle, classify_quadrant


class InvariantViolation(AssertionError):
    pass


def assert_score_bounds(frame: pd.DataFrame, column: str = "rotation_score") -> None:
    s = pd.to_numeric(frame[column], errors="coerce")
    bad = s.notna() & ((s < 0) | (s > 100))
    if bad.any():
        raise InvariantViolation(f"{column} outside 0-100: {s[bad].tolist()[:5]}")


def assert_finite_normalized(frame: pd.DataFrame, column: str = "normalized_flow") -> None:
    if column not in frame.columns:
        return
    s = pd.to_numeric(frame[column], errors="coerce")
    inf = s.map(lambda x: bool(x is not None and not pd.isna(x) and math.isinf(float(x))))
    if inf.any():
        raise InvariantViolation(f"{column} contains inf")


def assert_quadrant_matches_signs(frame: pd.DataFrame) -> None:
    for _, row in frame.iterrows():
        flow = _num(row.get("flow_5d"))
        acc = _num(row.get("acceleration"))
        expected = classify_quadrant(flow, acc)
        got = row.get("quadrant")
        if expected is None:
            continue
        if got is None or (isinstance(got, float) and pd.isna(got)):
            raise InvariantViolation("quadrant missing while flow/acc present")
        if Quadrant(str(got)) != expected:
            raise InvariantViolation(f"quadrant {got} != {expected} for flow={flow} acc={acc}")


def assert_lifecycle_consistent(frame: pd.DataFrame) -> None:
    for _, row in frame.iterrows():
        q = row.get("quadrant")
        if q is None or (isinstance(q, float) and pd.isna(q)):
            continue
        expected = classify_lifecycle(
            Quadrant(str(q)),
            _num(row.get("rotation_score")),
            _num(row.get("price_momentum")),
            _num(row.get("volume_expansion")),
            _num(row.get("acceleration")),
        )
        got = row.get("lifecycle")
        if expected is None:
            continue
        if got is None or str(got) != expected.value:
            raise InvariantViolation(f"lifecycle {got} != {expected}")


def assert_warmup_windows(frame: pd.DataFrame, session_count: int) -> None:
    """After 20 stored sessions, latest rows must have avg_20d and acceleration."""
    if session_count < FLOW_LONG or frame.empty:
        return
    latest = pd.to_datetime(frame["trade_date"]).max()
    snap = frame.loc[pd.to_datetime(frame["trade_date"]) == latest]
    if snap["avg_20d"].isna().all():
        raise InvariantViolation("avg_20d still missing after 20-session warm-up")
    if snap["acceleration"].isna().all():
        raise InvariantViolation("acceleration still missing after 20-session warm-up")


def assert_no_nan_after_warmup(frame: pd.DataFrame, required: Sequence[str], session_count: int) -> None:
    if session_count < FLOW_LONG or frame.empty:
        return
    latest = pd.to_datetime(frame["trade_date"]).max()
    snap = frame.loc[pd.to_datetime(frame["trade_date"]) == latest]
    for col in required:
        if col not in snap.columns:
            continue
        if snap[col].isna().all():
            raise InvariantViolation(f"{col} entirely missing after warm-up")


def assert_emerging_after_history(frame: pd.DataFrame, min_score_points: int = 6) -> None:
    if frame.empty or "emerging_metric" not in frame.columns:
        return
    counts = frame.dropna(subset=["rotation_score"]).groupby("theme_id").size()
    ready = counts[counts >= min_score_points].index
    if ready.empty:
        return
    latest = pd.to_datetime(frame["trade_date"]).max()
    snap = frame.loc[pd.to_datetime(frame["trade_date"]) == latest]
    subset = snap[snap["theme_id"].isin(ready)]
    if subset.empty:
        return
    if subset["emerging_metric"].isna().all():
        raise InvariantViolation("emerging_metric missing after sufficient score history")


def validate_sector_invariants(frame: pd.DataFrame, session_count: int) -> None:
    if frame.empty:
        return
    assert_score_bounds(frame)
    assert_finite_normalized(frame)
    assert_quadrant_matches_signs(frame)
    assert_lifecycle_consistent(frame)
    assert_warmup_windows(frame, session_count)
    assert_no_nan_after_warmup(frame, ["flow_5d", "avg_5d", "rotation_score"], session_count)
    assert_emerging_after_history(frame)


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)

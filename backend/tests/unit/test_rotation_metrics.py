import pandas as pd

from app.core.enums import Quadrant
from app.services.rotation_engine import classify_quadrant, normalized_flow, window_flow_metrics


def test_avg5_avg20_and_acceleration():
    flow = pd.Series([10.0] * 5 + [0.0] * 15)
    metrics = window_flow_metrics(flow)
    last = metrics.iloc[-1]
    assert last["flow_5d"] == 0.0
    assert last["avg_5d"] == 0.0
    assert last["avg_20d"] == 2.5
    assert last["acceleration"] == -2.5

    first_full_short = metrics.iloc[4]
    assert first_full_short["flow_5d"] == 50.0
    assert first_full_short["avg_5d"] == 10.0
    assert pd.isna(first_full_short["avg_20d"])
    assert pd.isna(first_full_short["acceleration"])

    last20 = metrics.iloc[19]
    assert last20["avg_20d"] == 2.5
    assert last20["avg_5d"] == 0.0


def test_incomplete_windows_are_missing_not_fabricated():
    metrics = window_flow_metrics(pd.Series([1.0, 2.0, 3.0]))
    assert metrics["flow_5d"].isna().all()
    assert metrics["avg_20d"].isna().all()


def test_normalized_flow_guards_zero_and_missing_denominator():
    assert normalized_flow(100.0, 50.0) == 2.0
    assert normalized_flow(100.0, 0.0) is None
    assert normalized_flow(100.0, None) is None
    assert normalized_flow(None, 50.0) is None
    assert normalized_flow(100.0, float("nan")) is None


def test_all_four_quadrants_including_zero_boundaries():
    assert classify_quadrant(1.0, 1.0) == Quadrant.STRONG_INFLOW
    assert classify_quadrant(1.0, 0.0) == Quadrant.SLOWING_INFLOW
    assert classify_quadrant(1.0, -1.0) == Quadrant.SLOWING_INFLOW
    assert classify_quadrant(0.0, 1.0) == Quadrant.IMPROVING_OUTFLOW
    assert classify_quadrant(0.0, 0.0) == Quadrant.ACCELERATING_OUTFLOW
    assert classify_quadrant(-1.0, 1.0) == Quadrant.IMPROVING_OUTFLOW
    assert classify_quadrant(-1.0, 0.0) == Quadrant.ACCELERATING_OUTFLOW
    assert classify_quadrant(-1.0, -1.0) == Quadrant.ACCELERATING_OUTFLOW
    assert classify_quadrant(None, 1.0) is None
    assert classify_quadrant(1.0, None) is None

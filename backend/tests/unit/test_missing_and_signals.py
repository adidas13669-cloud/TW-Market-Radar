import math

import pandas as pd

from app.core.enums import Lifecycle, Quadrant
from app.services.rotation_engine import (
    buying_continuity,
    classify_lifecycle,
    is_flow_price_divergence,
    price_momentum_from_close,
    volume_expansion_ratio,
)


def test_missing_price_momentum_not_filled():
    close = pd.Series([10.0, None, 12.0, 12.5, 13.0, 14.0])
    mom = price_momentum_from_close(close, lookback=5)
    assert math.isclose(float(mom.iloc[5]), 0.4)
    close_zero = pd.Series([0.0, 1, 1, 1, 1, 2])
    mom0 = price_momentum_from_close(close_zero, lookback=5)
    assert pd.isna(mom0.iloc[-1])
    short = price_momentum_from_close(pd.Series([10.0, 11.0]), lookback=5)
    assert short.isna().all()


def test_volume_expansion_zero_denominator_is_missing():
    vol = pd.Series([0.0] * 20)
    ratio = volume_expansion_ratio(vol)
    assert ratio.isna().all()


def test_continuity_requires_full_lookback():
    flow = pd.Series([1.0] * 9)
    cont = buying_continuity(flow, lookback=10)
    assert cont.isna().all()
    flow10 = pd.Series([1.0] * 10)
    cont10 = buying_continuity(flow10, lookback=10)
    assert math.isclose(float(cont10.iloc[-1]), 1.0)


def test_divergence_requires_accelerating_inflow_and_quiet_price():
    assert is_flow_price_divergence(1.0, 10.0, 0.01) is True
    assert is_flow_price_divergence(1.0, 10.0, 0.05) is False
    assert is_flow_price_divergence(-1.0, 10.0, 0.0) is False
    assert is_flow_price_divergence(1.0, -10.0, 0.0) is False
    assert is_flow_price_divergence(1.0, 10.0, None) is False


def test_lifecycle_rules():
    assert (
        classify_lifecycle(Quadrant.ACCELERATING_OUTFLOW, 80.0, 0.1, 2.0, -1.0)
        == Lifecycle.EXIT
    )
    assert (
        classify_lifecycle(Quadrant.STRONG_INFLOW, 70.0, 0.08, 1.2, 1.0)
        == Lifecycle.CONFIRMED
    )
    assert classify_lifecycle(Quadrant.STRONG_INFLOW, 70.0, 0.01, 1.2, 1.0) == Lifecycle.EARLY
    assert classify_lifecycle(Quadrant.SLOWING_INFLOW, 80.0, 0.1, 1.6, -0.2) == Lifecycle.CROWDED

import pandas as pd

from app.core.config import ScoreWeights
from app.services.scoring_engine import (
    attach_emerging_metric,
    emerging_metric_from_scores,
    rotation_score_row,
    score_cross_section,
)


def test_rotation_score_is_bounded_0_100():
    weights = ScoreWeights()
    low = rotation_score_row({name: 0.0 for name in weights.as_dict()}, weights)
    high = rotation_score_row({name: 1.0 for name in weights.as_dict()}, weights)
    mid = rotation_score_row({name: 0.5 for name in weights.as_dict()}, weights)
    assert low == 0.0
    assert high == 100.0
    assert mid == 50.0

    clipped = rotation_score_row({name: 2.0 for name in weights.as_dict()}, weights)
    assert clipped == 100.0


def test_rotation_score_skips_missing_factors_and_renormalizes():
    weights = ScoreWeights(flow=0.5, acceleration=0.5, price_momentum=0, volume_expansion=0, continuity=0, margin=0)
    score = rotation_score_row({"normalized_flow": 1.0, "acceleration": None}, weights)
    assert score == 100.0
    assert rotation_score_row({}, weights) is None


def test_cross_section_scores_stay_in_bounds():
    frame = pd.DataFrame(
        {
            "trade_date": ["2024-01-31"] * 4,
            "theme_id": ["A", "B", "C", "D"],
            "normalized_flow": [0.1, 0.2, 0.3, 0.4],
            "acceleration": [-5, 0, 5, 10],
            "price_momentum": [-0.1, 0.0, 0.05, 0.2],
            "volume_expansion": [0.8, 1.0, 1.2, 2.0],
            "continuity": [0.1, 0.4, 0.7, 1.0],
            "margin_signal": [-0.2, 0.0, 0.1, 0.3],
            "quadrant": ["STRONG_INFLOW"] * 4,
        }
    )
    scored = score_cross_section(frame)
    assert scored["rotation_score"].between(0, 100).all()
    assert scored.loc[scored["theme_id"] == "D", "rotation_score"].iloc[0] == scored["rotation_score"].max()
    assert scored.loc[scored["theme_id"] == "A", "rotation_score"].iloc[0] == scored["rotation_score"].min()


def test_emerging_rotation_orders_rising_path_ahead_of_high_flat():
    rising = pd.Series([50.0, 65.0, 78.0])
    flat = pd.Series([80.0, 80.0, 80.0])
    falling = pd.Series([90.0, 85.0, 70.0])
    lag = 2
    r, f, d = (
        emerging_metric_from_scores(rising, lag=lag).iloc[-1],
        emerging_metric_from_scores(flat, lag=lag).iloc[-1],
        emerging_metric_from_scores(falling, lag=lag).iloc[-1],
    )
    assert r > f > d


def test_emerging_metric_attached_per_theme():
    rows = []
    for i, (theme, scores) in enumerate(
        {
            "RISING": [50.0, 65.0, 78.0],
            "FLAT": [80.0, 80.0, 80.0],
            "FALLING": [90.0, 85.0, 70.0],
        }.items()
    ):
        for j, score in enumerate(scores):
            rows.append(
                {
                    "theme_id": theme,
                    "trade_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=j),
                    "rotation_score": score,
                }
            )
    frame = pd.DataFrame(rows)
    out = attach_emerging_metric(frame, lag=2)
    latest = out.sort_values("trade_date").groupby("theme_id").tail(1)
    order = latest.sort_values("emerging_metric", ascending=False)["theme_id"].tolist()
    assert order == ["RISING", "FLAT", "FALLING"]

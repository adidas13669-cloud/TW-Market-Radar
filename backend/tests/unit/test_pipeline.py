from app.services.pipeline import run_calculation
from tests.fixtures.market import synthetic_snapshot


def test_pipeline_produces_sector_scores_and_history():
    result = run_calculation(synthetic_snapshot(25))
    latest = result.sector_metrics["trade_date"].max()
    snap = result.sector_metrics[result.sector_metrics["trade_date"] == latest]
    assert set(snap["theme_id"]) == {"SEMI", "AI", "SHIP"}
    assert snap["rotation_score"].between(0, 100).all()
    assert snap["flow_5d"].notna().all()
    assert snap["avg_20d"].notna().all()
    assert snap["acceleration"].notna().all()
    ship = snap.loc[snap["theme_id"] == "SHIP"].iloc[0]
    assert ship["flow_5d"] < 0
    semi = snap.loc[snap["theme_id"] == "SEMI"].iloc[0]
    assert semi["flow_5d"] > 0


def test_pipeline_keeps_multi_theme_stock_in_both_sectors():
    result = run_calculation(synthetic_snapshot(5))
    latest = result.sector_daily["trade_date"].max()
    day = result.sector_daily[result.sector_daily["trade_date"] == latest]
    # 2330 is in SEMI and AI; both sectors must have positive member contribution
    assert day.loc[day["theme_id"] == "SEMI", "member_count"].iloc[0] == 2
    assert day.loc[day["theme_id"] == "AI", "member_count"].iloc[0] == 2

from app.data_providers.registry import load_theme_mapping_csv
from app.services.ranking_engine import rank_emerging, rank_sectors
from tests.fixtures.market import synthetic_snapshot
from app.services.pipeline import run_calculation


def test_load_theme_mapping_csv_keeps_multi_theme_rows():
    rows = load_theme_mapping_csv("data/theme_mapping/seed_themes.csv")
    tsmc = [r for r in rows if r.security_id == "2330"]
    assert {r.theme_id for r in tsmc} == {"SEMI", "AI"}


def test_rank_sectors_orders_by_rotation_score():
    result = run_calculation(synthetic_snapshot(25))
    ranked = rank_sectors(result.sector_metrics)
    scores = list(ranked["rotation_score"])
    assert scores == sorted(scores, reverse=True)
    emerging = rank_emerging(result.sector_metrics)
    assert "emerging_metric" in emerging.columns

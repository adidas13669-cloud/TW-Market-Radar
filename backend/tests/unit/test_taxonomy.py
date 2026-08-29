from datetime import date

import pandas as pd

from app.core.config import get_settings
from app.core.securities import is_common_stock
from app.services.ranking_engine import rank_sectors
from app.taxonomy.flatten import expand_membership, flatten_themes
from app.taxonomy.loader import CURRENT_MAPPING_VERSION, load_taxonomy_bundle, mapping_effective_on
from app.taxonomy.validate import validate_taxonomy
from app.services.pipeline import run_calculation
from tests.fixtures.market import synthetic_snapshot


def test_taxonomy_has_100_plus_themes_and_three_levels():
    themes = flatten_themes()
    assert len(themes) >= 100
    levels = {t.theme_level for t in themes}
    assert levels == {1, 2, 3}
    l1 = [t for t in themes if t.theme_level == 1]
    assert all(t.parent_theme_id is None for t in l1)


def test_taxonomy_parent_child_consistency():
    bundle = load_taxonomy_bundle()
    report = validate_taxonomy(bundle)
    assert report.ok
    assert not report.unknown_parents
    assert not report.level_mismatch
    assert not report.duplicate_pairs
    assert report.mapped_securities >= 1500
    assert report.l2 >= 80


def test_membership_rolls_up_to_parents():
    members = expand_membership()
    tsmc = {m.theme_id for m in members if m.security_id == "2330"}
    assert "SEMI_FOUNDRY" in tsmc
    assert "SEMI" in tsmc
    assert "SEMI_COWOS" in tsmc


def test_common_stock_heuristic():
    assert is_common_stock("2330")
    assert is_common_stock("6488")
    assert not is_common_stock("0050")
    assert not is_common_stock("2002A")
    assert not is_common_stock("00400A")


def test_mapping_effective_window():
    assert mapping_effective_on(date(2026, 6, 1), effective_from=date(2026, 6, 1), effective_to=None)
    assert not mapping_effective_on(date(2026, 5, 31), effective_from=date(2026, 6, 1), effective_to=None)
    assert mapping_effective_on(date(2026, 8, 1), effective_from=date(2026, 6, 1), effective_to=date(2026, 8, 31))
    assert not mapping_effective_on(date(2026, 9, 1), effective_from=date(2026, 6, 1), effective_to=date(2026, 8, 31))


def test_thin_membership_excluded_when_theme_levels_present():
    result = run_calculation(synthetic_snapshot(25))
    frame = result.sector_metrics.copy()
    frame["theme_level"] = 3
    frame["thin_membership"] = True
    frame["concentrated_ok"] = False
    frame["low_coverage"] = False
    ranked = rank_sectors(frame)
    assert ranked.empty
    allowed = rank_sectors(frame, include_thin=True)
    assert not allowed.empty


def test_current_mapping_version_constant():
    assert CURRENT_MAPPING_VERSION == "v2-tax-2"
    assert get_settings().min_theme_members == 3


def test_coverage_prefix_and_keywords_expand_unmapped_names():
    members = expand_membership(
        universe=[("1103", "嘉泥"), ("2801", "彰銀"), ("2330", "台積電")],
    )
    by = {(m.security_id, m.theme_id) for m in members}
    assert ("1103", "CEMENT") in by
    assert ("1103", "MATERIALS") in by
    assert ("2801", "BANK") in by or ("2801", "FINANCIAL") in by
    # Curated TSMC is not also dumped into the electronics L1 residual via prefix.
    tsmc_l1 = {m.theme_id for m in members if m.security_id == "2330" and m.theme_id == "ELEC"}
    assert not tsmc_l1


def test_retired_tickers_not_in_curated_members():
    from app.taxonomy.v2_catalog import MEMBERS

    retired = {"2456", "2809", "2823", "2841", "2856", "2888", "3698", "5102", "6288", "9412"}
    present = {sid for tickers in MEMBERS.values() for sid in tickers}
    assert not (retired & present)


def test_persist_calculation_keeps_other_mapping_versions(tmp_path):
    from datetime import date

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models.entities import Base, SectorDailyMetric, Theme
    from app.services.persistence import persist_calculation
    from app.services.pipeline import CalculationResult

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    session.add(Theme(id="CEMENT", name="水泥"))
    session.add(
        SectorDailyMetric(
            theme_id="CEMENT",
            trade_date=date(2026, 8, 28),
            mapping_version="v2-tax-1",
            rotation_score=10,
        )
    )
    session.commit()
    result = CalculationResult(
        stock_daily=pd.DataFrame(),
        sector_daily=pd.DataFrame(),
        sector_metrics=pd.DataFrame(
            [
                {
                    "theme_id": "CEMENT",
                    "trade_date": date(2026, 8, 28),
                    "rotation_score": 50,
                    "divergence_flag": False,
                    "low_coverage": False,
                    "thin_membership": False,
                    "rank_excluded": False,
                }
            ]
        ),
        stock_metrics=pd.DataFrame(),
    )
    persist_calculation(session, result, mapping_version="v2-tax-2")
    session.commit()
    versions = set(
        session.execute(select(SectorDailyMetric.mapping_version)).scalars().all()
    )
    assert versions == {"v2-tax-1", "v2-tax-2"}

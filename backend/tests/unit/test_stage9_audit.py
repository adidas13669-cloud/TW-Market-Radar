from datetime import date

import pandas as pd

from app.services.audit import mapping_audit
from app.services.invariants import validate_sector_invariants
from app.services.pipeline import run_calculation
from app.services.ranking_engine import rank_emerging, rank_sectors
from tests.fixtures.market import synthetic_snapshot


def test_sector_invariants_hold_after_warmup():
    result = run_calculation(synthetic_snapshot(25))
    dates = pd.to_datetime(result.sector_metrics["trade_date"]).dt.date.nunique()
    validate_sector_invariants(result.sector_metrics, session_count=int(dates))


def test_low_coverage_kept_but_excluded_from_default_ranks():
    result = run_calculation(synthetic_snapshot(25))
    frame = result.sector_metrics.copy()
    latest = pd.to_datetime(frame["trade_date"]).max()
    mask = pd.to_datetime(frame["trade_date"]) == latest
    frame.loc[mask, "low_coverage"] = True
    frame.loc[mask & (frame["theme_id"] == "SEMI"), "low_coverage"] = False
    ranked = rank_sectors(frame)
    assert set(ranked["theme_id"]) == {"SEMI"}
    emerging = rank_emerging(frame)
    assert set(emerging["theme_id"]) == {"SEMI"}
    included = rank_sectors(frame, include_low_coverage=True)
    assert set(included["theme_id"]) == {"SEMI", "AI", "SHIP"}


def test_coverage_columns_attached():
    result = run_calculation(synthetic_snapshot(25))
    latest = result.sector_metrics["trade_date"].max()
    snap = result.sector_metrics[result.sector_metrics["trade_date"] == latest]
    assert (snap["member_count"] >= 1).all()
    assert (snap["coverage_ratio"] >= 0.8).all()
    assert (~snap["low_coverage"]).all()


def test_mapping_audit_reports_invalid_unmapped_and_multi_theme(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models.entities import Base, DailyQuote, MappingCatalog, Security, SecurityTheme, Theme

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    session.add(Theme(id="SEMI", name="半導體"))
    session.add(Security(id="2330", name="TSMC", market="TWSE"))
    session.add(Security(id="9999", name="FAKE", market="TWSE"))
    session.add(Security(id="1101", name="台泥", market="TWSE"))
    session.add(SecurityTheme(security_id="2330", theme_id="SEMI", mapping_version="seed-v1"))
    session.add(SecurityTheme(security_id="9999", theme_id="SEMI", mapping_version="seed-v1"))
    session.add(DailyQuote(security_id="2330", trade_date=date(2026, 8, 28), close=100))
    session.add(DailyQuote(security_id="1101", trade_date=date(2026, 8, 28), close=30))
    session.add(
        MappingCatalog(
            mapping_version="seed-v1",
            mapping_source="seed",
            effective_from=date(2026, 6, 1),
            production_ready=False,
        )
    )
    session.commit()
    report = mapping_audit(session, asof=date(2026, 8, 28))
    assert report["mapping_version"] == "seed-v1"
    assert report["production_ready"] is False
    assert "9999" in report["invalid_tickers"]
    assert "9999" in report["delisted_or_missing_on_asof"]
    assert report["unmapped_securities_on_asof"] == 1
    assert "1101" in report["unmapped_sample"]

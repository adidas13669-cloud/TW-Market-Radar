from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ProviderError
from app.core.enums import IngestStatus
from app.models.entities import Base, DailyQuote, IngestRun
from app.services.ingest import ingest_trade_date
from app.services.pipeline import run_calculation
from app.services.validation import validate_session
from tests.fixtures.market import synthetic_snapshot

LIVE = Path(__file__).resolve().parent.parent / "fixtures" / "live"


class PayloadProvider:
    name = "TWSE"

    def __init__(self, payloads: dict[str, dict], fail: str | None = None) -> None:
        self._payloads = payloads
        self._fail = fail

    def quotes_request(self, trade_date: date):
        return "https://example.test/quotes", {"d": trade_date.isoformat()}

    def flow_request(self, trade_date: date):
        return "https://example.test/flow", {"d": trade_date.isoformat()}

    def margin_request(self, trade_date: date):
        return "https://example.test/margin", {"d": trade_date.isoformat()}

    def fetch_payload(self, url: str, params):
        if self._fail and self._fail in url:
            raise ProviderError(f"failed {url}")
        if "quotes" in url:
            return self._payloads["quotes"]
        if "flow" in url:
            return self._payloads["flow"]
        return self._payloads["margin"]


class EmptyHolidayProvider(PayloadProvider):
    def fetch_payload(self, url: str, params):
        from app.core.exceptions import NoTradingSessionError

        raise NoTradingSessionError("holiday")


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _twse_payloads():
    import json

    def load(name):
        return json.loads((LIVE / name).read_text(encoding="utf-8"))

    return {
        "quotes": load("twse_mi_index_20260828.json"),
        "flow": load("twse_t86_20260828.json"),
        "margin": load("twse_mi_margn_20260828.json"),
    }


def _tpex_payloads():
    import json

    def load(name):
        return json.loads((LIVE / name).read_text(encoding="utf-8"))

    return {
        "quotes": load("tpex_quotes_20260828.json"),
        "flow": load("tpex_flow_20260828.json"),
        "margin": load("tpex_margin_20260828.json"),
    }


def test_duplicate_ingest_is_idempotent(tmp_path):
    session = _session()
    twse = PayloadProvider(_twse_payloads())
    tpex = PayloadProvider(_tpex_payloads())
    mapping = Path("data/theme_mapping/seed_themes.csv")
    kwargs = dict(
        twse=twse,
        tpex=tpex,
        payload_dir=tmp_path,
        mapping_path=mapping,
        recompute_metrics=True,
    )
    first = ingest_trade_date(session, date(2026, 8, 28), **kwargs)
    session.commit()
    n_quotes = session.execute(select(func.count()).select_from(DailyQuote)).scalar()
    second = ingest_trade_date(session, date(2026, 8, 28), **kwargs)
    session.commit()
    n_quotes2 = session.execute(select(func.count()).select_from(DailyQuote)).scalar()
    assert n_quotes == n_quotes2
    assert first.providers["TWSE"].quotes == second.providers["TWSE"].quotes
    assert (tmp_path / "2026-08-28" / "twse_quotes.json").exists()
    from app.models.entities import Security

    tpex_stock = session.get(Security, "3105")
    twse_stock = session.get(Security, "1101")
    if tpex_stock is not None:
        assert tpex_stock.market == "TPEX"
    if twse_stock is not None:
        assert twse_stock.market == "TWSE"


def test_successful_ingest_is_skipped_on_resume(tmp_path):
    session = _session()
    twse = PayloadProvider(_twse_payloads())
    tpex = PayloadProvider(_tpex_payloads())
    mapping = Path("data/theme_mapping/seed_themes.csv")
    kwargs = dict(
        twse=twse,
        tpex=tpex,
        payload_dir=tmp_path,
        mapping_path=mapping,
        recompute_metrics=False,
        skip_if_success=True,
    )
    first = ingest_trade_date(session, date(2026, 8, 28), **kwargs)
    session.commit()
    assert first.status == IngestStatus.SUCCESS
    second = ingest_trade_date(session, date(2026, 8, 28), **kwargs)
    assert second.status == IngestStatus.SKIPPED
    run = session.get(IngestRun, date(2026, 8, 28))
    assert run is not None
    assert run.status == IngestStatus.SUCCESS
    assert session.execute(select(func.count()).select_from(DailyQuote)).scalar() > 0


def test_partial_provider_failure_still_ingests_other_venue(tmp_path):
    session = _session()
    twse = PayloadProvider(_twse_payloads(), fail="quotes")
    tpex = PayloadProvider(_tpex_payloads())
    result = ingest_trade_date(
        session,
        date(2026, 8, 28),
        twse=twse,
        tpex=tpex,
        payload_dir=tmp_path,
        mapping_path=Path("data/theme_mapping/seed_themes.csv"),
        continue_on_provider_error=True,
        recompute_metrics=False,
    )
    assert result.providers["TWSE"].error
    assert result.providers["TPEX"].quotes > 0
    assert session.execute(select(func.count()).select_from(DailyQuote)).scalar() > 0


def test_holiday_skips_persist(tmp_path):
    session = _session()
    result = ingest_trade_date(
        session,
        date(2026, 8, 29),
        twse=EmptyHolidayProvider({"quotes": {}, "flow": {}, "margin": {}}),
        tpex=EmptyHolidayProvider({"quotes": {}, "flow": {}, "margin": {}}),
        payload_dir=tmp_path,
        mapping_path=Path("data/theme_mapping/seed_themes.csv"),
    )
    assert result.skipped_holiday
    assert session.execute(select(func.count()).select_from(DailyQuote)).scalar() == 0


def test_suspended_and_warmup_validation():
    quotes = pd.DataFrame(
        [
            {"trade_date": date(2026, 8, 28), "security_id": "1472", "close": None, "is_suspended": True},
            {"trade_date": date(2026, 8, 28), "security_id": "2330", "close": 2420, "is_suspended": False},
        ]
    )
    report = validate_session(date(2026, 8, 28), quotes, pd.DataFrame(), prior_security_ids={"2330"})
    assert "1472" in report.suspended_ids
    assert "1472" in report.new_listing_ids
    assert report.warmup_complete is False
    assert any(i.code == "warmup" for i in report.issues)


def test_twenty_session_warmup_behavior():
    short = run_calculation(synthetic_snapshot(5))
    latest = short.sector_metrics["trade_date"].max()
    snap = short.sector_metrics[short.sector_metrics["trade_date"] == latest]
    assert snap["avg_20d"].isna().all()
    assert snap["acceleration"].isna().all()
    full = run_calculation(synthetic_snapshot(25))
    latest = full.sector_metrics["trade_date"].max()
    snap = full.sector_metrics[full.sector_metrics["trade_date"] == latest]
    assert snap["avg_20d"].notna().all()

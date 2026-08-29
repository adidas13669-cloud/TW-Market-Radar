from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.core.exceptions import NoTradingSessionError, UnitMismatchError
from app.core.units import QuantityUnit
from app.data_providers.tpex import parse_tpex_flow, parse_tpex_margin, parse_tpex_quotes
from app.data_providers.twse import parse_twse_flow, parse_twse_margin, parse_twse_quotes
from app.services.institutional_flow import add_institutional_flow_column, aggregate_sector_daily_flow
from app.services.normalize import to_canonical_flow, to_margin_notional

LIVE = Path(__file__).resolve().parent.parent / "fixtures" / "live"


def _json(name: str):
    import json

    return json.loads((LIVE / name).read_text(encoding="utf-8"))


def test_twse_real_payload_quotes_units_and_suspended():
    rows = parse_twse_quotes(_json("twse_mi_index_20260828.json"), date(2026, 8, 28))
    by_id = {r.security_id: r for r in rows}
    tsmc = by_id["2330"]
    assert tsmc.close == 2420
    assert tsmc.volume == 15_025_832
    assert tsmc.trading_value == 36_465_015_980
    assert tsmc.volume_unit == QuantityUnit.SHARES
    assert tsmc.trading_value_unit == QuantityUnit.TWD_NOTIONAL
    assert by_id["1472"].is_suspended is True
    assert by_id["1472"].close is None


def test_twse_real_payload_flow_is_shares_not_twd():
    rows = parse_twse_flow(_json("twse_t86_20260828.json"), date(2026, 8, 28))
    tsmc = next(r for r in rows if r.security_id == "2330")
    assert tsmc.foreign_net_shares == 3_031_655
    assert tsmc.investment_trust_net_shares == -1_764_995
    assert tsmc.dealer_net_shares == -23_367
    assert tsmc.foreign_net_amount is None
    assert tsmc.source_unit == QuantityUnit.SHARES
    buy, sell, net = 10_027_572, 6_995_917, 3_031_655
    assert buy - sell == net


def test_twse_real_payload_margin_is_lots():
    rows = parse_twse_margin(_json("twse_mi_margn_20260828.json"), date(2026, 8, 28))
    tsmc = next(r for r in rows if r.security_id == "2330")
    assert tsmc.source_unit == QuantityUnit.LOTS
    assert tsmc.margin_buy_balance_lots == 27_630
    assert tsmc.margin_buy_change_lots == -40  # 27630 - 27670


def test_twse_holiday_payload():
    with pytest.raises(NoTradingSessionError):
        parse_twse_quotes(_json("twse_mi_index_holiday.json"), date(2026, 8, 29))


def test_tpex_real_payload_quotes_shares_and_twd():
    rows = parse_tpex_quotes(_json("tpex_quotes_20260828.json"), date(2026, 8, 28))
    win = next(r for r in rows if r.security_id == "3105")
    assert win.close == 439
    assert win.volume == 48_392_000
    assert win.trading_value == 21_737_791_500
    assert win.volume_unit == QuantityUnit.SHARES


def test_tpex_real_payload_flow_shares_same_sign_as_twse():
    rows = parse_tpex_flow(_json("tpex_flow_20260828.json"), date(2026, 8, 28))
    win = next(r for r in rows if r.security_id == "3105")
    assert win.source_unit == QuantityUnit.SHARES
    assert win.foreign_net_amount is None
    # 買賣超 = 買 − 賣 for foreign group (indices 2,3,4)
    raw = _json("tpex_flow_20260828.json")["tables"][0]["data"]
    row = next(r for r in raw if r[0] == "3105")
    buy = float(str(row[2]).replace(",", ""))
    sell = float(str(row[3]).replace(",", ""))
    net = float(str(row[4]).replace(",", ""))
    assert buy - sell == net
    assert win.foreign_net_shares == net


def test_tpex_real_payload_margin_lots():
    rows = parse_tpex_margin(_json("tpex_margin_20260828.json"), date(2026, 8, 28))
    win = next(r for r in rows if r.security_id == "3105")
    assert win.source_unit == QuantityUnit.LOTS
    assert win.margin_buy_balance_lots == 43_627
    assert win.margin_buy_change_lots == 43_627 - 43_897


def test_tpex_holiday_empty_session():
    with pytest.raises(NoTradingSessionError):
        parse_tpex_quotes(_json("tpex_quotes_holiday.json"), date(2026, 8, 29))


def test_share_to_notional_and_margin_notional():
    flows = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 28),
                "security_id": "2330",
                "foreign_net_shares": 10,
                "investment_trust_net_shares": 0,
                "dealer_net_shares": 0,
                "foreign_net_amount": None,
                "investment_trust_net_amount": None,
                "dealer_net_amount": None,
                "source_unit": "shares",
            }
        ]
    )
    quotes = pd.DataFrame(
        [{"trade_date": date(2026, 8, 28), "security_id": "2330", "close": 2420.0, "trading_value": 1e9, "volume": 1e6}]
    )
    out = to_canonical_flow(flows, quotes)
    assert out.loc[0, "foreign_net_amount"] == 24200.0
    assert out.loc[0, "flow_unit"] == "twd_notional"
    margins = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 28),
                "security_id": "2330",
                "margin_buy_change_lots": -40,
                "source_unit": "lots",
            }
        ]
    )
    m = to_margin_notional(margins, quotes)
    assert m.loc[0, "margin_share_change"] == -40_000
    assert m.loc[0, "margin_notional_change"] == -40_000 * 2420


def test_missing_close_during_amount_estimation():
    flows = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 28),
                "security_id": "1472",
                "foreign_net_shares": 100,
                "investment_trust_net_shares": None,
                "dealer_net_shares": None,
                "foreign_net_amount": None,
                "investment_trust_net_amount": None,
                "dealer_net_amount": None,
                "source_unit": "shares",
            }
        ]
    )
    quotes = pd.DataFrame(
        [{"trade_date": date(2026, 8, 28), "security_id": "1472", "close": None}]
    )
    out = to_canonical_flow(flows, quotes)
    assert pd.isna(out.loc[0, "foreign_net_amount"])
    assert pd.isna(out.loc[0, "institutional_flow"])


def test_unit_mismatch_rejected_at_aggregation():
    flows = add_institutional_flow_column(
        pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 8, 28),
                    "security_id": "A",
                    "foreign_net_amount": 100,
                    "investment_trust_net_amount": 0,
                    "dealer_net_amount": 0,
                    "flow_unit": "shares",
                }
            ]
        )
    )
    flows["flow_unit"] = "shares"
    mapping = pd.DataFrame([{"security_id": "A", "theme_id": "SEMI"}])
    with pytest.raises(UnitMismatchError):
        aggregate_sector_daily_flow(flows, mapping)


def test_mixed_share_and_twd_source_rejected():
    flows = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 28),
                "security_id": "A",
                "foreign_net_amount": 100,
                "investment_trust_net_amount": 0,
                "dealer_net_amount": 0,
                "source_unit": "shares",
            },
            {
                "trade_date": date(2026, 8, 28),
                "security_id": "B",
                "foreign_net_amount": 100,
                "investment_trust_net_amount": 0,
                "dealer_net_amount": 0,
                "source_unit": "twd_notional",
            },
        ]
    )
    with pytest.raises(UnitMismatchError):
        to_canonical_flow(flows, pd.DataFrame())

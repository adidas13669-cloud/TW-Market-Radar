from datetime import date

import httpx
import pytest

from app.core.exceptions import ProviderError, ProviderParseError
from app.core.http import HttpClient
from app.data_providers.dates import parse_number, to_roc_slash, to_yyyymmdd
from app.data_providers.twse import parse_twse_flow, parse_twse_quotes


def test_date_helpers():
    d = date(2024, 3, 1)
    assert to_yyyymmdd(d) == "20240301"
    assert to_roc_slash(d) == "113/03/01"


def test_parse_number_does_not_fabricate_missing():
    assert parse_number("----") is None
    assert parse_number("--") is None
    assert parse_number("") is None
    assert parse_number("1,234") == 1234.0
    with pytest.raises(ValueError):
        parse_number("abc")


def test_parse_twse_quotes_isolated_schema():
    payload = {
        "tables": [
            {
                "fields": ["證券代號", "證券名稱", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"],
                "data": [["2330", "台積電", "10,000", "5,000,000", "500", "510", "490", "505"]],
            }
        ]
    }
    rows = parse_twse_quotes(payload, date(2024, 1, 2))
    assert len(rows) == 1
    assert rows[0].security_id == "2330"
    assert rows[0].close == 505
    assert rows[0].trading_value == 5_000_000


def test_parse_twse_flow_missing_legs_stay_none():
    payload = {
        "stat": "OK",
        "fields": ["證券代號", "外資買賣超股數", "投信買賣超股數", "自營商買賣超股數"],
        "data": [["2330", "1,000", "--", ""]],
    }
    rows = parse_twse_flow(payload, date(2024, 1, 2))
    assert rows[0].foreign_net_shares == 1000
    assert rows[0].investment_trust_net_shares is None
    assert rows[0].dealer_net_shares is None
    assert rows[0].foreign_net_amount is None
    assert rows[0].source_unit.value == "shares"


def test_parse_rejects_non_object():
    with pytest.raises(ProviderParseError):
        parse_twse_quotes(["not", "an", "object"], date(2024, 1, 2))


def test_http_client_retries_then_errors():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "nope"})

    transport = httpx.MockTransport(handler)
    client = HttpClient(timeout_seconds=1, max_retries=3, backoff_seconds=0, transport=transport)
    with pytest.raises(ProviderError):
        client.get_json("https://example.test/data")
    assert calls["n"] == 3
    client.close()

"""TWSE adapter. Parsing is isolated from HTTP."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.config import get_settings
from app.core.enums import Market
from app.core.exceptions import ProviderParseError
from app.core.http import HttpClient
from app.data_providers.base import FlowRecord, MarginRecord, QuoteRecord, SecurityRecord
from app.data_providers.dates import parse_number, to_yyyymmdd


class TwseProvider:
    name = "TWSE"

    def __init__(self, client: HttpClient | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base = (base_url or settings.twse_base_url).rstrip("/")
        self._client = client or HttpClient(
            timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
            backoff_seconds=settings.http_retry_backoff_seconds,
        )

    def fetch_securities(self) -> list[SecurityRecord]:
        # Listed names from the latest MI_INDEX type=ALLBUT0999 payload's stock rows.
        payload = self._client.get_json(
            f"{self._base}/rwd/zh/afterTrading/MI_INDEX",
            params={"response": "json", "type": "ALLBUT0999"},
        )
        quotes = parse_twse_quotes(payload, trade_date=date.today())
        return [
            SecurityRecord(security_id=q.security_id, name="", market=Market.TWSE)
            for q in quotes
        ]

    def fetch_daily_quotes(self, trade_date: date) -> list[QuoteRecord]:
        payload = self._client.get_json(
            f"{self._base}/rwd/zh/afterTrading/MI_INDEX",
            params={"response": "json", "date": to_yyyymmdd(trade_date), "type": "ALLBUT0999"},
        )
        return parse_twse_quotes(payload, trade_date)

    def fetch_institutional_flow(self, trade_date: date) -> list[FlowRecord]:
        payload = self._client.get_json(
            f"{self._base}/rwd/zh/fund/T86",
            params={"response": "json", "date": to_yyyymmdd(trade_date), "selectType": "ALL"},
        )
        return parse_twse_flow(payload, trade_date)

    def fetch_margin(self, trade_date: date) -> list[MarginRecord]:
        payload = self._client.get_json(
            f"{self._base}/rwd/zh/marginTrading/MI_MARGN",
            params={"response": "json", "date": to_yyyymmdd(trade_date), "selectType": "STOCK"},
        )
        return parse_twse_margin(payload, trade_date)


def _tables(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TWSE payload is not an object")
    tables = payload.get("tables")
    if isinstance(tables, list) and tables:
        return [t for t in tables if isinstance(t, dict)]
    if "fields" in payload and "data" in payload:
        return [payload]
    raise ProviderParseError("TWSE payload missing tables/fields")


def _rows_from_fields(table: dict[str, Any]) -> list[dict[str, Any]]:
    fields = table.get("fields") or table.get("title")
    data = table.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise ProviderParseError("TWSE table missing fields/data")
    rows = []
    for raw in data:
        if not isinstance(raw, list):
            continue
        mapped = {str(fields[i]): raw[i] if i < len(raw) else None for i in range(len(fields))}
        rows.append(mapped)
    return rows


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    for key, value in row.items():
        for name in names:
            if name in str(key) and value not in (None, ""):
                return value
    return None


def parse_twse_quotes(payload: Any, trade_date: date) -> list[QuoteRecord]:
    records: list[QuoteRecord] = []
    for table in _tables(payload):
        try:
            rows = _rows_from_fields(table)
        except ProviderParseError:
            continue
        for row in rows:
            code = _pick(row, "證券代號", "代號", "股票代號")
            if code is None:
                continue
            sid = str(code).strip()
            if not sid.isdigit():
                continue
            close = _safe_num(_pick(row, "收盤價", "收盤"))
            volume = _safe_num(_pick(row, "成交股數", "成交量"))
            value = _safe_num(_pick(row, "成交金額"))
            records.append(
                QuoteRecord(
                    security_id=sid,
                    trade_date=trade_date,
                    open=_safe_num(_pick(row, "開盤價", "開盤")),
                    high=_safe_num(_pick(row, "最高價", "最高")),
                    low=_safe_num(_pick(row, "最低價", "最低")),
                    close=close,
                    volume=volume,
                    trading_value=value,
                )
            )
    return records


def parse_twse_flow(payload: Any, trade_date: date) -> list[FlowRecord]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TWSE T86 payload is not an object")
    tables = []
    if "fields" in payload and "data" in payload:
        tables = [payload]
    else:
        tables = _tables(payload)
    records: list[FlowRecord] = []
    for table in tables:
        for row in _rows_from_fields(table):
            code = _pick(row, "證券代號", "代號")
            if code is None:
                continue
            sid = str(code).strip()
            records.append(
                FlowRecord(
                    security_id=sid,
                    trade_date=trade_date,
                    foreign_net_amount=_first_num(
                        row,
                        "外陸資買賣超股數(不含外資自營商)",
                        "外資買賣超股數",
                        "外資及陸資買賣超股數",
                    ),
                    investment_trust_net_amount=_first_num(row, "投信買賣超股數"),
                    dealer_net_amount=_first_num(row, "自營商買賣超股數", "自營商買賣超股數(自行買賣)"),
                    foreign_net_shares=_first_num(
                        row,
                        "外陸資買賣超股數(不含外資自營商)",
                        "外資買賣超股數",
                    ),
                    investment_trust_net_shares=_first_num(row, "投信買賣超股數"),
                    dealer_net_shares=_first_num(row, "自營商買賣超股數"),
                    amount_estimated=False,
                )
            )
    return records


def parse_twse_margin(payload: Any, trade_date: date) -> list[MarginRecord]:
    records: list[MarginRecord] = []
    sources: list[dict[str, Any]]
    if isinstance(payload, dict) and "fields" in payload:
        sources = [payload]
    else:
        sources = _tables(payload)
    for table in sources:
        try:
            rows = _rows_from_fields(table)
        except ProviderParseError:
            continue
        for row in rows:
            code = _pick(row, "股票代號", "證券代號", "代號")
            if code is None:
                continue
            records.append(
                MarginRecord(
                    security_id=str(code).strip(),
                    trade_date=trade_date,
                    margin_buy_balance=_first_num(row, "融資今日餘額", "融資餘額"),
                    short_sell_balance=_first_num(row, "融券今日餘額", "融券餘額"),
                    margin_buy_change=_margin_change(row),
                    short_sell_change=_short_change(row),
                )
            )
    return records


def _margin_change(row: dict[str, Any]) -> float | None:
    today = _first_num(row, "融資今日餘額")
    yesterday = _first_num(row, "融資昨日餘額")
    if today is None or yesterday is None:
        return _first_num(row, "融資增減")
    return today - yesterday


def _short_change(row: dict[str, Any]) -> float | None:
    today = _first_num(row, "融券今日餘額")
    yesterday = _first_num(row, "融券昨日餘額")
    if today is None or yesterday is None:
        return _first_num(row, "融券增減")
    return today - yesterday


def _first_num(row: dict[str, Any], *names: str) -> float | None:
    return _safe_num(_pick(row, *names))


def _safe_num(value: object) -> float | None:
    try:
        return parse_number(value)
    except ValueError as exc:
        raise ProviderParseError(str(exc)) from exc

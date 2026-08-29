"""TWSE adapter. Field maps verified against 2026-08-28 live JSON."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.config import get_settings
from app.core.enums import Market
from app.core.exceptions import NoTradingSessionError, ProviderParseError
from app.core.http import HttpClient
from app.core.units import LOT_TO_SHARES, QuantityUnit
from app.data_providers.base import FlowRecord, MarginRecord, QuoteRecord, SecurityRecord
from app.data_providers.dates import parse_number, to_yyyymmdd
from app.data_providers.parse_util import field_map, pick, safe_num, strip_code, sum_present

# Verified T86 column names (stat=OK, date=20260828).
TWSE_FOREIGN_NET_SHARES = "外陸資買賣超股數(不含外資自營商)"
TWSE_TRUST_NET_SHARES = "投信買賣超股數"
TWSE_DEALER_NET_SHARES = "自營商買賣超股數"  # 自行買賣 + 避險
TWSE_FOREIGN_BUY = "外陸資買進股數(不含外資自營商)"
TWSE_FOREIGN_SELL = "外陸資賣出股數(不含外資自營商)"

TWSE_QUOTE_TABLE_FIELDS = ("證券代號", "收盤價", "成交股數", "成交金額")


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

    def quotes_request(self, trade_date: date) -> tuple[str, dict[str, str]]:
        return f"{self._base}/rwd/zh/afterTrading/MI_INDEX", {
            "response": "json",
            "date": to_yyyymmdd(trade_date),
            "type": "ALLBUT0999",
        }

    def flow_request(self, trade_date: date) -> tuple[str, dict[str, str]]:
        return f"{self._base}/rwd/zh/fund/T86", {
            "response": "json",
            "date": to_yyyymmdd(trade_date),
            "selectType": "ALLBUT0999",
        }

    def margin_request(self, trade_date: date) -> tuple[str, dict[str, str]]:
        return f"{self._base}/rwd/zh/marginTrading/MI_MARGN", {
            "response": "json",
            "date": to_yyyymmdd(trade_date),
            "selectType": "STOCK",
        }

    def fetch_payload(self, url: str, params: dict[str, str]) -> Any:
        return self._client.get_json(url, params=params)

    def fetch_securities(self) -> list[SecurityRecord]:
        url, params = self.quotes_request(date.today())
        params = {k: v for k, v in params.items() if k != "date"}
        payload = self._client.get_json(url, params=params)
        quotes = parse_twse_quotes(payload, trade_date=date.today())
        return [
            SecurityRecord(security_id=q.security_id, name=q.name or "", market=Market.TWSE)
            for q in quotes
        ]

    def fetch_daily_quotes(self, trade_date: date) -> list[QuoteRecord]:
        url, params = self.quotes_request(trade_date)
        return parse_twse_quotes(self.fetch_payload(url, params), trade_date)

    def fetch_institutional_flow(self, trade_date: date) -> list[FlowRecord]:
        url, params = self.flow_request(trade_date)
        return parse_twse_flow(self.fetch_payload(url, params), trade_date)

    def fetch_margin(self, trade_date: date) -> list[MarginRecord]:
        url, params = self.margin_request(trade_date)
        return parse_twse_margin(self.fetch_payload(url, params), trade_date)


def twse_session_ok(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    stat = str(payload.get("stat") or "")
    if stat.upper() == "OK":
        return True
    return False


def parse_twse_quotes(payload: Any, trade_date: date) -> list[QuoteRecord]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TWSE payload is not an object")
    if not twse_session_ok(payload) and not _has_stock_table(payload):
        raise NoTradingSessionError(f"TWSE has no session for {trade_date}: {payload.get('stat')}")
    records: list[QuoteRecord] = []
    for table in _tables(payload):
        try:
            rows = _rows_from_fields(table)
        except ProviderParseError:
            continue
        if not rows or not any(k in rows[0] for k in ("證券代號", "代號")):
            continue
        if "收盤價" not in rows[0] and "收盤" not in rows[0]:
            continue
        for row in rows:
            code = pick(row, "證券代號", "代號", "股票代號")
            if code is None:
                continue
            sid = strip_code(code)
            if not sid:
                continue
            close = safe_num(pick(row, "收盤價", "收盤"))
            volume = safe_num(pick(row, "成交股數", "成交量"))
            value = safe_num(pick(row, "成交金額"))
            records.append(
                QuoteRecord(
                    security_id=sid,
                    trade_date=trade_date,
                    name=str(pick(row, "證券名稱", "名稱") or "").strip() or None,
                    open=safe_num(pick(row, "開盤價", "開盤")),
                    high=safe_num(pick(row, "最高價", "最高")),
                    low=safe_num(pick(row, "最低價", "最低")),
                    close=close,
                    volume=volume,
                    trading_value=value,
                    volume_unit=QuantityUnit.SHARES,
                    trading_value_unit=QuantityUnit.TWD_NOTIONAL,
                    is_suspended=close is None,
                )
            )
    return records


def parse_twse_flow(payload: Any, trade_date: date) -> list[FlowRecord]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TWSE T86 payload is not an object")
    if not twse_session_ok(payload) and "data" not in payload and "tables" not in payload:
        raise NoTradingSessionError(f"TWSE T86 has no session for {trade_date}: {payload.get('stat')}")
    tables = [payload] if "fields" in payload and "data" in payload else _tables(payload)
    records: list[FlowRecord] = []
    for table in tables:
        for row in _rows_from_fields(table):
            code = pick(row, "證券代號", "代號")
            if code is None:
                continue
            sid = strip_code(code)
            foreign = safe_num(pick(row, TWSE_FOREIGN_NET_SHARES, "外資買賣超股數", "外資及陸資買賣超股數"))
            trust = safe_num(pick(row, TWSE_TRUST_NET_SHARES))
            dealer = safe_num(pick(row, TWSE_DEALER_NET_SHARES, "自營商買賣超股數(自行買賣)"))
            records.append(
                FlowRecord(
                    security_id=sid,
                    trade_date=trade_date,
                    name=str(pick(row, "證券名稱", "名稱") or "").strip() or None,
                    foreign_net_shares=foreign,
                    investment_trust_net_shares=trust,
                    dealer_net_shares=dealer,
                    raw_net_shares=sum_present(foreign, trust, dealer),
                    foreign_net_amount=None,
                    investment_trust_net_amount=None,
                    dealer_net_amount=None,
                    estimated_net_amount=None,
                    source_unit=QuantityUnit.SHARES,
                    flow_unit=None,
                    amount_estimated=False,
                    estimation_method=None,
                )
            )
    return records


def parse_twse_margin(payload: Any, trade_date: date) -> list[MarginRecord]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TWSE MI_MARGN payload is not an object")
    if not twse_session_ok(payload) and "tables" not in payload:
        raise NoTradingSessionError(f"TWSE margin has no session for {trade_date}: {payload.get('stat')}")
    sources = [payload] if "fields" in payload and "data" in payload else _tables(payload)
    records: list[MarginRecord] = []
    for table in sources:
        try:
            rows = _rows_from_fields_duplicate(table)
        except ProviderParseError:
            continue
        if not rows:
            continue
        if "代號" not in rows[0] and "證券代號" not in rows[0]:
            continue
        for row in rows:
            code = pick(row, "代號", "股票代號", "證券代號")
            if code is None:
                continue
            sid = strip_code(code)
            if not sid or sid in {"合計"}:
                continue
            yesterday = safe_num(row.get("融資_前日餘額") or pick(row, "前日餘額"))
            today = safe_num(row.get("融資_今日餘額") or pick(row, "今日餘額", "融資今日餘額", "融資餘額"))
            change = None
            if today is not None and yesterday is not None:
                change = today - yesterday
            else:
                change = safe_num(pick(row, "融資增減"))
            short_y = safe_num(row.get("融券_前日餘額"))
            short_t = safe_num(row.get("融券_今日餘額") or pick(row, "融券今日餘額", "融券餘額"))
            short_chg = None
            if short_t is not None and short_y is not None:
                short_chg = short_t - short_y
            records.append(
                MarginRecord(
                    security_id=sid,
                    trade_date=trade_date,
                    name=str(pick(row, "名稱", "證券名稱") or "").strip() or None,
                    source_unit=QuantityUnit.LOTS,
                    lot_size=LOT_TO_SHARES,
                    margin_buy_balance_lots=today,
                    short_sell_balance_lots=short_t,
                    margin_buy_change_lots=change,
                    short_sell_change_lots=short_chg,
                    margin_buy_balance=today,
                    short_sell_balance=short_t,
                    margin_buy_change=change,
                    short_sell_change=short_chg,
                )
            )
    return records


def _has_stock_table(payload: dict[str, Any]) -> bool:
    for table in payload.get("tables") or []:
        if isinstance(table, dict) and "收盤價" in (table.get("fields") or []):
            return True
    return False


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
    return [field_map(fields, raw) for raw in data if isinstance(raw, list)]


def _rows_from_fields_duplicate(table: dict[str, Any]) -> list[dict[str, Any]]:
    """MI_MARGN repeats 前日餘額/今日餘額 for 融資 then 融券."""
    fields = table.get("fields")
    data = table.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise ProviderParseError("TWSE table missing fields/data")
    labels = []
    seen_today = 0
    for name in fields:
        key = str(name).strip()
        if key in {"前日餘額", "今日餘額", "買進", "賣出", "次一營業日限額"}:
            prefix = "融資" if seen_today == 0 else "融券"
            if key == "今日餘額":
                # 今日餘額 appears once per block; after first 今日餘額, next block is 融券.
                labels.append(f"{prefix}_{key}")
                if prefix == "融資" and key == "今日餘額":
                    pass
            else:
                labels.append(f"{prefix}_{key}")
            if key == "次一營業日限額" and prefix == "融資":
                seen_today = 1
        else:
            labels.append(key)
    # Fallback if heuristic failed: positional 5=融資前日 6=融資今日 11=融券前日 12=融券今日
    rows = []
    for raw in data:
        if not isinstance(raw, list):
            continue
        mapped = {labels[i]: raw[i] if i < len(raw) else None for i in range(len(labels))}
        if len(raw) >= 13:
            mapped["融資_前日餘額"] = raw[5]
            mapped["融資_今日餘額"] = raw[6]
            mapped["融券_前日餘額"] = raw[11]
            mapped["融券_今日餘額"] = raw[12]
        rows.append(mapped)
    return rows

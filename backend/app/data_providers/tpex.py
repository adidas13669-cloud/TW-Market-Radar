"""TPEx adapter. Field maps verified against 2026-08-28 live JSON.

Quote volume is 成交股數 (shares). Bid/ask sizes are 張. Margin balances are 張.
Institutional 三大法人 columns are 股數 with the same 買賣超 = 買 − 賣 sign as TWSE.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.config import get_settings
from app.core.enums import Market
from app.core.exceptions import NoTradingSessionError, ProviderParseError
from app.core.http import HttpClient
from app.core.units import LOT_TO_SHARES, QuantityUnit
from app.data_providers.base import FlowRecord, MarginRecord, QuoteRecord, SecurityRecord
from app.data_providers.dates import to_roc_slash
from app.data_providers.parse_util import field_map, pick, safe_num, strip_code, sum_present

# Verified 2026-08-28: 7 repeating 買進/賣出/買賣超 groups then 合計.
# Group order matches TWSE T86: foreign ex-dealer, foreign dealer, foreign total,
# trust, dealer proprietary, dealer hedge, dealer total.
TPEX_FOREIGN_NET_IDX = 4
TPEX_TRUST_NET_IDX = 13
TPEX_DEALER_NET_IDX = 22  # 自營商合計 買賣超股數


class TpexProvider:
    name = "TPEX"

    def __init__(self, client: HttpClient | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base = (base_url or settings.tpex_base_url).rstrip("/")
        self._client = client or HttpClient(
            timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
            backoff_seconds=settings.http_retry_backoff_seconds,
        )

    def quotes_request(self, trade_date: date) -> tuple[str, dict[str, str]]:
        return f"{self._base}/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php", {
            "l": "zh-tw",
            "o": "json",
            "se": "EW",
            "d": to_roc_slash(trade_date),
        }

    def flow_request(self, trade_date: date) -> tuple[str, dict[str, str]]:
        return f"{self._base}/web/stock/3insti/daily_trade/3itrade_hedge_result.php", {
            "l": "zh-tw",
            "o": "json",
            "se": "EW",
            "t": "D",
            "d": to_roc_slash(trade_date),
        }

    def margin_request(self, trade_date: date) -> tuple[str, dict[str, str]]:
        return f"{self._base}/web/stock/margin_trading/margin_balance/margin_bal_result.php", {
            "l": "zh-tw",
            "o": "json",
            "d": to_roc_slash(trade_date),
        }

    def fetch_payload(self, url: str, params: dict[str, str]) -> Any:
        return self._client.get_json(url, params=params)

    def fetch_securities(self) -> list[SecurityRecord]:
        url, params = self.quotes_request(date.today())
        quotes = parse_tpex_quotes(self.fetch_payload(url, params), date.today())
        return [SecurityRecord(security_id=q.security_id, name=q.name or "", market=Market.TPEX) for q in quotes]

    def fetch_daily_quotes(self, trade_date: date) -> list[QuoteRecord]:
        url, params = self.quotes_request(trade_date)
        return parse_tpex_quotes(self.fetch_payload(url, params), trade_date)

    def fetch_institutional_flow(self, trade_date: date) -> list[FlowRecord]:
        url, params = self.flow_request(trade_date)
        return parse_tpex_flow(self.fetch_payload(url, params), trade_date)

    def fetch_margin(self, trade_date: date) -> list[MarginRecord]:
        url, params = self.margin_request(trade_date)
        return parse_tpex_margin(self.fetch_payload(url, params), trade_date)


def parse_tpex_quotes(payload: Any, trade_date: date) -> list[QuoteRecord]:
    table = _first_table(payload, trade_date, kind="quotes")
    fields = table.get("fields") or []
    rows = table.get("data") or table.get("aaData") or []
    records: list[QuoteRecord] = []
    for raw in rows:
        if not isinstance(raw, list) or not raw:
            continue
        row = field_map(fields, raw) if fields else {}
        sid = strip_code(row.get("代號") or raw[0])
        if not sid:
            continue
        close = safe_num(pick(row, "收盤") if row else (raw[2] if len(raw) > 2 else None))
        if not row:
            close = safe_num(raw[2] if len(raw) > 2 else None)
        records.append(
            QuoteRecord(
                security_id=sid,
                trade_date=trade_date,
                name=str(pick(row, "名稱") or (raw[1] if len(raw) > 1 else "")).strip() or None,
                close=safe_num(pick(row, "收盤")) if row else safe_num(raw[2] if len(raw) > 2 else None),
                open=safe_num(pick(row, "開盤")) if row else safe_num(raw[4] if len(raw) > 4 else None),
                high=safe_num(pick(row, "最高")) if row else safe_num(raw[5] if len(raw) > 5 else None),
                low=safe_num(pick(row, "最低")) if row else safe_num(raw[6] if len(raw) > 6 else None),
                volume=safe_num(pick(row, "成交股數")) if row else safe_num(raw[7] if len(raw) > 7 else None),
                trading_value=safe_num(pick(row, "成交金額(元)")) if row else safe_num(raw[8] if len(raw) > 8 else None),
                volume_unit=QuantityUnit.SHARES,
                trading_value_unit=QuantityUnit.TWD_NOTIONAL,
                is_suspended=(safe_num(pick(row, "收盤")) if row else safe_num(raw[2] if len(raw) > 2 else None)) is None,
            )
        )
    return records


def parse_tpex_flow(payload: Any, trade_date: date) -> list[FlowRecord]:
    table = _first_table(payload, trade_date, kind="flow")
    rows = table.get("data") or table.get("aaData") or []
    records: list[FlowRecord] = []
    for raw in rows:
        if not isinstance(raw, list) or not raw:
            continue
        sid = strip_code(raw[0])
        foreign = _idx(raw, TPEX_FOREIGN_NET_IDX)
        trust = _idx(raw, TPEX_TRUST_NET_IDX)
        dealer = _idx(raw, TPEX_DEALER_NET_IDX)
        records.append(
            FlowRecord(
                security_id=sid,
                trade_date=trade_date,
                name=str(raw[1]).strip() if len(raw) > 1 else None,
                foreign_net_shares=foreign,
                investment_trust_net_shares=trust,
                dealer_net_shares=dealer,
                raw_net_shares=sum_present(foreign, trust, dealer),
                source_unit=QuantityUnit.SHARES,
                flow_unit=None,
                amount_estimated=False,
            )
        )
    return records


def parse_tpex_margin(payload: Any, trade_date: date) -> list[MarginRecord]:
    table = _first_table(payload, trade_date, kind="margin")
    fields = table.get("fields") or []
    rows = table.get("data") or table.get("aaData") or []
    records: list[MarginRecord] = []
    for raw in rows:
        if not isinstance(raw, list) or not raw:
            continue
        row = field_map(fields, raw) if fields else {}
        sid = strip_code(row.get("代號") or raw[0])
        yesterday = safe_num(pick(row, "前資餘額(張)")) if row else _idx(raw, 2)
        today = safe_num(pick(row, "資餘額")) if row else _idx(raw, 6)
        buy = safe_num(pick(row, "資買")) if row else _idx(raw, 3)
        sell = safe_num(pick(row, "資賣")) if row else _idx(raw, 4)
        redeem = safe_num(pick(row, "現償")) if row else _idx(raw, 5)
        change = None
        if today is not None and yesterday is not None:
            change = today - yesterday
        elif buy is not None or sell is not None or redeem is not None:
            change = (buy or 0) - (sell or 0) - (redeem or 0)
        short_y = safe_num(pick(row, "前券餘額(張)")) if row else _idx(raw, 10)
        short_t = safe_num(pick(row, "券餘額")) if row else _idx(raw, 14)
        short_chg = None
        if short_t is not None and short_y is not None:
            short_chg = short_t - short_y
        records.append(
            MarginRecord(
                security_id=sid,
                trade_date=trade_date,
                name=str(pick(row, "名稱") or (raw[1] if len(raw) > 1 else "")).strip() or None,
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


def _first_table(payload: Any, trade_date: date, kind: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TPEx payload is not an object")
    tables = payload.get("tables")
    if isinstance(tables, list) and tables and isinstance(tables[0], dict):
        table = tables[0]
        data = table.get("data") or table.get("aaData") or []
        total = table.get("totalCount")
        if str(payload.get("stat") or "").lower() in {"ok", ""} and total == 0 and not data:
            raise NoTradingSessionError(f"TPEx {kind} has no session for {trade_date}")
        if data or total == 0:
            return table
        return table
    data = payload.get("aaData")
    if isinstance(data, list):
        if not data:
            raise NoTradingSessionError(f"TPEx {kind} has no session for {trade_date}")
        return {"fields": payload.get("fields") or [], "data": data}
    raise ProviderParseError("TPEx payload missing tables/aaData")


def _idx(row: list[Any], index: int) -> float | None:
    if index >= len(row):
        return None
    return safe_num(row[index])

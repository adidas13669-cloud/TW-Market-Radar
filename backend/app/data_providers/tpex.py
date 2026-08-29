"""TPEx adapter. Parsing is isolated from HTTP."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.config import get_settings
from app.core.enums import Market
from app.core.exceptions import ProviderParseError
from app.core.http import HttpClient
from app.data_providers.base import FlowRecord, MarginRecord, QuoteRecord, SecurityRecord
from app.data_providers.dates import parse_number, to_roc_slash


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

    def fetch_securities(self) -> list[SecurityRecord]:
        payload = self._client.get_json(
            f"{self._base}/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php",
            params={"l": "zh-tw", "o": "json", "se": "EW"},
        )
        quotes = parse_tpex_quotes(payload, date.today())
        return [SecurityRecord(security_id=q.security_id, name="", market=Market.TPEX) for q in quotes]

    def fetch_daily_quotes(self, trade_date: date) -> list[QuoteRecord]:
        payload = self._client.get_json(
            f"{self._base}/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php",
            params={"l": "zh-tw", "o": "json", "se": "EW", "d": to_roc_slash(trade_date)},
        )
        return parse_tpex_quotes(payload, trade_date)

    def fetch_institutional_flow(self, trade_date: date) -> list[FlowRecord]:
        payload = self._client.get_json(
            f"{self._base}/web/stock/3insti/daily_trade/3itrade_hedge_result.php",
            params={"l": "zh-tw", "o": "json", "se": "EW", "t": "D", "d": to_roc_slash(trade_date)},
        )
        return parse_tpex_flow(payload, trade_date)

    def fetch_margin(self, trade_date: date) -> list[MarginRecord]:
        payload = self._client.get_json(
            f"{self._base}/web/stock/margin_trading/margin_balance/margin_bal_result.php",
            params={"l": "zh-tw", "o": "json", "d": to_roc_slash(trade_date)},
        )
        return parse_tpex_margin(payload, trade_date)


def parse_tpex_quotes(payload: Any, trade_date: date) -> list[QuoteRecord]:
    rows = _aa_data(payload)
    records: list[QuoteRecord] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        sid = str(row[0]).strip()
        if not sid:
            continue
        records.append(
            QuoteRecord(
                security_id=sid,
                trade_date=trade_date,
                close=_idx(row, 2),
                open=_idx(row, 4),
                high=_idx(row, 5),
                low=_idx(row, 6),
                volume=_idx(row, 7),
                trading_value=_idx(row, 8),
            )
        )
    return records


def parse_tpex_flow(payload: Any, trade_date: date) -> list[FlowRecord]:
    rows = _aa_data(payload)
    records: list[FlowRecord] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        sid = str(row[0]).strip()
        records.append(
            FlowRecord(
                security_id=sid,
                trade_date=trade_date,
                foreign_net_shares=_idx(row, 10) if len(row) > 10 else _idx(row, 4),
                investment_trust_net_shares=_idx(row, 13) if len(row) > 13 else _idx(row, 7),
                dealer_net_shares=_idx(row, 22) if len(row) > 22 else _idx(row, 10),
                foreign_net_amount=None,
                investment_trust_net_amount=None,
                dealer_net_amount=None,
                amount_estimated=False,
            )
        )
    return records


def parse_tpex_margin(payload: Any, trade_date: date) -> list[MarginRecord]:
    rows = _aa_data(payload)
    records: list[MarginRecord] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        records.append(
            MarginRecord(
                security_id=str(row[0]).strip(),
                trade_date=trade_date,
                margin_buy_balance=_idx(row, 5),
                short_sell_balance=_idx(row, 11) if len(row) > 11 else None,
                margin_buy_change=_idx(row, 6),
                short_sell_change=_idx(row, 12) if len(row) > 12 else None,
            )
        )
    return records


def _aa_data(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        raise ProviderParseError("TPEx payload is not an object")
    data = payload.get("aaData")
    if data is None:
        data = payload.get("tables")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            data = data[0].get("data")
    if not isinstance(data, list):
        raise ProviderParseError("TPEx payload missing aaData")
    return data


def _idx(row: list[Any], index: int) -> float | None:
    if index >= len(row):
        return None
    try:
        return parse_number(row[index])
    except ValueError as exc:
        raise ProviderParseError(str(exc)) from exc

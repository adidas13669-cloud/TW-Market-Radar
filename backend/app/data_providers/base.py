from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class SecurityRecord(BaseModel):
    security_id: str
    name: str
    market: str
    is_active: bool = True


class QuoteRecord(BaseModel):
    security_id: str
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    trading_value: float | None = None


class FlowRecord(BaseModel):
    security_id: str
    trade_date: date
    foreign_net_amount: float | None = None
    investment_trust_net_amount: float | None = None
    dealer_net_amount: float | None = None
    foreign_net_shares: float | None = None
    investment_trust_net_shares: float | None = None
    dealer_net_shares: float | None = None
    amount_estimated: bool = False


class MarginRecord(BaseModel):
    security_id: str
    trade_date: date
    margin_buy_balance: float | None = None
    short_sell_balance: float | None = None
    margin_buy_change: float | None = None
    short_sell_change: float | None = None


class ThemeMappingRecord(BaseModel):
    security_id: str
    theme_id: str
    theme_name: str | None = None


@runtime_checkable
class MarketDataProvider(Protocol):
    """Replaceable TWSE / TPEx (or fixture) adapter.

    Implementations must raise ProviderError on transport failure and
    ProviderParseError on unexpected payloads. Missing rows are omitted,
    never invented.
    """

    name: str

    def fetch_securities(self) -> list[SecurityRecord]: ...

    def fetch_daily_quotes(self, trade_date: date) -> list[QuoteRecord]: ...

    def fetch_institutional_flow(self, trade_date: date) -> list[FlowRecord]: ...

    def fetch_margin(self, trade_date: date) -> list[MarginRecord]: ...

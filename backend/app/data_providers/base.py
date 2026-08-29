from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.core.units import QuantityUnit


class SecurityRecord(BaseModel):
    security_id: str
    name: str
    market: str
    is_active: bool = True


class QuoteRecord(BaseModel):
    security_id: str
    trade_date: date
    name: str | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    trading_value: float | None = None
    volume_unit: QuantityUnit = QuantityUnit.SHARES
    trading_value_unit: QuantityUnit = QuantityUnit.TWD_NOTIONAL
    is_suspended: bool = False


class FlowRecord(BaseModel):
    """Institutional print. Raw quantity stays in *_shares; TWD never copied from 股數."""

    security_id: str
    trade_date: date
    name: str | None = None
    foreign_net_shares: float | None = None
    investment_trust_net_shares: float | None = None
    dealer_net_shares: float | None = None
    raw_net_shares: float | None = None
    foreign_net_amount: float | None = None
    investment_trust_net_amount: float | None = None
    dealer_net_amount: float | None = None
    estimated_net_amount: float | None = None
    source_unit: QuantityUnit = QuantityUnit.SHARES
    flow_unit: QuantityUnit | None = None
    amount_estimated: bool = False
    estimation_method: str | None = None
    sign_convention: str = "net_buy_positive"


class MarginRecord(BaseModel):
    security_id: str
    trade_date: date
    name: str | None = None
    source_unit: QuantityUnit = QuantityUnit.LOTS
    lot_size: int = 1000
    margin_buy_balance_lots: float | None = None
    short_sell_balance_lots: float | None = None
    margin_buy_change_lots: float | None = None
    short_sell_change_lots: float | None = None
    # Back-compat aliases used only after notional conversion.
    margin_buy_balance: float | None = None
    short_sell_balance: float | None = None
    margin_buy_change: float | None = None
    short_sell_change: float | None = None
    margin_notional_change: float | None = None


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

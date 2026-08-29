from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


Money = Numeric(20, 4)
Ratio = Numeric(18, 8)


class Security(Base):
    __tablename__ = "securities"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    theme_links: Mapped[list["SecurityTheme"]] = relationship(back_populates="security")
    quotes: Mapped[list["DailyQuote"]] = relationship(back_populates="security")
    flows: Mapped[list["DailyInstitutionalFlow"]] = relationship(back_populates="security")
    margins: Mapped[list["DailyMargin"]] = relationship(back_populates="security")


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mapping_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)

    security_links: Mapped[list["SecurityTheme"]] = relationship(back_populates="theme")
    metrics: Mapped[list["SectorDailyMetric"]] = relationship(back_populates="theme")


class SecurityTheme(Base):
    """Many-to-many: one security may belong to multiple themes."""

    __tablename__ = "security_themes"
    __table_args__ = (UniqueConstraint("security_id", "theme_id", name="uq_security_theme"),)

    security_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("securities.id"), primary_key=True
    )
    theme_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("themes.id"), primary_key=True
    )

    security: Mapped[Security] = relationship(back_populates="theme_links")
    theme: Mapped[Theme] = relationship(back_populates="security_links")


class DailyQuote(Base):
    __tablename__ = "daily_quotes"
    __table_args__ = (UniqueConstraint("security_id", "trade_date", name="uq_quote_sec_date"),)

    security_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("securities.id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    close: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    trading_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    volume_unit: Mapped[str] = mapped_column(String(16), default="shares", nullable=False)
    trading_value_unit: Mapped[str] = mapped_column(String(16), default="twd_notional", nullable=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    security: Mapped[Security] = relationship(back_populates="quotes")


class DailyInstitutionalFlow(Base):
    __tablename__ = "daily_institutional_flows"
    __table_args__ = (UniqueConstraint("security_id", "trade_date", name="uq_flow_sec_date"),)

    security_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("securities.id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    foreign_net_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    investment_trust_net_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    dealer_net_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Shares are stored when the source publishes volume not notional.
    foreign_net_shares: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    investment_trust_net_shares: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    dealer_net_shares: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    amount_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    estimation_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_unit: Mapped[str] = mapped_column(String(16), default="shares", nullable=False)
    flow_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_net_shares: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    estimated_net_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    security: Mapped[Security] = relationship(back_populates="flows")


class DailyMargin(Base):
    __tablename__ = "daily_margins"
    __table_args__ = (UniqueConstraint("security_id", "trade_date", name="uq_margin_sec_date"),)

    security_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("securities.id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    margin_buy_balance: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    short_sell_balance: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    margin_buy_change: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    short_sell_change: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    source_unit: Mapped[str] = mapped_column(String(16), default="lots", nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    margin_buy_balance_lots: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    margin_buy_change_lots: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    margin_share_change: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    margin_notional_change: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    security: Mapped[Security] = relationship(back_populates="margins")


class SectorDailyMetric(Base):
    __tablename__ = "sector_daily_metrics"
    __table_args__ = (UniqueConstraint("theme_id", "trade_date", name="uq_sector_metric"),)

    theme_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("themes.id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    institutional_flow: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    flow_5d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    avg_5d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    avg_20d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    acceleration: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    trading_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    trading_value_avg_20d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    normalized_flow: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    price_momentum: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    volume_expansion: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    continuity: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    margin_signal: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    quadrant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lifecycle: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rotation_score: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    emerging_metric: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    divergence_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priced_member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flow_member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage_ratio: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    low_coverage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    theme: Mapped[Theme] = relationship(back_populates="metrics")


class StockDailyMetric(Base):
    __tablename__ = "stock_daily_metrics"
    __table_args__ = (UniqueConstraint("security_id", "trade_date", name="uq_stock_metric"),)

    security_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("securities.id"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    institutional_flow: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    flow_5d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    avg_5d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    avg_20d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    acceleration: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    trading_value_avg_20d: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    normalized_flow: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    price_momentum: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    volume_expansion: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    continuity: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    margin_signal: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    rotation_score: Mapped[Decimal | None] = mapped_column(Ratio, nullable=True)
    divergence_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MappingCatalog(Base):
    """Seed/production mapping provenance. Seed mappings are not a full taxonomy."""

    __tablename__ = "mapping_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_source: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    production_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    twse_quotes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tpex_quotes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    twse_flows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tpex_flows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    twse_margins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tpex_margins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


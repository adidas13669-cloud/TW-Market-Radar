from datetime import date

from pydantic import BaseModel, Field

from app.core.enums import Lifecycle, Quadrant, QuadrantLabel


class HealthResponse(BaseModel):
    status: str
    service: str = "tw-market-radar"


class ThemeMeta(BaseModel):
    theme_id: str
    name: str
    theme_level: int | None = None
    parent_theme_id: str | None = None
    theme_category: str | None = None
    concentrated_ok: bool = False


class RadarMetaResponse(BaseModel):
    asof: date | None = None
    mapping_version: str | None = None
    production_ready: bool = False
    mapping_source: str | None = None
    notes: str | None = None
    session_dates: list[date] = Field(default_factory=list)
    themes: list[ThemeMeta] = Field(default_factory=list)
    estimated_notional_caveat: str = (
        "Institutional notional may be estimated as shares × close when the exchange "
        "publishes share prints rather than TWD."
    )


class SectorRadarRow(BaseModel):
    theme_id: str
    theme_name: str | None = None
    trade_date: date
    institutional_flow: float | None = None
    flow_5d: float | None = None
    avg_5d: float | None = None
    avg_20d: float | None = None
    acceleration: float | None = None
    trading_value: float | None = None
    trading_value_avg_20d: float | None = None
    normalized_flow: float | None = None
    price_momentum: float | None = None
    volume_expansion: float | None = None
    continuity: float | None = None
    margin_signal: float | None = None
    quadrant: Quadrant | None = None
    quadrant_label: QuadrantLabel | None = None
    lifecycle: Lifecycle | None = None
    rotation_score: float | None = None
    emerging_metric: float | None = None
    divergence_flag: bool = False
    rank: float | None = None
    member_count: int | None = None
    priced_member_count: int | None = None
    flow_member_count: int | None = None
    coverage_ratio: float | None = None
    low_coverage: bool = False
    thin_membership: bool = False
    rank_excluded: bool = False
    mapping_version: str | None = None
    theme_level: int | None = None
    parent_theme_id: str | None = None
    theme_category: str | None = None
    concentrated_ok: bool = False
    parent_chain: list[str] = Field(default_factory=list)
    score_delta: float | None = None


class ConstituentRow(BaseModel):
    security_id: str
    name: str | None = None
    trade_date: date
    institutional_flow: float | None = None
    flow_5d: float | None = None
    acceleration: float | None = None
    normalized_flow: float | None = None
    price_momentum: float | None = None
    volume_expansion: float | None = None
    continuity: float | None = None
    rotation_score: float | None = None
    divergence_flag: bool = False
    rank: float | None = None


class SectorDetailResponse(BaseModel):
    sector: SectorRadarRow
    constituents: list[ConstituentRow] = Field(default_factory=list)
    parent_chain: list[ThemeMeta] = Field(default_factory=list)


class SectorHistoryResponse(BaseModel):
    theme_id: str
    sessions: list[SectorRadarRow]

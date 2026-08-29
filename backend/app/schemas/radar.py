from datetime import date

from pydantic import BaseModel, Field

from app.core.enums import Lifecycle, Quadrant, QuadrantLabel


class HealthResponse(BaseModel):
    status: str
    service: str = "tw-market-radar"


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


class ConstituentRow(BaseModel):
    security_id: str
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


class SectorHistoryResponse(BaseModel):
    theme_id: str
    sessions: list[SectorRadarRow]

from __future__ import annotations

from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import QUADRANT_LABELS, Quadrant
from app.db.session import get_db
from app.models.entities import SectorDailyMetric, SecurityTheme, StockDailyMetric, Theme
from app.schemas.radar import (
    ConstituentRow,
    SectorDetailResponse,
    SectorHistoryResponse,
    SectorRadarRow,
)
from app.services.ranking_engine import rank_descending

router = APIRouter(prefix="/api/v1")


def _sector_row(metric: SectorDailyMetric, theme_name: str | None, rank: float | None = None) -> SectorRadarRow:
    quadrant = Quadrant(metric.quadrant) if metric.quadrant else None
    return SectorRadarRow(
        theme_id=metric.theme_id,
        theme_name=theme_name,
        trade_date=metric.trade_date,
        institutional_flow=_f(metric.institutional_flow),
        flow_5d=_f(metric.flow_5d),
        avg_5d=_f(metric.avg_5d),
        avg_20d=_f(metric.avg_20d),
        acceleration=_f(metric.acceleration),
        trading_value=_f(metric.trading_value),
        trading_value_avg_20d=_f(metric.trading_value_avg_20d),
        normalized_flow=_f(metric.normalized_flow),
        price_momentum=_f(metric.price_momentum),
        volume_expansion=_f(metric.volume_expansion),
        continuity=_f(metric.continuity),
        margin_signal=_f(metric.margin_signal),
        quadrant=quadrant,
        quadrant_label=QUADRANT_LABELS.get(quadrant) if quadrant else None,
        lifecycle=metric.lifecycle,  # type: ignore[arg-type]
        rotation_score=_f(metric.rotation_score),
        emerging_metric=_f(metric.emerging_metric),
        divergence_flag=metric.divergence_flag,
        rank=rank,
        member_count=metric.member_count,
        priced_member_count=metric.priced_member_count,
        flow_member_count=metric.flow_member_count,
        coverage_ratio=_f(metric.coverage_ratio),
        low_coverage=bool(metric.low_coverage),
    )


@router.get("/radar/sectors/latest", response_model=list[SectorRadarRow])
def latest_sector_radar(
    include_low_coverage: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> list[SectorRadarRow]:
    latest = _latest_date(session)
    if latest is None:
        return []
    return _sector_snapshot(session, latest, order_by="rotation_score", include_low_coverage=include_low_coverage)


@router.get("/radar/emerging", response_model=list[SectorRadarRow])
def emerging_sectors(
    include_low_coverage: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> list[SectorRadarRow]:
    latest = _latest_date(session)
    if latest is None:
        return []
    return _sector_snapshot(session, latest, order_by="emerging_metric", include_low_coverage=include_low_coverage)


@router.get("/radar/divergence", response_model=list[SectorRadarRow])
def divergence_candidates(session: Session = Depends(get_db)) -> list[SectorRadarRow]:
    latest = _latest_date(session)
    if latest is None:
        return []
    names = _theme_names(session)
    rows = session.execute(
        select(SectorDailyMetric).where(
            SectorDailyMetric.trade_date == latest,
            SectorDailyMetric.divergence_flag.is_(True),
        )
    ).scalars().all()
    rows = [r for r in rows if not r.low_coverage]
    frame = pd.DataFrame(
        [{"theme_id": r.theme_id, "acceleration": _f(r.acceleration)} for r in rows]
    )
    ranked = rank_descending(frame, "acceleration") if not frame.empty else frame
    rank_map = {row.theme_id: _f(row.rank) for row in ranked.itertuples()} if not ranked.empty else {}
    ordered = sorted(rows, key=lambda r: rank_map.get(r.theme_id) or 1e9)
    return [_sector_row(r, names.get(r.theme_id), rank_map.get(r.theme_id)) for r in ordered]


@router.get("/radar/sectors/{theme_id}", response_model=SectorDetailResponse)
def sector_detail(theme_id: str, session: Session = Depends(get_db)) -> SectorDetailResponse:
    latest = _latest_date(session)
    if latest is None:
        raise HTTPException(status_code=404, detail="No calculated metrics")
    metric = session.get(SectorDailyMetric, {"theme_id": theme_id, "trade_date": latest})
    if metric is None:
        # composite PK get may not work on all SQLAlchemy versions; query instead
        metric = session.execute(
            select(SectorDailyMetric).where(
                SectorDailyMetric.theme_id == theme_id,
                SectorDailyMetric.trade_date == latest,
            )
        ).scalar_one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail=f"Unknown theme {theme_id}")
    names = _theme_names(session)
    member_ids = session.execute(
        select(SecurityTheme.security_id).where(SecurityTheme.theme_id == theme_id)
    ).scalars().all()
    stocks = session.execute(
        select(StockDailyMetric).where(
            StockDailyMetric.trade_date == latest,
            StockDailyMetric.security_id.in_(member_ids),
        )
    ).scalars().all()
    frame = pd.DataFrame(
        [{"security_id": s.security_id, "rotation_score": _f(s.rotation_score)} for s in stocks]
    )
    ranked = rank_descending(frame, "rotation_score") if not frame.empty else frame
    rank_map = (
        {row.security_id: _f(row.rank) for row in ranked.itertuples()} if not ranked.empty else {}
    )
    constituents = [
        ConstituentRow(
            security_id=s.security_id,
            trade_date=s.trade_date,
            institutional_flow=_f(s.institutional_flow),
            flow_5d=_f(s.flow_5d),
            acceleration=_f(s.acceleration),
            normalized_flow=_f(s.normalized_flow),
            price_momentum=_f(s.price_momentum),
            volume_expansion=_f(s.volume_expansion),
            continuity=_f(s.continuity),
            rotation_score=_f(s.rotation_score),
            divergence_flag=s.divergence_flag,
            rank=rank_map.get(s.security_id),
        )
        for s in sorted(stocks, key=lambda x: rank_map.get(x.security_id) or 1e9)
    ]
    return SectorDetailResponse(
        sector=_sector_row(metric, names.get(theme_id)),
        constituents=constituents,
    )


@router.get("/radar/sectors/{theme_id}/history", response_model=SectorHistoryResponse)
def sector_history(
    theme_id: str,
    sessions: int = Query(default=20, ge=1, le=120),
    session: Session = Depends(get_db),
) -> SectorHistoryResponse:
    names = _theme_names(session)
    rows = (
        session.execute(
            select(SectorDailyMetric)
            .where(SectorDailyMetric.theme_id == theme_id)
            .order_by(SectorDailyMetric.trade_date.desc())
            .limit(sessions)
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No history for theme {theme_id}")
    chronological = list(reversed(rows))
    return SectorHistoryResponse(
        theme_id=theme_id,
        sessions=[_sector_row(r, names.get(theme_id)) for r in chronological],
    )


def _latest_date(session: Session) -> date | None:
    value = session.execute(select(SectorDailyMetric.trade_date).order_by(SectorDailyMetric.trade_date.desc())).scalars().first()
    return value


def _theme_names(session: Session) -> dict[str, str]:
    return {t.id: t.name for t in session.execute(select(Theme)).scalars().all()}


def _sector_snapshot(
    session: Session,
    asof: date,
    order_by: str,
    include_low_coverage: bool = False,
) -> list[SectorRadarRow]:
    names = _theme_names(session)
    rows = session.execute(
        select(SectorDailyMetric).where(SectorDailyMetric.trade_date == asof)
    ).scalars().all()
    if not include_low_coverage:
        rows = [r for r in rows if not r.low_coverage]
    frame = pd.DataFrame(
        [
            {
                "theme_id": r.theme_id,
                "rotation_score": _f(r.rotation_score),
                "emerging_metric": _f(r.emerging_metric),
            }
            for r in rows
        ]
    )
    ranked = rank_descending(frame, order_by) if not frame.empty else frame
    rank_map = {row.theme_id: _f(row.rank) for row in ranked.itertuples()} if not ranked.empty else {}
    ordered = sorted(rows, key=lambda r: rank_map.get(r.theme_id) or 1e9)
    return [_sector_row(r, names.get(r.theme_id), rank_map.get(r.theme_id)) for r in ordered]


def _f(value: object) -> float | None:
    if value is None:
        return None
    return float(value)

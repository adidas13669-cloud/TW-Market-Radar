from __future__ import annotations

from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import QUADRANT_LABELS, Quadrant
from app.db.session import get_db
from app.models.entities import (
    MappingCatalog,
    SectorDailyMetric,
    Security,
    SecurityTheme,
    StockDailyMetric,
    Theme,
)
from app.schemas.radar import (
    ConstituentRow,
    RadarMetaResponse,
    SectorDetailResponse,
    SectorHistoryResponse,
    SectorRadarRow,
    ThemeMeta,
)
from app.services.persistence import current_mapping_version
from app.services.ranking_engine import rank_descending

router = APIRouter(prefix="/api/v1")


@router.get("/radar/meta", response_model=RadarMetaResponse)
def radar_meta(session: Session = Depends(get_db)) -> RadarMetaResponse:
    asof = _latest_date(session)
    version = current_mapping_version(session, asof=asof)
    catalog = session.get(MappingCatalog, version) if version else None
    dates = sorted(session.execute(select(SectorDailyMetric.trade_date).distinct()).scalars().all())
    themes = [_theme_meta(t) for t in session.execute(select(Theme).order_by(Theme.id)).scalars().all()]
    return RadarMetaResponse(
        asof=asof,
        mapping_version=catalog.mapping_version if catalog else version,
        production_ready=bool(catalog.production_ready) if catalog else False,
        mapping_source=catalog.mapping_source if catalog else None,
        notes=catalog.notes if catalog else None,
        session_dates=dates,
        themes=themes,
    )


@router.get("/radar/sectors/latest", response_model=list[SectorRadarRow])
def latest_sector_radar(
    include_low_coverage: bool = Query(default=False),
    trade_date: date | None = Query(default=None),
    mapping_version: str | None = Query(default=None),
    theme_level: int | None = Query(default=None),
    parent_theme_id: str | None = Query(default=None),
    rank_eligible: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> list[SectorRadarRow]:
    asof = trade_date or _latest_date(session)
    if asof is None:
        return []
    return _sector_snapshot(
        session,
        asof,
        order_by="rotation_score",
        include_low_coverage=include_low_coverage,
        mapping_version=mapping_version,
        theme_level=theme_level,
        parent_theme_id=parent_theme_id,
        rank_eligible=rank_eligible,
    )


@router.get("/radar/emerging", response_model=list[SectorRadarRow])
def emerging_sectors(
    include_low_coverage: bool = Query(default=False),
    trade_date: date | None = Query(default=None),
    mapping_version: str | None = Query(default=None),
    theme_level: int | None = Query(default=None),
    parent_theme_id: str | None = Query(default=None),
    rank_eligible: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> list[SectorRadarRow]:
    asof = trade_date or _latest_date(session)
    if asof is None:
        return []
    return _sector_snapshot(
        session,
        asof,
        order_by="emerging_metric",
        include_low_coverage=include_low_coverage,
        mapping_version=mapping_version,
        theme_level=theme_level,
        parent_theme_id=parent_theme_id,
        rank_eligible=rank_eligible,
    )


@router.get("/radar/divergence", response_model=list[SectorRadarRow])
def divergence_candidates(
    include_low_coverage: bool = Query(default=False),
    trade_date: date | None = Query(default=None),
    mapping_version: str | None = Query(default=None),
    theme_level: int | None = Query(default=None),
    parent_theme_id: str | None = Query(default=None),
    rank_eligible: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> list[SectorRadarRow]:
    asof = trade_date or _latest_date(session)
    if asof is None:
        return []
    rows = _sector_snapshot(
        session,
        asof,
        order_by="acceleration",
        include_low_coverage=include_low_coverage,
        mapping_version=mapping_version,
        theme_level=theme_level,
        parent_theme_id=parent_theme_id,
        rank_eligible=rank_eligible,
        divergence_only=True,
    )
    return rows


@router.get("/radar/sectors/{theme_id}", response_model=SectorDetailResponse)
def sector_detail(
    theme_id: str,
    trade_date: date | None = Query(default=None),
    mapping_version: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> SectorDetailResponse:
    asof = trade_date or _latest_date(session)
    if asof is None:
        raise HTTPException(status_code=404, detail="No calculated metrics")
    version = mapping_version or current_mapping_version(session, asof=asof)
    q = select(SectorDailyMetric).where(
        SectorDailyMetric.theme_id == theme_id,
        SectorDailyMetric.trade_date == asof,
    )
    if version:
        q = q.where(SectorDailyMetric.mapping_version == version)
    metric = session.execute(q).scalar_one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail=f"Unknown theme {theme_id}")
    themes = _themes_by_id(session)
    prev = _previous_scores(session, asof, version, [theme_id])
    names = {tid: t.name for tid, t in themes.items()}
    sector = _sector_row(metric, names.get(theme_id), themes=themes, prev_score=prev.get(theme_id))
    mq = select(SecurityTheme.security_id).where(SecurityTheme.theme_id == theme_id)
    if version:
        mq = mq.where(SecurityTheme.mapping_version == version)
    member_ids = session.execute(mq).scalars().all()
    stocks = session.execute(
        select(StockDailyMetric).where(
            StockDailyMetric.trade_date == asof,
            StockDailyMetric.security_id.in_(member_ids),
        )
    ).scalars().all()
    sec_names = {
        s.id: s.name
        for s in session.execute(select(Security).where(Security.id.in_(member_ids))).scalars().all()
    }
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
            name=sec_names.get(s.security_id),
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
    chain_ids = _parent_chain(theme_id, themes)
    return SectorDetailResponse(
        sector=sector,
        constituents=constituents[:25],
        parent_chain=[_theme_meta(themes[tid]) for tid in chain_ids if tid in themes],
    )


@router.get("/radar/sectors/{theme_id}/history", response_model=SectorHistoryResponse)
def sector_history(
    theme_id: str,
    sessions: int = Query(default=20, ge=1, le=120),
    mapping_version: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> SectorHistoryResponse:
    themes = _themes_by_id(session)
    version = mapping_version or current_mapping_version(session)
    q = select(SectorDailyMetric).where(SectorDailyMetric.theme_id == theme_id)
    if version:
        q = q.where(SectorDailyMetric.mapping_version == version)
    rows = (
        session.execute(q.order_by(SectorDailyMetric.trade_date.desc()).limit(sessions))
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No history for theme {theme_id}")
    chronological = list(reversed(rows))
    prev_map: dict[str, float | None] = {}
    out: list[SectorRadarRow] = []
    for metric in chronological:
        row = _sector_row(
            metric,
            themes[theme_id].name if theme_id in themes else theme_id,
            themes=themes,
            prev_score=prev_map.get(theme_id),
        )
        out.append(row)
        prev_map[theme_id] = row.rotation_score
    return SectorHistoryResponse(theme_id=theme_id, sessions=out)


def _latest_date(session: Session) -> date | None:
    value = session.execute(select(SectorDailyMetric.trade_date).order_by(SectorDailyMetric.trade_date.desc())).scalars().first()
    return value


def _themes_by_id(session: Session) -> dict[str, Theme]:
    return {t.id: t for t in session.execute(select(Theme)).scalars().all()}


def _theme_meta(theme: Theme) -> ThemeMeta:
    return ThemeMeta(
        theme_id=theme.id,
        name=theme.name,
        theme_level=theme.theme_level,
        parent_theme_id=theme.parent_theme_id,
        theme_category=theme.theme_category,
        concentrated_ok=bool(theme.concentrated_ok),
    )


def _parent_chain(theme_id: str, themes: dict[str, Theme]) -> list[str]:
    chain: list[str] = []
    current = themes.get(theme_id)
    while current and current.parent_theme_id:
        chain.append(current.parent_theme_id)
        current = themes.get(current.parent_theme_id)
    return list(reversed(chain))


def _descendants_and_self(root: str, themes: dict[str, Theme]) -> set[str]:
    children: dict[str, list[str]] = {}
    for tid, theme in themes.items():
        if theme.parent_theme_id:
            children.setdefault(theme.parent_theme_id, []).append(tid)
    out = {root}
    stack = [root]
    while stack:
        node = stack.pop()
        for child in children.get(node, []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def _previous_scores(
    session: Session,
    asof: date,
    version: str | None,
    theme_ids: list[str],
) -> dict[str, float | None]:
    prev_date = session.execute(
        select(SectorDailyMetric.trade_date)
        .where(SectorDailyMetric.trade_date < asof)
        .order_by(SectorDailyMetric.trade_date.desc())
    ).scalars().first()
    if prev_date is None or not theme_ids:
        return {}
    q = select(SectorDailyMetric).where(
        SectorDailyMetric.trade_date == prev_date,
        SectorDailyMetric.theme_id.in_(theme_ids),
    )
    if version:
        q = q.where(SectorDailyMetric.mapping_version == version)
    return {m.theme_id: _f(m.rotation_score) for m in session.execute(q).scalars().all()}


def _sector_snapshot(
    session: Session,
    asof: date,
    order_by: str,
    include_low_coverage: bool = False,
    mapping_version: str | None = None,
    theme_level: int | None = None,
    parent_theme_id: str | None = None,
    rank_eligible: bool = True,
    divergence_only: bool = False,
) -> list[SectorRadarRow]:
    themes = _themes_by_id(session)
    version = mapping_version or current_mapping_version(session, asof=asof)
    q = select(SectorDailyMetric).where(SectorDailyMetric.trade_date == asof)
    if version:
        q = q.where(SectorDailyMetric.mapping_version == version)
    rows = list(session.execute(q).scalars().all())
    if divergence_only:
        rows = [r for r in rows if r.divergence_flag]
    if not include_low_coverage:
        rows = [r for r in rows if not r.low_coverage]
        if rank_eligible:
            rows = [r for r in rows if not getattr(r, "rank_excluded", False)]
    allowed_levels: set[int] | None
    if theme_level is not None:
        allowed_levels = {theme_level}
    elif rank_eligible:
        allowed_levels = {2, 3}
    else:
        allowed_levels = None
    if allowed_levels is not None:
        kept = []
        for r in rows:
            level = themes[r.theme_id].theme_level if r.theme_id in themes else None
            if level is None or level in allowed_levels:
                kept.append(r)
        rows = kept
    if parent_theme_id:
        family = _descendants_and_self(parent_theme_id, themes)
        rows = [r for r in rows if r.theme_id in family]
    prev = _previous_scores(session, asof, version, [r.theme_id for r in rows])
    frame = pd.DataFrame(
        [
            {
                "theme_id": r.theme_id,
                "rotation_score": _f(r.rotation_score),
                "emerging_metric": _f(r.emerging_metric),
                "acceleration": _f(r.acceleration),
            }
            for r in rows
        ]
    )
    ranked = rank_descending(frame, order_by) if not frame.empty else frame
    rank_map = {row.theme_id: _f(row.rank) for row in ranked.itertuples()} if not ranked.empty else {}
    ordered = sorted(rows, key=lambda r: rank_map.get(r.theme_id) or 1e9)
    return [
        _sector_row(
            r,
            themes[r.theme_id].name if r.theme_id in themes else r.theme_id,
            rank=rank_map.get(r.theme_id),
            themes=themes,
            prev_score=prev.get(r.theme_id),
        )
        for r in ordered
    ]


def _sector_row(
    metric: SectorDailyMetric,
    theme_name: str | None,
    rank: float | None = None,
    themes: dict[str, Theme] | None = None,
    prev_score: float | None = None,
) -> SectorRadarRow:
    quadrant = Quadrant(metric.quadrant) if metric.quadrant else None
    theme = themes.get(metric.theme_id) if themes else None
    score = _f(metric.rotation_score)
    delta = None
    if score is not None and prev_score is not None:
        delta = score - prev_score
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
        rotation_score=score,
        emerging_metric=_f(metric.emerging_metric),
        divergence_flag=metric.divergence_flag,
        rank=rank,
        member_count=metric.member_count,
        priced_member_count=metric.priced_member_count,
        flow_member_count=metric.flow_member_count,
        coverage_ratio=_f(metric.coverage_ratio),
        low_coverage=bool(metric.low_coverage),
        thin_membership=bool(getattr(metric, "thin_membership", False)),
        rank_excluded=bool(getattr(metric, "rank_excluded", False)),
        mapping_version=getattr(metric, "mapping_version", None),
        theme_level=theme.theme_level if theme else None,
        parent_theme_id=theme.parent_theme_id if theme else None,
        theme_category=theme.theme_category if theme else None,
        concentrated_ok=bool(theme.concentrated_ok) if theme else False,
        parent_chain=_parent_chain(metric.theme_id, themes) if themes else [],
        score_delta=delta,
    )


def _f(value: object) -> float | None:
    if value is None:
        return None
    return float(value)

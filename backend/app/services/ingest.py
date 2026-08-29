"""Dated TWSE/TPEx ingest: fetch → validate → normalize → persist → score."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import IngestStatus, Market
from app.core.exceptions import NoTradingSessionError, ProviderError
from app.core.units import LOT_TO_SHARES, QuantityUnit
from app.data_providers.registry import load_theme_mapping_csv
from app.data_providers.tpex import TpexProvider, parse_tpex_flow, parse_tpex_margin, parse_tpex_quotes
from app.data_providers.twse import TwseProvider, parse_twse_flow, parse_twse_margin, parse_twse_quotes
from app.models.entities import (
    DailyInstitutionalFlow,
    DailyMargin,
    DailyQuote,
    IngestRun,
    MappingCatalog,
    Security,
    SecurityTheme,
    Theme,
)
from app.services.normalize import to_canonical_flow, to_margin_notional
from app.services.persistence import persist_calculation, snapshot_from_db
from app.services.pipeline import run_calculation
from app.services.validation import SessionValidation, validate_session

logger = logging.getLogger(__name__)

DEFAULT_MAPPING = Path("data/theme_mapping/seed_themes.csv")
DEFAULT_PAYLOAD_DIR = Path("data/raw_payloads")


def _upsert_security(session: Session, security_id: str, name: str, market: str, is_active: bool = True) -> None:
    obj = session.get(Security, security_id)
    if obj is None:
        for inst in list(session.new):
            if isinstance(inst, Security) and inst.id == security_id:
                obj = inst
                break
    if obj is None:
        session.add(Security(id=security_id, name=name, market=market, is_active=is_active))
        return
    if name and name != security_id:
        obj.name = name
    obj.market = market
    obj.is_active = is_active


@dataclass
class ProviderDayResult:
    name: str
    quotes: int = 0
    flows: int = 0
    margins: int = 0
    error: str | None = None
    holiday: bool = False


@dataclass
class IngestResult:
    trade_date: date
    providers: dict[str, ProviderDayResult] = field(default_factory=dict)
    validation: SessionValidation | None = None
    sectors_scored: int = 0
    warmup_complete: bool = False
    skipped_holiday: bool = False
    status: IngestStatus = IngestStatus.SUCCESS


def save_payload(directory: Path, trade_date: date, name: str, payload: Any) -> Path:
    folder = directory / trade_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def load_mapping_meta(mapping_path: Path = DEFAULT_MAPPING) -> dict[str, Any]:
    meta_path = mapping_path.with_name("mapping_meta.json")
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "mapping_version": "seed-v1",
        "mapping_source": str(mapping_path),
        "effective_from": "2026-06-01",
        "production_ready": False,
        "notes": "Development seed mapping. Not a production sector taxonomy.",
    }


def seed_theme_mapping(session: Session, mapping_path: Path = DEFAULT_MAPPING) -> None:
    if not mapping_path.exists():
        return
    meta = load_mapping_meta(mapping_path)
    effective = date.fromisoformat(str(meta["effective_from"])) if meta.get("effective_from") else None
    catalog = session.get(MappingCatalog, 1)
    if catalog is None:
        session.add(
            MappingCatalog(
                id=1,
                mapping_version=str(meta.get("mapping_version") or "seed-v1"),
                mapping_source=str(meta.get("mapping_source") or mapping_path),
                effective_from=effective or date(2026, 6, 1),
                production_ready=bool(meta.get("production_ready")),
                notes=meta.get("notes"),
            )
        )
    else:
        catalog.mapping_version = str(meta.get("mapping_version") or catalog.mapping_version)
        catalog.mapping_source = str(meta.get("mapping_source") or catalog.mapping_source)
        if effective:
            catalog.effective_from = effective
        catalog.production_ready = bool(meta.get("production_ready"))
        catalog.notes = meta.get("notes")
    seen_sec: set[str] = set()
    seen_theme: set[str] = set()
    for rec in load_theme_mapping_csv(mapping_path):
        if rec.theme_id not in seen_theme:
            session.merge(
                Theme(
                    id=rec.theme_id,
                    name=rec.theme_name or rec.theme_id,
                    mapping_version=str(meta.get("mapping_version") or "seed-v1"),
                    mapping_source=str(meta.get("mapping_source") or mapping_path),
                    effective_from=effective,
                )
            )
            seen_theme.add(rec.theme_id)
        if rec.security_id not in seen_sec:
            _upsert_security(session, rec.security_id, rec.security_id, Market.TWSE, True)
            seen_sec.add(rec.security_id)
        session.merge(SecurityTheme(security_id=rec.security_id, theme_id=rec.theme_id))
    session.flush()


def ingest_trade_date(
    session: Session,
    trade_date: date,
    *,
    twse: TwseProvider | None = None,
    tpex: TpexProvider | None = None,
    payload_dir: Path = DEFAULT_PAYLOAD_DIR,
    mapping_path: Path = DEFAULT_MAPPING,
    continue_on_provider_error: bool = True,
    recompute_metrics: bool = True,
    skip_if_success: bool = False,
    force: bool = False,
) -> IngestResult:
    """Fetch both venues for one calendar date. Holidays skip persist of empty sessions."""
    twse = twse or TwseProvider()
    tpex = tpex or TpexProvider()
    seed_theme_mapping(session, mapping_path)
    result = IngestResult(trade_date=trade_date)

    existing = session.get(IngestRun, trade_date)
    if skip_if_success and not force and existing is not None and existing.status == IngestStatus.SUCCESS:
        result.status = IngestStatus.SKIPPED
        result.warmup_complete = True
        logger.info("skip %s already SUCCESS", trade_date)
        return result

    quote_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    margin_rows: list[dict[str, Any]] = []

    twse_res = _ingest_provider(
        name="TWSE",
        trade_date=trade_date,
        provider=twse,
        parse_quotes=parse_twse_quotes,
        parse_flow=parse_twse_flow,
        parse_margin=parse_twse_margin,
        payload_dir=payload_dir,
        market=Market.TWSE,
        session=session,
        quote_rows=quote_rows,
        flow_rows=flow_rows,
        margin_rows=margin_rows,
        continue_on_error=continue_on_provider_error,
    )
    tpex_res = _ingest_provider(
        name="TPEX",
        trade_date=trade_date,
        provider=tpex,
        parse_quotes=parse_tpex_quotes,
        parse_flow=parse_tpex_flow,
        parse_margin=parse_tpex_margin,
        payload_dir=payload_dir,
        market=Market.TPEX,
        session=session,
        quote_rows=quote_rows,
        flow_rows=flow_rows,
        margin_rows=margin_rows,
        continue_on_error=continue_on_provider_error,
    )
    result.providers = {"TWSE": twse_res, "TPEX": tpex_res}

    if twse_res.holiday and tpex_res.holiday:
        result.skipped_holiday = True
        result.status = IngestStatus.HOLIDAY
        result.validation = SessionValidation(trade_date=trade_date)
        result.validation.add("holiday", f"{trade_date} is not a trading session", "info")
        _record_ingest_run(session, result)
        logger.info("%s HOLIDAY", trade_date)
        return result

    quotes = pd.DataFrame(quote_rows)
    flows = pd.DataFrame(flow_rows)
    margins = pd.DataFrame(margin_rows)

    prior_dates, prior_ids = _prior_quote_universe(session, trade_date)
    result.validation = validate_session(
        trade_date,
        quotes,
        flows,
        prior_quote_dates=prior_dates,
        prior_security_ids=prior_ids,
    )
    fatal = [i for i in result.validation.issues if i.severity == "error"]
    if fatal and quotes.empty:
        result.status = _classify_status(result)
        _record_ingest_run(session, result)
        logger.warning("%s %s with empty quotes", trade_date, result.status)
        return result

    _persist_raw(session, trade_date, quotes, flows, margins)
    session.flush()

    stored_dates = set(
        session.execute(select(DailyQuote.trade_date).distinct()).scalars().all()
    )
    if result.validation:
        result.validation.quote_sessions = len(stored_dates)
        result.validation.warmup_complete = len(stored_dates) >= 20
        result.validation.issues = [i for i in result.validation.issues if i.code != "warmup"]
        if not result.validation.warmup_complete:
            result.validation.add(
                "warmup",
                f"{len(stored_dates)} quote sessions stored; avg_20d/acceleration need 20",
            )

    if recompute_metrics:
        snap = snapshot_from_db(session)
        calc = run_calculation(snap)
        persist_calculation(session, calc)
        latest = calc.sector_metrics[calc.sector_metrics["trade_date"].map(lambda d: pd.Timestamp(d).date()) == trade_date]
        if latest.empty and not calc.sector_metrics.empty:
            latest = calc.sector_metrics
        result.sectors_scored = int(latest["theme_id"].nunique()) if not latest.empty else 0
        result.warmup_complete = bool(
            not latest.empty and latest["avg_20d"].notna().any()
        )
    result.status = _classify_status(result)
    _record_ingest_run(session, result)
    if result.status != IngestStatus.SUCCESS:
        logger.warning("%s %s", trade_date, result.status)
        for name, provider in result.providers.items():
            if provider.error:
                logger.warning("%s %s provider failure: %s", trade_date, name, provider.error)
    else:
        logger.info(
            "%s SUCCESS twse_q=%s tpex_q=%s",
            trade_date,
            result.providers.get("TWSE").quotes if result.providers.get("TWSE") else 0,
            result.providers.get("TPEX").quotes if result.providers.get("TPEX") else 0,
        )
    return result


def backfill(
    session: Session,
    start: date,
    end: date,
    *,
    commit_each: bool = False,
    skip_if_success: bool = True,
    **kwargs: Any,
) -> list[IngestResult]:
    results: list[IngestResult] = []
    current = start
    kwargs.setdefault("skip_if_success", skip_if_success)
    while current <= end:
        if current.weekday() < 5:
            result = ingest_trade_date(session, current, **kwargs)
            results.append(result)
            if commit_each:
                session.commit()
        current += timedelta(days=1)
    return results


def _classify_status(result: IngestResult) -> IngestStatus:
    if result.skipped_holiday:
        return IngestStatus.HOLIDAY
    quotes = sum(p.quotes for p in result.providers.values())
    errors = [p for p in result.providers.values() if p.error and not p.holiday]
    if quotes == 0:
        return IngestStatus.PROVIDER_ERROR if errors else IngestStatus.NO_DATA
    return IngestStatus.SUCCESS


def _record_ingest_run(session: Session, result: IngestResult) -> None:
    twse = result.providers.get("TWSE") or ProviderDayResult("TWSE")
    tpex = result.providers.get("TPEX") or ProviderDayResult("TPEX")
    errors = []
    for name, provider in result.providers.items():
        if provider.error:
            errors.append(f"{name}: {provider.error}")
    session.merge(
        IngestRun(
            trade_date=result.trade_date,
            status=result.status.value,
            twse_quotes=twse.quotes,
            tpex_quotes=tpex.quotes,
            twse_flows=twse.flows,
            tpex_flows=tpex.flows,
            twse_margins=twse.margins,
            tpex_margins=tpex.margins,
            error_log="; ".join(errors) if errors else None,
            notes="holiday" if result.skipped_holiday else None,
        )
    )
    session.flush()


def _ingest_provider(
    *,
    name: str,
    trade_date: date,
    provider: Any,
    parse_quotes,
    parse_flow,
    parse_margin,
    payload_dir: Path,
    market: str,
    session: Session,
    quote_rows: list[dict[str, Any]],
    flow_rows: list[dict[str, Any]],
    margin_rows: list[dict[str, Any]],
    continue_on_error: bool,
) -> ProviderDayResult:
    out = ProviderDayResult(name=name)
    try:
        q_url, q_params = provider.quotes_request(trade_date)
        q_payload = provider.fetch_payload(q_url, q_params)
        save_payload(payload_dir, trade_date, f"{name.lower()}_quotes", q_payload)
        quotes = parse_quotes(q_payload, trade_date)
        out.quotes = len(quotes)
        seen: set[str] = set()
        for rec in quotes:
            if rec.security_id not in seen:
                _upsert_security(
                    session,
                    rec.security_id,
                    rec.name or rec.security_id,
                    market,
                    is_active=not rec.is_suspended,
                )
                seen.add(rec.security_id)
            quote_rows.append(_quote_dict(rec, market))
    except NoTradingSessionError as exc:
        out.holiday = True
        out.error = str(exc)
        return out
    except ProviderError as exc:
        out.error = str(exc)
        if not continue_on_error:
            raise
        return out

    try:
        f_url, f_params = provider.flow_request(trade_date)
        f_payload = provider.fetch_payload(f_url, f_params)
        save_payload(payload_dir, trade_date, f"{name.lower()}_flow", f_payload)
        flows = parse_flow(f_payload, trade_date)
        out.flows = len(flows)
        flow_rows.extend(_flow_dict(rec) for rec in flows)
    except NoTradingSessionError:
        out.holiday = True
    except ProviderError as exc:
        out.error = (out.error + "; " if out.error else "") + str(exc)
        if not continue_on_error:
            raise

    try:
        m_url, m_params = provider.margin_request(trade_date)
        m_payload = provider.fetch_payload(m_url, m_params)
        save_payload(payload_dir, trade_date, f"{name.lower()}_margin", m_payload)
        margins = parse_margin(m_payload, trade_date)
        out.margins = len(margins)
        margin_rows.extend(_margin_dict(rec) for rec in margins)
    except NoTradingSessionError:
        pass
    except ProviderError as exc:
        out.error = (out.error + "; " if out.error else "") + str(exc)
        if not continue_on_error:
            raise
    return out


def _quote_dict(rec, market: str) -> dict[str, Any]:
    return {
        "security_id": rec.security_id,
        "trade_date": rec.trade_date,
        "market": market,
        "name": rec.name,
        "open": rec.open,
        "high": rec.high,
        "low": rec.low,
        "close": rec.close,
        "volume": rec.volume,
        "trading_value": rec.trading_value,
        "volume_unit": rec.volume_unit.value if rec.volume_unit else QuantityUnit.SHARES.value,
        "trading_value_unit": rec.trading_value_unit.value if rec.trading_value_unit else QuantityUnit.TWD_NOTIONAL.value,
        "is_suspended": rec.is_suspended,
    }


def _flow_dict(rec) -> dict[str, Any]:
    return {
        "security_id": rec.security_id,
        "trade_date": rec.trade_date,
        "foreign_net_shares": rec.foreign_net_shares,
        "investment_trust_net_shares": rec.investment_trust_net_shares,
        "dealer_net_shares": rec.dealer_net_shares,
        "raw_net_shares": rec.raw_net_shares,
        "foreign_net_amount": rec.foreign_net_amount,
        "investment_trust_net_amount": rec.investment_trust_net_amount,
        "dealer_net_amount": rec.dealer_net_amount,
        "estimated_net_amount": rec.estimated_net_amount,
        "source_unit": rec.source_unit.value if rec.source_unit else QuantityUnit.SHARES.value,
        "flow_unit": rec.flow_unit.value if rec.flow_unit else None,
        "amount_estimated": rec.amount_estimated,
        "estimation_method": rec.estimation_method,
    }


def _margin_dict(rec) -> dict[str, Any]:
    return {
        "security_id": rec.security_id,
        "trade_date": rec.trade_date,
        "source_unit": rec.source_unit.value if rec.source_unit else QuantityUnit.LOTS.value,
        "lot_size": rec.lot_size or LOT_TO_SHARES,
        "margin_buy_balance_lots": rec.margin_buy_balance_lots,
        "margin_buy_change_lots": rec.margin_buy_change_lots,
        "short_sell_balance_lots": rec.short_sell_balance_lots,
        "short_sell_change_lots": rec.short_sell_change_lots,
        "margin_buy_balance": rec.margin_buy_balance,
        "margin_buy_change": rec.margin_buy_change,
        "short_sell_balance": rec.short_sell_balance,
        "short_sell_change": rec.short_sell_change,
    }


def _persist_raw(session: Session, trade_date: date, quotes: pd.DataFrame, flows: pd.DataFrame, margins: pd.DataFrame) -> None:
    quotes_canon = quotes
    flows_canon = to_canonical_flow(flows, quotes) if not flows.empty else flows
    margins_canon = to_margin_notional(margins, quotes) if not margins.empty else margins

    ids = set()
    for frame in (quotes_canon, flows_canon, margins_canon):
        if frame is not None and not frame.empty and "security_id" in frame.columns:
            ids.update(str(s) for s in frame["security_id"].unique())
    for sid in ids:
        _upsert_security(session, sid, sid, Market.TWSE, True)

    if not quotes_canon.empty:
        for _, row in quotes_canon.iterrows():
            sid = str(row["security_id"])
            session.merge(
                DailyQuote(
                    security_id=sid,
                    trade_date=trade_date,
                    open=_dec(row.get("open")),
                    high=_dec(row.get("high")),
                    low=_dec(row.get("low")),
                    close=_dec(row.get("close")),
                    volume=_dec(row.get("volume")),
                    trading_value=_dec(row.get("trading_value")),
                    volume_unit=str(row.get("volume_unit") or "shares"),
                    trading_value_unit=str(row.get("trading_value_unit") or "twd_notional"),
                    is_suspended=bool(row.get("is_suspended")),
                )
            )
    if not flows_canon.empty:
        for _, row in flows_canon.iterrows():
            session.merge(
                DailyInstitutionalFlow(
                    security_id=str(row["security_id"]),
                    trade_date=trade_date,
                    foreign_net_amount=_dec(row.get("foreign_net_amount")),
                    investment_trust_net_amount=_dec(row.get("investment_trust_net_amount")),
                    dealer_net_amount=_dec(row.get("dealer_net_amount")),
                    foreign_net_shares=_dec(row.get("foreign_net_shares")),
                    investment_trust_net_shares=_dec(row.get("investment_trust_net_shares")),
                    dealer_net_shares=_dec(row.get("dealer_net_shares")),
                    raw_net_shares=_dec(row.get("raw_net_shares")),
                    estimated_net_amount=_dec(row.get("estimated_net_amount")),
                    amount_estimated=bool(row.get("amount_estimated")),
                    estimation_method=_str(row.get("estimation_method")),
                    source_unit=str(row.get("source_unit") or "shares"),
                    flow_unit=str(row.get("flow_unit") or "twd_notional"),
                )
            )
    if not margins_canon.empty:
        for _, row in margins_canon.iterrows():
            session.merge(
                DailyMargin(
                    security_id=str(row["security_id"]),
                    trade_date=trade_date,
                    source_unit=str(row.get("source_unit") or "lots"),
                    lot_size=int(row.get("lot_size") or LOT_TO_SHARES),
                    margin_buy_balance=_dec(row.get("margin_buy_balance")),
                    short_sell_balance=_dec(row.get("short_sell_balance")),
                    margin_buy_change=_dec(row.get("margin_buy_change")),
                    short_sell_change=_dec(row.get("short_sell_change")),
                    margin_buy_balance_lots=_dec(row.get("margin_buy_balance_lots")),
                    margin_buy_change_lots=_dec(row.get("margin_buy_change_lots")),
                    margin_share_change=_dec(row.get("margin_share_change")),
                    margin_notional_change=_dec(row.get("margin_notional_change")),
                )
            )


def _prior_quote_universe(session: Session, trade_date: date) -> tuple[set[date], set[str]]:
    rows = session.execute(select(DailyQuote.trade_date, DailyQuote.security_id)).all()
    dates = {d for d, _ in rows if d < trade_date}
    ids = {sid for d, sid in rows if d < trade_date}
    return dates, ids


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return Decimal(str(float(value)))


def _str(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value)
    return text if text not in {"", "nan", "None"} else None

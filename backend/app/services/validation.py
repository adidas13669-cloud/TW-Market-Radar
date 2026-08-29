"""Session-level data quality checks. Missing values stay missing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from app.core.units import QuantityUnit
from app.services.rotation_engine import FLOW_LONG


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "warning"


@dataclass
class SessionValidation:
    trade_date: date
    issues: list[ValidationIssue] = field(default_factory=list)
    suspended_ids: list[str] = field(default_factory=list)
    new_listing_ids: list[str] = field(default_factory=list)
    quote_sessions: int = 0
    warmup_complete: bool = False

    def add(self, code: str, message: str, severity: str = "warning") -> None:
        self.issues.append(ValidationIssue(code, message, severity))


def validate_session(
    trade_date: date,
    quotes: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    prior_quote_dates: set[date] | None = None,
    prior_security_ids: set[str] | None = None,
) -> SessionValidation:
    report = SessionValidation(trade_date=trade_date)
    prior_quote_dates = prior_quote_dates or set()
    prior_security_ids = prior_security_ids or set()

    if quotes is None or quotes.empty:
        report.add("no_quotes", f"No quotes for {trade_date}", "error")
        return report

    day = quotes[quotes["trade_date"].map(lambda d: pd.Timestamp(d).date()) == trade_date]
    if day.empty:
        report.add("no_quotes", f"No quotes for {trade_date}", "error")
        return report

    if "is_suspended" in day.columns:
        report.suspended_ids = sorted({str(s) for s in day.loc[day["is_suspended"] == True, "security_id"]})  # noqa: E712
    elif "close" in day.columns:
        report.suspended_ids = sorted({str(s) for s in day.loc[day["close"].isna(), "security_id"]})
    if report.suspended_ids:
        report.add("suspended", f"{len(report.suspended_ids)} securities unpriced/suspended on {trade_date}")

    ids = {str(s) for s in day["security_id"]}
    if prior_security_ids:
        report.new_listing_ids = sorted(ids - prior_security_ids)
        if report.new_listing_ids:
            report.add("new_listing", f"{len(report.new_listing_ids)} securities not seen in prior sessions")

    all_dates = {pd.Timestamp(d).date() for d in quotes["trade_date"]} | prior_quote_dates
    all_dates.add(trade_date)
    report.quote_sessions = len(all_dates)
    report.warmup_complete = report.quote_sessions >= FLOW_LONG
    if not report.warmup_complete:
        report.add(
            "warmup",
            f"{report.quote_sessions} quote sessions stored; avg_20d/acceleration need {FLOW_LONG}",
        )

    ordered = sorted(all_dates)
    gaps = _weekday_gaps(ordered)
    if gaps:
        report.add("calendar_gap", f"weekday gaps without quotes: {gaps[:5]}{'...' if len(gaps)>5 else ''}")

    if flows is not None and not flows.empty and "source_unit" in flows.columns:
        units = {str(u) for u in flows["source_unit"].dropna().unique()}
        if len(units) > 1:
            report.add("mixed_units", f"flow source_unit mixed: {sorted(units)}", "error")
        if QuantityUnit.LOTS.value in units:
            report.add("lot_flow", "institutional flow marked as lots", "error")

    return report


def _weekday_gaps(ordered: list[date]) -> list[str]:
    if len(ordered) < 2:
        return []
    missing: list[str] = []
    current = ordered[0]
    seen = set(ordered)
    while current < ordered[-1]:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in seen:
            missing.append(current.isoformat())
    return missing

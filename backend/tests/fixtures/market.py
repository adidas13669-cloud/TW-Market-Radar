from datetime import date, timedelta

import pandas as pd

from app.models.entities import (
    DailyInstitutionalFlow,
    DailyMargin,
    DailyQuote,
    Security,
    SecurityTheme,
    Theme,
)
from app.services.pipeline import MarketSnapshot


def make_session_calendar(n: int = 25, start: date = date(2024, 1, 2)) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def synthetic_snapshot(n_days: int = 25) -> MarketSnapshot:
    """Deterministic universe covering inflow/outflow and multi-theme membership."""
    days = make_session_calendar(n_days)
    mapping = pd.DataFrame(
        [
            {"security_id": "2330", "theme_id": "SEMI"},
            {"security_id": "2330", "theme_id": "AI"},
            {"security_id": "2454", "theme_id": "SEMI"},
            {"security_id": "2317", "theme_id": "AI"},
            {"security_id": "2603", "theme_id": "SHIP"},
        ]
    )
    themes = pd.DataFrame(
        [
            {"theme_id": "SEMI", "name": "半導體"},
            {"theme_id": "AI", "name": "AI應用"},
            {"theme_id": "SHIP", "name": "航運"},
        ]
    )

    flow_rows = []
    quote_rows = []
    margin_rows = []
    specs = {
        "2330": {"base_px": 500.0, "flow_start": 80.0, "flow_step": 4.0},
        "2454": {"base_px": 800.0, "flow_start": 20.0, "flow_step": 1.0},
        "2317": {"base_px": 100.0, "flow_start": 10.0, "flow_step": 2.0},
        "2603": {"base_px": 150.0, "flow_start": -40.0, "flow_step": -1.0},
    }
    for i, d in enumerate(days):
        for sid, spec in specs.items():
            flow = spec["flow_start"] + spec["flow_step"] * i
            close = spec["base_px"] * (1 + 0.001 * i)
            # Keep 2330 price nearly flat so AI/SEMI can show flow-price divergence.
            if sid == "2330":
                close = spec["base_px"] * (1 + 0.0001 * i)
            volume = 1_000_000 + 10_000 * i
            trading_value = close * volume
            flow_rows.append(
                {
                    "trade_date": d,
                    "security_id": sid,
                    "foreign_net_amount": flow * 0.6,
                    "investment_trust_net_amount": flow * 0.3,
                    "dealer_net_amount": flow * 0.1,
                    "source_unit": "twd_notional",
                    "flow_unit": "twd_notional",
                }
            )
            quote_rows.append(
                {
                    "trade_date": d,
                    "security_id": sid,
                    "close": close,
                    "volume": volume,
                    "trading_value": trading_value,
                }
            )
            margin_rows.append(
                {
                    "trade_date": d,
                    "security_id": sid,
                    "source_unit": "twd_notional",
                    "margin_buy_change": 5_000 * (1 if flow > 0 else -1),
                    "margin_buy_balance": 1_000_000 + i * 1_000,
                    "margin_notional_change": 5_000 * (1 if flow > 0 else -1),
                }
            )

    return MarketSnapshot(
        mapping=mapping,
        flows=pd.DataFrame(flow_rows),
        quotes=pd.DataFrame(quote_rows),
        margins=pd.DataFrame(margin_rows),
        themes=themes,
    )


def seed_snapshot(session, snapshot: MarketSnapshot) -> None:
    theme_names = {}
    if snapshot.themes is not None and not snapshot.themes.empty:
        for _, row in snapshot.themes.iterrows():
            theme_id = str(row.get("theme_id") or row.get("id"))
            name = str(row.get("name") or row.get("theme_name") or theme_id)
            theme_names[theme_id] = name
            session.merge(Theme(id=theme_id, name=name, theme_level=3, theme_category="seed", concentrated_ok=True))
    securities = set(snapshot.flows["security_id"].astype(str))
    for sid in securities:
        session.merge(Security(id=sid, name=sid, market="TWSE", is_active=True))
    for _, row in snapshot.mapping.iterrows():
        tid = str(row["theme_id"])
        if tid not in theme_names:
            session.merge(Theme(id=tid, name=tid, theme_level=3, concentrated_ok=True, theme_category="seed"))
        session.merge(SecurityTheme(security_id=str(row["security_id"]), theme_id=tid, mapping_version="seed-v1"))
    for _, row in snapshot.flows.iterrows():
        session.merge(
            DailyInstitutionalFlow(
                security_id=str(row["security_id"]),
                trade_date=pd.Timestamp(row["trade_date"]).date(),
                foreign_net_amount=row["foreign_net_amount"],
                investment_trust_net_amount=row["investment_trust_net_amount"],
                dealer_net_amount=row["dealer_net_amount"],
                source_unit="twd_notional",
                flow_unit="twd_notional",
                amount_estimated=False,
            )
        )
    for _, row in snapshot.quotes.iterrows():
        session.merge(
            DailyQuote(
                security_id=str(row["security_id"]),
                trade_date=pd.Timestamp(row["trade_date"]).date(),
                close=row.get("close"),
                volume=row.get("volume"),
                trading_value=row.get("trading_value"),
            )
        )
    if snapshot.margins is not None:
        for _, row in snapshot.margins.iterrows():
            session.merge(
                DailyMargin(
                    security_id=str(row["security_id"]),
                    trade_date=pd.Timestamp(row["trade_date"]).date(),
                    margin_buy_change=row.get("margin_buy_change"),
                    margin_buy_balance=row.get("margin_buy_balance"),
                    source_unit="twd_notional",
                    margin_notional_change=row.get("margin_buy_change"),
                )
            )
    session.flush()

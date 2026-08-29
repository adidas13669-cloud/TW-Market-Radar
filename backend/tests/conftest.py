from datetime import date, timedelta

import pandas as pd


def trading_days(n: int, start: date | None = None) -> list[date]:
    start = start or date(2024, 1, 2)
    days: list[date] = []
    current = start
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def flow_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def mapping_frame(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["security_id", "theme_id"])

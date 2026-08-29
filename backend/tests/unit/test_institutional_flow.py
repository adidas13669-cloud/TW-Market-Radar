from datetime import date

from app.services.institutional_flow import add_institutional_flow_column, institutional_flow
from tests.conftest import flow_frame


def test_institutional_flow_sums_three_legs():
    assert institutional_flow(100, 40, -10) == 130.0


def test_institutional_flow_all_missing_is_none():
    assert institutional_flow(None, None, None) is None


def test_institutional_flow_partial_treats_missing_leg_as_zero():
    assert institutional_flow(100, None, None) == 100.0


def test_add_institutional_flow_column_marks_all_missing_as_na():
    frame = flow_frame(
        [
            {
                "trade_date": date(2024, 1, 2),
                "security_id": "2330",
                "foreign_net_amount": 10,
                "investment_trust_net_amount": 5,
                "dealer_net_amount": -1,
            },
            {
                "trade_date": date(2024, 1, 2),
                "security_id": "2317",
                "foreign_net_amount": None,
                "investment_trust_net_amount": None,
                "dealer_net_amount": None,
            },
        ]
    )
    out = add_institutional_flow_column(frame)
    assert out.loc[0, "institutional_flow"] == 14.0
    assert out.loc[1, "institutional_flow"] != out.loc[1, "institutional_flow"] or out.loc[1, "institutional_flow"] is None
    assert pd_isna(out.loc[1, "institutional_flow"])


def pd_isna(value) -> bool:
    import pandas as pd

    return bool(pd.isna(value))

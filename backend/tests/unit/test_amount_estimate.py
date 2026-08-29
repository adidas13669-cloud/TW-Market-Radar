from datetime import date

import pandas as pd

from app.services.amount_estimate import estimate_amounts_from_shares


def test_estimate_amounts_from_shares_flags_and_skips_when_close_missing():
    flows = pd.DataFrame(
        [
            {
                "trade_date": date(2024, 1, 2),
                "security_id": "2330",
                "foreign_net_shares": 10,
                "investment_trust_net_shares": 2,
                "dealer_net_shares": -1,
                "foreign_net_amount": None,
                "investment_trust_net_amount": None,
                "dealer_net_amount": None,
            },
            {
                "trade_date": date(2024, 1, 2),
                "security_id": "2317",
                "foreign_net_shares": 5,
                "investment_trust_net_shares": 0,
                "dealer_net_shares": 0,
                "foreign_net_amount": None,
                "investment_trust_net_amount": None,
                "dealer_net_amount": None,
            },
        ]
    )
    quotes = pd.DataFrame(
        [
            {"trade_date": date(2024, 1, 2), "security_id": "2330", "close": 100.0},
            {"trade_date": date(2024, 1, 2), "security_id": "2317", "close": None},
        ]
    )
    out = estimate_amounts_from_shares(flows, quotes)
    a = out.loc[out["security_id"] == "2330"].iloc[0]
    assert a["foreign_net_amount"] == 1000.0
    assert bool(a["amount_estimated"]) is True
    b = out.loc[out["security_id"] == "2317"].iloc[0]
    assert pd.isna(b["foreign_net_amount"])
    assert bool(b["amount_estimated"]) is False

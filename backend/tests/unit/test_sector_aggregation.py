from datetime import date

from app.services.institutional_flow import add_institutional_flow_column, aggregate_sector_daily_flow
from tests.conftest import flow_frame, mapping_frame


def test_many_to_many_theme_mapping_counts_stock_in_each_theme():
    """A stock in two themes contributes full flow to both; no global dedupe."""
    flows = add_institutional_flow_column(
        flow_frame(
            [
                _row("A", 100),
                _row("B", 50),
                _row("C", 20),
            ]
        )
    )
    mapping = mapping_frame(
        [
            ("A", "SEMI"),
            ("A", "AI"),
            ("B", "SEMI"),
            ("C", "AI"),
        ]
    )
    sector = aggregate_sector_daily_flow(flows, mapping)
    by_theme = {row.theme_id: row for row in sector.itertuples()}
    assert by_theme["SEMI"].institutional_flow == 150
    assert by_theme["SEMI"].member_count == 2
    assert by_theme["AI"].institutional_flow == 120
    assert by_theme["AI"].member_count == 2


def test_duplicate_mapping_rows_do_not_drop_a_second_theme():
    flows = add_institutional_flow_column(flow_frame([_row("A", 100)]))
    mapping = mapping_frame([("A", "SEMI"), ("A", "AI")])
    sector = aggregate_sector_daily_flow(flows, mapping)
    assert set(sector["theme_id"]) == {"SEMI", "AI"}
    assert list(sector["institutional_flow"]) == [100, 100]


def _row(security_id: str, total: float) -> dict:
    return {
        "trade_date": date(2024, 1, 2),
        "security_id": security_id,
        "foreign_net_amount": total,
        "investment_trust_net_amount": 0.0,
        "dealer_net_amount": 0.0,
    }

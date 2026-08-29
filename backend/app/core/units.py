from enum import StrEnum

# Taiwan listed common shares: 1 board lot (張) = 1,000 shares.
LOT_TO_SHARES = 1000

ESTIMATION_SHARES_TIMES_CLOSE = "net_shares_times_close"


class QuantityUnit(StrEnum):
    SHARES = "shares"
    LOTS = "lots"
    TWD_NOTIONAL = "twd_notional"


CANONICAL_FLOW_UNIT = QuantityUnit.TWD_NOTIONAL
QUOTE_VOLUME_UNIT = QuantityUnit.SHARES
QUOTE_VALUE_UNIT = QuantityUnit.TWD_NOTIONAL
MARGIN_SOURCE_UNIT = QuantityUnit.LOTS

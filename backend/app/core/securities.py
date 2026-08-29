"""Security classification helpers. No I/O."""

from __future__ import annotations

import re

_COMMON = re.compile(r"^[1-9]\d{3}$")


def is_common_stock(security_id: str) -> bool:
    """TWSE/TPEx common shares: 4-digit codes not starting with 0.

    Excludes ETFs/ETNs (0050, 006208, 004xx), preferred (2002A), and warrants.
    """
    return bool(_COMMON.fullmatch(str(security_id).strip()))

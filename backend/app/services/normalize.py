"""Convert published share/lot prints into canonical TWD notional. No I/O."""

from __future__ import annotations

import pandas as pd

from app.core.exceptions import UnitMismatchError
from app.core.units import (
    LOT_TO_SHARES,
    QuantityUnit,
)
from app.services.amount_estimate import estimate_amounts_from_shares
from app.services.institutional_flow import FLOW_COMPONENTS, add_institutional_flow_column


def to_canonical_flow(flows: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Ensure scoring columns are TWD notional. Raw shares are preserved."""
    if flows.empty:
        out = flows.copy()
        out["flow_unit"] = pd.Series(dtype=object)
        return out

    out = flows.copy()
    if "source_unit" not in out.columns:
        # Synthetic / already-notional frames used in unit tests.
        if any(c in out.columns for c in FLOW_COMPONENTS):
            out["source_unit"] = QuantityUnit.TWD_NOTIONAL.value
            out["flow_unit"] = QuantityUnit.TWD_NOTIONAL.value
            return add_institutional_flow_column(out)
        raise UnitMismatchError("flow frame has no source_unit and no notional legs")

    units = {str(u) for u in out["source_unit"].dropna().unique()}
    if QuantityUnit.SHARES.value in units and QuantityUnit.TWD_NOTIONAL.value in units:
        raise UnitMismatchError("cannot mix raw share prints with TWD notionals in one flow frame")
    if QuantityUnit.LOTS.value in units:
        raise UnitMismatchError("institutional flow in lots is not supported; expected shares or TWD")

    if units == {QuantityUnit.TWD_NOTIONAL.value}:
        out["flow_unit"] = QuantityUnit.TWD_NOTIONAL.value
        return add_institutional_flow_column(out)

    if units == {QuantityUnit.SHARES.value}:
        estimated = estimate_amounts_from_shares(out, quotes)
        estimated["flow_unit"] = QuantityUnit.TWD_NOTIONAL.value
        estimated["source_unit"] = QuantityUnit.SHARES.value
        return add_institutional_flow_column(estimated)

    raise UnitMismatchError(f"unsupported flow source units: {sorted(units)}")


def to_margin_notional(margins: pd.DataFrame, quotes: pd.DataFrame, lot_size: int = LOT_TO_SHARES) -> pd.DataFrame:
    """margin_notional_change = lot_change * lot_size * close. Missing close stays missing."""
    if margins is None or margins.empty:
        return pd.DataFrame(columns=["trade_date", "security_id", "margin_notional_change"])
    out = margins.copy()
    if "source_unit" not in out.columns:
        if "margin_notional_change" not in out.columns:
            out["margin_notional_change"] = out.get("margin_buy_change")
        return out
    unit = QuantityUnit.LOTS.value
    if "source_unit" in out.columns and len(out["source_unit"].dropna()):
        units = {str(u) for u in out["source_unit"].dropna().unique()}
        if len(units) > 1:
            raise UnitMismatchError(f"mixed margin units: {sorted(units)}")
        unit = units.pop()

    px = quotes[["trade_date", "security_id", "close"]] if quotes is not None and not quotes.empty else pd.DataFrame()
    if not px.empty:
        out = out.merge(px, on=["trade_date", "security_id"], how="left")
    else:
        out["close"] = pd.NA

    if "margin_buy_change_lots" in out.columns:
        lots = pd.to_numeric(out["margin_buy_change_lots"], errors="coerce")
    elif unit == QuantityUnit.LOTS.value and "margin_buy_change" in out.columns:
        lots = pd.to_numeric(out["margin_buy_change"], errors="coerce")
    else:
        lots = pd.Series(pd.NA, index=out.index)

    close = pd.to_numeric(out["close"], errors="coerce")
    if unit == QuantityUnit.TWD_NOTIONAL.value:
        out["margin_notional_change"] = pd.to_numeric(
            out.get("margin_notional_change", out.get("margin_buy_change")), errors="coerce"
        )
    else:
        share_change = lots * float(lot_size)
        out["margin_share_change"] = share_change
        out["margin_notional_change"] = share_change * close
        missing_px = share_change.notna() & close.isna()
        out.loc[missing_px, "margin_notional_change"] = pd.NA
    if "close" in out.columns:
        out = out.drop(columns=["close"])
    return out


def require_canonical_flow_unit(frame: pd.DataFrame) -> None:
    from app.services.institutional_flow import require_canonical_flow_unit as _require

    _require(frame)

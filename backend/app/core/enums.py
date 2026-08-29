from enum import StrEnum


class Market(StrEnum):
    TWSE = "TWSE"
    TPEX = "TPEX"


class Quadrant(StrEnum):
    """Four-quadrant sector state from 5D flow and acceleration."""

    STRONG_INFLOW = "STRONG_INFLOW"
    SLOWING_INFLOW = "SLOWING_INFLOW"
    IMPROVING_OUTFLOW = "IMPROVING_OUTFLOW"
    ACCELERATING_OUTFLOW = "ACCELERATING_OUTFLOW"


class Lifecycle(StrEnum):
    EARLY = "EARLY"
    CONFIRMED = "CONFIRMED"
    CROWDED = "CROWDED"
    EXIT = "EXIT"


class QuadrantLabel(StrEnum):
    """Product-facing labels paired with Quadrant."""

    TIDE = "Tide"
    ROTATION = "Rotation"
    WATCH = "Watch"
    EXIT = "Exit"


QUADRANT_LABELS: dict[Quadrant, QuadrantLabel] = {
    Quadrant.STRONG_INFLOW: QuadrantLabel.TIDE,
    Quadrant.SLOWING_INFLOW: QuadrantLabel.ROTATION,
    Quadrant.IMPROVING_OUTFLOW: QuadrantLabel.WATCH,
    Quadrant.ACCELERATING_OUTFLOW: QuadrantLabel.EXIT,
}

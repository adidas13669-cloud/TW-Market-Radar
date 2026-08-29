class RadarError(Exception):
    """Base error for the radar backend."""


class ProviderError(RadarError):
    """Raised when a market data provider cannot complete a request."""


class ProviderParseError(ProviderError):
    """Raised when a provider response cannot be mapped to the internal schema."""


class MissingDataError(RadarError):
    """Raised when required inputs are absent (never filled with invented values)."""


class UnitMismatchError(RadarError):
    """Raised when share, lot, and TWD quantities would be mixed in one calculation."""


class NoTradingSessionError(ProviderError):
    """Raised when the exchange has no session for the requested calendar date (holiday/weekend)."""


class IngestValidationError(RadarError):
    """Raised when ingest validation finds a fatal issue."""

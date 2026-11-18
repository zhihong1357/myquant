"""Source adapters: read-only bridges from public market-data APIs.

Adapters fetch and parse only. They never place orders, hold credentials,
or compute statistics.
"""

from myquant.adapters.okx import (
    OKXAPIError,
    OKXCandle,
    fetch_history,
    parse_candles_response,
)

__all__ = [
    "OKXAPIError",
    "OKXCandle",
    "fetch_history",
    "parse_candles_response",
]

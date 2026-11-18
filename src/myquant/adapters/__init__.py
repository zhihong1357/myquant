"""Source adapters: read-only bridges from public market-data APIs.

Adapters fetch and parse only. They never place orders, hold credentials,
or compute statistics.
"""

from myquant.adapters.hyperliquid import (
    HyperliquidAPIError,
    HyperliquidCandle,
)
from myquant.adapters.hyperliquid import (
    candles_to_observations as hyperliquid_candles_to_observations,
)
from myquant.adapters.hyperliquid import (
    fetch_candles as fetch_hyperliquid_candles,
)
from myquant.adapters.hyperliquid import (
    parse_candles_response as parse_hyperliquid_candles_response,
)
from myquant.adapters.okx import (
    OKXAPIError,
    OKXCandle,
    fetch_history,
    parse_candles_response,
)

__all__ = [
    "HyperliquidAPIError",
    "HyperliquidCandle",
    "OKXAPIError",
    "OKXCandle",
    "fetch_history",
    "fetch_hyperliquid_candles",
    "hyperliquid_candles_to_observations",
    "parse_candles_response",
    "parse_hyperliquid_candles_response",
]

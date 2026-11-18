# Stage 4b validation replay report

- Replayed at: 2026-11-18T08:28:36.008535+00:00
- Configuration (defaults): latency 100 ms, snapshot max age 5 s, market slippage 1 bp, impact coefficient 5 bps over top-5 depth, queue-ahead fallback 0.0, fee tier Regular (VIP 0), contract value 0.01 BTC
- Order set: see `replay.py` (market buy/sell + 6-offset limit grid + at-market buy/sell limits per decision time, 1.0 contract each)

## Two-hour tape (2026-11-18 05:00-07:00 UTC, 153,971 trades)

- Orders replayed: 80
- Fills: 363 (363 book-unknown, 347 queue-unknown)
- Funding settlements crossed: 0; funding paid: 0.000000 USDT (rate input 0.00002150 per interval, read live 2026-11-18; no settlement crossed in either window, so funding is zero by construction)

| Type | Orders | Filled | Partial | Unfilled | Cancelled | Fill rate (qty) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| market | 16 | 16 | 0 | 0 | 0 | 100.0% |
| limit | 64 | 38 | 0 | 3 | 23 | 59.4% |

| Type | Fees (USDT) | Crossing (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills (count / qty) |
| --- | ---: | ---: | ---: | ---: | ---: |
| market | 5.1690 | unknown (16 orders lack a book) | 1.0338 | 0.0000 | 0 / 0.00 |
| limit | 4.9111 | unknown (38 orders lack a book) | 0.0000 | 0.0000 | 3 / 1.77 |

Cost per filled notional (fees + slippage + impact, crossing excluded where unknown):

- market: 6.2028 USDT on 10338.04 USDT filled notional = 6.00 bps
- limit: 4.9111 USDT on 24555.72 USDT filled notional = 2.00 bps

## Dense window (2026-11-18T08:14:03.554000+00:00 to 2026-11-18T08:24:02.554000+00:00, 13384 trades, 600 snapshots)

- Orders replayed: 80
- Fills: 151 (0 book-unknown, 0 queue-unknown)
- Funding settlements crossed: 0; funding paid: 0.000000 USDT (rate input 0.00002150 per interval, read live 2026-11-18; no settlement crossed in either window, so funding is zero by construction)

| Type | Orders | Filled | Partial | Unfilled | Cancelled | Fill rate (qty) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| market | 16 | 16 | 0 | 0 | 0 | 100.0% |
| limit | 64 | 18 | 0 | 0 | 46 | 28.2% |

| Type | Fees (USDT) | Crossing (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills (count / qty) |
| --- | ---: | ---: | ---: | ---: | ---: |
| market | 5.1670 | 0.0080 | 1.0334 | 0.0575 | 0 / 0.00 |
| limit | 3.2965 | -1.2900 | 0.0000 | 0.0000 | 4 / 0.07 |

Cost per filled notional (fees + slippage + impact, crossing excluded where unknown):

- market: 6.2579 USDT on 10334.09 USDT filled notional = 6.06 bps
- limit: 3.2965 USDT on 11639.57 USDT filled notional = 2.83 bps

## Independent recomputation (2026-11-18)

- The fee table was verified against the cited OKX notice
  ("Advance Notice: Spot and Futures Trading Fee Adjustment",
  published 2026-08-21, effective 2026-09-09): all 10 futures tiers
  (rates and EUR thresholds) match `fees.py` exactly; Regular
  maker 0.0200% / taker 0.0500%.
- Venue facts re-checked live: BTC-USDT-SWAP `ctVal` 0.01, tick
  0.1 USDT, min size 0.01; next funding time 2026-11-18T16:00Z
  (00/08/16 UTC grid); funding cap/floor +/-0.375%. The live
  funding rate at check time was 0.00002112 per interval, of the
  same order as the replay's recorded input 0.00002150.
- Deterministic re-runs of `replay.py` and `stress_test.py`
  reproduce both reports byte-identically except their timestamps.
- The fill rule was spot-checked with an independent plain-Python
  reimplementation (opposite-side prints only, strictly after
  arrival, before cancel, queue 0): four 2h limit orders match the
  simulator exactly on filled quantity, fill count, fill trade IDs
  and fees; the missed-fill total matches (3 prints, 1.77
  contracts); one dense-window market buy matches exactly on fill
  price, fee, slippage, impact and crossing costs.

## Limitations of this validation

- The order set is synthetic and fixed; fill rates describe the simulator's mechanics on these two windows, not any strategy.
- The 2h tape has no in-window snapshots, so all of its market fills are book-unknown (first-print fallback) and all of its limit fills use the queue-ahead fallback of 0.0 (flagged); crossing costs there are unknown, not zero.
- The dense window is ~10 minutes on one day for one instrument; nothing here generalizes beyond that.
- Funding is zero because neither window crosses a settlement; the funding calculation itself is covered by unit tests.
- Paper orders are replayed independently and do not consume tape volume for each other (see `docs/execution.md`).

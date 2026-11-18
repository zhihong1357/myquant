# Execution: conservative paper fills, fees and costs (Stage 4b)

Stage 4b builds the cost-and-realism layer on top of the Stage 4a
trade/quote foundation (`docs/microstructure.md`): a conservative
paper fill model, a verified OKX fee schedule, and cost models for
spread crossing, slippage, market impact and funding, plus latency
and stale-data stress tests. This is infrastructure and method work,
not a hypothesis study: no hypothesis was registered and no trial
run for it.

This is a cost and realism tool, not a strategy. Nothing here
optimizes anything, and no replay result implies any trading
advantage. The model exists to make paper results *less* flattering
than naive fills, by charging for the things naive fills ignore:
fees, the spread, the delay between deciding and arriving, and the
queue ahead of a resting order.

## What 4b is and is not

- **In scope:** paper orders with three clocks
  (`src/myquant/execution/orders.py`); the OKX futures fee schedule
  (`fees.py`, verified from OKX's own notice); the cost model
  (`costs.py`: crossing, slippage, impact, funding); the
  conservative fill simulator (`simulator.py`); a dense live
  snapshot dataset and validation replay
  (`research/microstructure-4b/`); latency and stale-data stress
  tests (`research/microstructure-4b/stress_test.py`).
- **Out of scope:** continuous L2 reconstruction (roadmap item 3,
  still open — snapshots are points in time, and 4b does not
  interpolate between them); a forward recorder (design only, in
  `docs/microstructure.md`); live order placement of any kind
  (forbidden by `AGENTS.md`); a funding-rate *series* (the funding
  rate is an input parameter — see below).

## Paper orders: three clocks

A `PaperOrder` carries `decision_time` (when the paper strategy
decided), `available_at` (when the order instruction was formed and
could be sent; usually equal to `decision_time`), and `arrival_time`
(`available_at + latency`, when the order reaches the book). Nothing
about the order may use market data newer than `decision_time`, and
nothing may fill before `arrival_time`. A limit order may carry a
`cancel_time`; a resting remainder is cancelled then. Orders are
market or limit, buy or sell; quantity is in contracts and must be
positive; limit orders require a positive limit price and market
orders must not carry one.

## Fill rules

The simulator replays orders against a tape of normalized `Trade`
records and a list of `BookSnapshot` records. The tape must be
sorted by (event_time, trade_id) and the snapshots by snapshot_time;
unsorted input raises instead of being silently re-sorted, because
ordering is load-bearing. Orders are replayed **independently**:
each order sees the full tape, and paper fills do not consume tape
volume for other orders. That is a simplification, valid only while
paper sizes are small relative to tape volume; it is stated here so
it is not mistaken for a modelled interaction.

### Limit orders (resting)

A resting buy fills only on prints with the opposite aggressor side
(sell prints fill bids, buy prints fill asks) at or through the
limit price, at the limit price — never better. Same-side prints
never fill a resting order, even at or through the limit: a
same-side print at the limit price means the opposite side of the
book was there, and the paper order may or may not have been the
counterparty. Assuming it was not is the conservative choice; it
understates fills for orders that would in reality have been hit,
and the bias direction is stated, not hidden.

A print exactly at the arrival instant does not fill: the order and
the print are simultaneous, and the order cannot be assumed to have
been resting first.

### Queue

The paper order is last in the queue at its price. At the limit
price, prints first consume `queue_ahead` — the resting size at
that price level in the arrival-time snapshot. When no valid
snapshot covers the arrival, `queue_ahead` falls back to the
configured parameter (default 0.0) and the fill is flagged
`queue_estimate_unknown`. A print strictly *through* the limit
price proves the whole level was swept, so it clears the queue and
fills at the limit price, bounded by the print size.

The queue rule overstates fills when the fallback is 0.0 and no
snapshot exists (the model assumes no queue ahead); the stress test
quantifies that assumption by re-running the 2h tape with a
100-contract fallback. It understates fills when the snapshot depth
overstates the queue that was actually ahead (depth can be
cancelled, and the snapshot is a point in time).

### Crossed at arrival

A limit order that crosses a valid arrival-time book (buy limit >=
best ask, sell limit <= best bid) fills immediately as a taker at
the best price plus slippage and impact, capped at the limit price:
a limit is the worst price the order accepts. With no valid book at
arrival the order rests — the model never fabricates a taker fill
from an unknown book.

### Market orders

A market order fills at arrival against a valid book snapshot (best
ask for buys, best bid for sells) plus adverse slippage and impact.
With no valid book, it fills at the first subsequent print price
(flagged `book_unknown`) plus slippage and impact; impact is then
unknown too, so it is 0 with the same flag. A market order with no
subsequent print does not fill. Market orders fill in full at one
computed price: the model does not walk the book level by level,
and the impact term is the stand-in for the depth the order would
have consumed. Walking the book is a possible refinement; it is not
in this version.

### Cancel and missed fills

A resting remainder is cancelled at `cancel_time` (prints at or
after it do not fill). An order cancelled before arrival never
becomes active. Prints in [decision_time, arrival_time) that would
have filled a limit order are recorded as `MissedFill` entries —
count, volume, price and trade ID — never silently dropped. A
missed fill is the visible cost of latency for resting orders.
Market orders record the last print price before the decision as
the decision reference.

## Fee schedule

The fee table is the OKX futures Standard Group schedule (perpetual
and expiry futures), verified from OKX's own notice: "Advance
Notice: Spot and Futures Trading Fee Adjustment", published
2026-08-21, updated 2026-08-25, effective 2026-09-09 15:00–17:00
(UTC+8), read 2026-11-18 from
https://www.okx.com/en-br/help/advance-notice-spot-and-futures-trading-fee-adjustment-eea

| Tier | Maker | Taker |
| --- | --- | --- |
| Regular (VIP 0) | 0.0200% | 0.0500% |
| VIP 1 | 0.0160% | 0.0450% |
| VIP 2 | 0.0150% | 0.0360% |
| VIP 3 | 0.0100% | 0.0280% |
| VIP 4 | 0.0080% | 0.0270% |
| VIP 5 | 0.0050% | 0.0260% |
| VIP 6 | 0.0000% | 0.0250% |
| VIP 7 | −0.0010% | 0.0230% |
| VIP 8 | −0.0025% | 0.0200% |
| VIP 9 | −0.0050% | 0.0150% |

Fees are charged on notional value (price x contracts x 0.01 BTC
per contract for BTC-USDT-SWAP), not on margin. Maker rates at
VIP 7+ are negative: a rebate for adding liquidity, not an error,
and the model returns a negative fee (a rebate) rather than zero.
The default tier is Regular (VIP 0). The table is versioned
(`version` + `effective_date` + `checked_date`) and must be
re-checked before any reuse past its checked date.

Two verification notes. First, the cited notice's thresholds are in
EUR (EEA publication); the rates are identical to the global USD
schedule, corroborated by independent reads of okx.com's fee page
(2026-09-14, 2026-09-23, 2026-10-11, 2026-11-16). The simulator
selects a tier by name, never by threshold, so the threshold
currency does not affect any result. Second, a direct read of
https://www.okx.com/fees from this machine returns the OKX US
schedule instead (spot only, Regular 0.20% / 0.35%, no futures
table) — OKX geo-redirects the fee page, which is why the notice,
not the fee page, is the cited source. Regional schedules differ
(US, EEA, SG); this table is the global/EEA Standard Group schedule.
BTC-USDT-SWAP is a Standard Group pair.

## Cost model: defaults and their reasons

Every default below is a choice, not a finding. The table states
each default with its reason in one sentence; the stress test
re-runs the replay under different values so no result depends on
any single one.

| Parameter | Default | Why this value |
| --- | --- | --- |
| `contract_value` | 0.01 BTC | Verified venue fact: `ctVal` for BTC-USDT-SWAP from OKX `/api/v5/public/instruments`, read 2026-11-18 (tick 0.1 USDT, min size 0.01). |
| `market_slippage_bps` | 1.0 bp | Adverse bps on market fills. The typical BTC perp top-of-book spread is ~0.02 bp, so 1 bp is ~50x the spread — deliberately conservative for a paper model. |
| `impact_coefficient_bps` | 5.0 bps | Impact in bps when the order equals the full top-N depth. A round, conservative starting point; uncalibrated against real executions. |
| `impact_depth_levels` | 5 | Top-5 depth is the book slice a market order would first consume; deeper levels are less certain from a snapshot. |
| `snapshot_max_age` | 5 s | A snapshot older than this is unknown, never held. Book state decorrelates in seconds; holding a stale book would fabricate quotes. |
| `queue_ahead_fallback` | 0.0 contracts | Used only when no valid snapshot covers the arrival. Zero is the neutral fallback; the stress test shows what 100 contracts does instead. |
| `latency` (per order) | 100 ms | A conservative round-trip allowance for REST-based paper trading from a non-colocated machine; a round number, scanned 0 / 100 / 500 / 1,000 ms in the stress test. |
| `funding_rate_per_interval` | 0.0 | Means "no funding input supplied", not "funding is free". The funding rate is an input parameter; see below. |

### Crossing

A market fill pays half the spread against the arrival-time mid
(buy at the ask, sell at the bid). A resting limit fill is measured
against the same mid and can show negative crossing (price
improvement: a buy below mid, a sell above mid). When no valid book
covers a fill, its crossing cost is `None` and the order total is
unknown — reported as unknown, never as zero.

### Slippage

Market fills pay `market_slippage_bps` adverse to the book (or
first-print) price. Resting limit fills pay no slippage by
construction: they fill at the limit price. The slippage term
covers the gap between the price observed at decision time and the
price actually obtained at arrival; it is a model input, not a
measurement of this venue's slippage.

### Impact

Impact is linear in the order's share of the top-N depth:
`coefficient x min(order / depth, 1)`, capped at the coefficient.
It is a model assumption, uncalibrated against real executions, and
is stated as one wherever it is used. Without a valid book the
depth is unknown, so impact is unknown (0 with the `book_unknown`
flag) rather than invented.

### Funding

Perpetual positions pay funding every 8 hours on the 00:00 / 08:00
/ 16:00 UTC grid (verified live: the next `fundingTime` read from
OKX `/api/v5/public/funding-rate` on 2026-11-18 was
2026-11-18T16:00:00Z; the per-interval cap/floor is +/-0.375%,
`maxFundingRate`/`minFundingRate` from the same endpoint). A
positive funding rate means longs pay shorts. The model computes
funding on the signed position held across each settlement, valued
at the last print price at or before the settlement.

**Data gap:** no historical funding-rate series is pulled. The rate
is an input parameter (`funding_rate_per_interval`), and any funding
figure computed with the default 0.0 is "no funding input
supplied", not a measured zero. Pulling a funding history (OKX
`/api/v5/public/funding-rate-history` is public) is a follow-up
task, not part of this PR.

## Snapshots between: the staleness rule

Snapshots are points in time. A snapshot is usable only within
`snapshot_max_age` of its snapshot time (default 5 s); older
snapshots are unknown, never held, and the book between snapshots
is unknown. The model does not interpolate between snapshots and
does not hold the last snapshot past its age. Every fill records
whether a valid book covered it, and every report discloses how
many fills were book-unknown. This is the rule the 4a interface
required 4b to state, and it is the conservative half of the
choice: holding a stale book would silently price fills off quotes
that no longer exist.

## Validation

The validation replay (`research/microstructure-4b/replay.py`)
runs a fixed, documented order set — market buy/sell plus a
6-offset limit grid per decision time, 1.0 contract each — against
both datasets and writes
`research/microstructure-4b/validation_report.md`. The stress test
(`research/microstructure-4b/stress_test.py`) replays the same set
under a grid of assumptions and writes `stress_report.md`.

**Validation results (2026-11-18, defaults: 100 ms latency, 5 s max
age, 1 bp slippage, 5 bps impact, queue fallback 0.0, Regular tier).**
80 orders per dataset (16 market, 64 limit: 6-offset grid plus
at-market buy/sell per decision time, 1.0 contract each).

- **Two-hour tape** (05:00–07:00 UTC, 153,971 trades): market
  16/16 filled; limit 38/64 filled (59.4% by quantity), 23
  cancelled, 3 unfilled (last slot — the tape ends before their
  cancel time). Market cost 6.00 bps of filled notional (5 bp fee +
  1 bp slippage; crossing unknown, impact 0 — no in-window book);
  limit cost 2.00 bps (maker fee only). Missed fills: 3 prints
  (1.77 contracts). All 363 fills book-unknown, 347 queue-unknown —
  the 4a dataset's two snapshots sit outside the window, so the 2h
  replay measures the limit-fill and latency paths, not crossing.
- **Dense window** (08:14:03–08:24:02 UTC, 13,384 trades, 600
  snapshots at ~1 s cadence): market 16/16 filled; limit 18/64
  filled (28.2%), 46 cancelled — the 60 s cancel window is short
  for grid limits 0.05%+ away. Market cost 6.06 bps (5 bp fee +
  1 bp slippage + 0.06 bp impact; crossing 0.0080 USDT in total);
  limit cost 2.83 bps (a mix of maker fills at 2 bp and
  crossed-at-arrival taker fills at 5 bp). Missed fills: 4 prints
  (0.07 contracts). Zero book-unknown and zero queue-unknown fills.
- **Funding:** 0.00 USDT in both windows — neither crosses a
  settlement (00:00 / 08:00 / 16:00 UTC). The funding calculation
  itself is covered by unit tests.

**Stress results.** Latency 0 / 100 / 500 / 1,000 ms on the dense
window: missed fills 0 / 4 / 148 / 243, limit fill rate 28.2% /
28.2% / 26.6% / 26.6% — the at-market limits lose fills they would
have had; the grid limits are unaffected within 1 s. Snapshot
max age on the full dense series (1 s cadence): no effect at 1 / 5 /
30 s. On the sparse series (every 7th snapshot, ~7 s gaps):
book-unknown fills 130 / 53 / 0 and limit fill rate 26.6% / 29.7% /
29.7% — with a valid book, some at-market limits cross at arrival
and fill as takers. Market slippage 0 / 1 / 5 bps: slippage cost
0 / 1.03 / 5.17 USDT, fill rates unchanged. Queue-ahead fallback
0 / 100 / 1,000 contracts on the 2h tape: no change in the limit
fill rate (59.4%) — the volume printed at each limit price over a
15-minute window dwarfs even a 1,000-contract queue, so the queue
assumption is not the binding constraint on this order set.

## Known limitations

- **No book history through REST.** The dense snapshot series is a
  live capture (~10 minutes); it cannot be re-pulled, and it exists
  only in the local cache. Anything needing the book outside that
  window has no book.
- **Snapshots are not continuous.** Two snapshots seconds apart can
  differ arbitrarily; the model never interpolates between them.
- **No L2 reconstruction.** 4b parses snapshots; it does not
  reconstruct the continuous book (roadmap item 3, still open).
- **No funding-rate series.** See above: funding is an input, not a
  dataset.
- **No tick-size enforcement.** The simulator accepts limit prices
  as given and does not round to the 0.1 USDT tick; the replay's
  order set rounds its own prices, but the model itself does not
  enforce it.
- **No book-walking.** Market orders fill at one computed price;
  the impact term stands in for the depth consumed.
- **Orders are independent.** Paper fills do not consume tape
  volume for other orders (see above).
- **Taker side is not intent.** `side` says which side took
  liquidity; it says nothing about who traded or why.
- **All assumptions are choices.** Every default in the cost table
  above is a modelling choice with a stated reason, not a measured
  property of the venue. Results must be re-read under different
  assumptions before being trusted — that is what the stress test
  is for.
- **Two windows, one instrument, one venue.** The validation
  datasets prove the simulator runs end to end; they do not
  characterize BTC execution costs in general.

# Microstructure: trades, quotes and order-flow metrics (Stage 4a)

Stage 4a builds the trade/quote foundation: normalized trades and
book snapshots from OKX public REST, plus descriptive trade-based
order-flow metrics bucketed by event time. This is infrastructure and
method work, not a hypothesis study: nothing here is a signal, a
prediction or a trading rule, and no hypothesis was registered and no
trial run for it.

## What 4a is and is not

- **In scope:** OKX trades/books/ticker fetching and parsing
  (`src/myquant/adapters/okx_microstructure.py`); canonical trade and
  book-snapshot records (`src/myquant/microstructure/`); bucketed
  order-flow metrics (CVD, imbalances, VWAP, large-trade share,
  intensity); a bounded validation dataset and its validation report
  (`research/microstructure-4a/`).
- **Out of scope (Stage 4b and later):** the conservative paper fill
  model, fees/spread/slippage/impact/financing, latency and stale-data
  stress tests, and continuous L2 reconstruction. 4a parses snapshots;
  it does not reconstruct the continuous book.

## Data sources (verified live, 2026-11-18)

All four endpoints are OKX public REST, no key, under source
`okx-public` v1 (registered in
`research/microstructure-4a/sources/okx-public/v1.json`).

| Endpoint | Returns | Notes |
| --- | --- | --- |
| `/market/trades` | Most recent trades (up to 500) | Newest first |
| `/market/history-trades` | Paginated trades, up to 100/page | `after=<tradeId>` pages backwards; see depth below |
| `/market/books?sz=N` | One L2 snapshot, N levels/side (N ≤ 400) | Asks ascending, bids descending; carries `seqId` |
| `/market/ticker` | Best bid/ask/last | Used to cross-check snapshots |

Trade rows carry `instId`, `tradeId`, `px`, `sz`, `side`, `ts` and
`source`. `side` is the **taker** side (`buy`/`sell`): the side of the
order that took liquidity. It is not a statement about trader identity
or intent — public trade data cannot show who traded or why. `ts` is
the match time in UTC milliseconds. `source` is `"0"` on every row
observed. Trade IDs are sequential integers with no gaps observed
between consecutive pages.

Book levels are 4-element arrays `[price, size, "0", order_count]`:
the third element is deprecated and always `"0"`; the fourth is the
number of orders at that price. The parser rejects any other shape
rather than guessing.

### Verified history-trades depth: ~90 days

The oldest trade retrievable through `/market/history-trades` for
BTC-USDT-SWAP was found by bisection on trade IDs on 2026-11-18:
**trade 2843636428, dated 2026-08-20 00:01:56 UTC**, 90.30 days before
the probe. The floor lands just after midnight UTC on exactly the
90th calendar day back, which is consistent with a rolling 90-calendar-
day retention window (the exact retention rule cannot be distinguished
from a single probe, but the date alignment is strong evidence).

Practical consequences:

- The full 90-day window cannot be pulled through REST: at the
  observed average rate of ~40 trades/s (21/s in a quiet minute,
  ~40–45/s averaged over weeks), 90 days is ~300M trades, i.e. ~3M
  pages of 100. Any REST pull must use a bounded recent window.
- The validation dataset uses two complete UTC hours (see below).
- Accumulating trade history needs a forward recorder (see "Forward
  recorder design"). A recorder started today reaches 90 days of
  history in 90 days; there is no shortcut through REST.

### Ticker cross-check

The ticker's best bid/ask prices match the books snapshot's best
bid/ask taken moments apart (sizes may differ by a few hundred
milliseconds of book movement between the two calls). Both validation
snapshots matched on price; see the validation report.

## Canonical schemas

### Trade (`src/myquant/microstructure/trades.py`)

| Field | Meaning |
| --- | --- |
| `instrument_id` | Canonical id, e.g. `crypto:btc-usdt-perp` |
| `venue` | `okx` |
| `event_time` | Match time (UTC) |
| `available_at` | Equals `event_time`: a trade is knowable when it prints on the public feed |
| `ingested_at` | When MyQuant pulled it |
| `trade_id` | Exchange trade ID (sequential) |
| `price` | Trade price, USDT, > 0 |
| `size` | Trade size, contracts, > 0 |
| `aggressor_side` | `buy` / `sell` (taker side) |
| `source_id` / `source_version` | `okx-public` / 1 |

Normalization (`normalize_trades`) sorts by trade ID, drops duplicate
trade IDs (keeping the first occurrence) and drops rows whose event
time decreases along trade-ID order. Every dropped row is counted in
`TradeNormalizationReport` (received / accepted / parse-rejected /
duplicates / non-monotonic); nothing is discarded silently. Rows the
adapter already rejected (bad side, non-positive price/size,
unparseable fields, wrong instrument) are counted as `parse_rejected`.

### BookSnapshot (`src/myquant/microstructure/books.py`)

One snapshot: `instrument_id`, `venue`, `snapshot_time`,
`available_at` (= snapshot time), `ingested_at`, `seq_id`, `asks`
(strictly ascending) and `bids` (strictly descending), each level a
`BookLevel` of `price`, `size`, `order_count`. Misordered levels are
rejected at construction; a crossed book (best bid >= best ask) or an
empty side is detected and reported as a data-quality issue on
`NormalizedBook.quality_issues`, and the snapshot is still returned —
a crossed snapshot is data (a transient exchange state or a feed
glitch), and the consumer decides how to treat it.

Derived quantities (all from the snapshot's own levels):

| Quantity | Definition |
| --- | --- |
| `best_bid` / `best_ask` | Highest bid / lowest ask; `None` if that side is empty |
| `mid` | (best bid + best ask) / 2 |
| `spread` | Best ask − best bid (price units) |
| `spread_bps` | spread / mid × 10,000 |
| `depth_bid(n)` / `depth_ask(n)` | Summed size over the top n levels |
| `imbalance(n)` | (bid depth − ask depth) / (bid depth + ask depth), in [−1, 1]; `None` when both depths are zero |
| `microprice` | (best bid × best ask size + best ask × best bid size) / (best bid size + best ask size) |

The imbalance is a descriptive depth ratio. It measures resting depth,
not intent and not future direction.

### BucketMetrics (`src/myquant/microstructure/orderflow.py`)

Buckets are aligned to UTC boundaries (a 5-minute bucket opens on a
multiple of 5 minutes past the UTC hour) and each bucket's metrics use
only the trades inside that bucket, so a bucket's values are knowable
at the bucket's close. Empty buckets between the first and last trade
are included with zero counts and `None` for ratios that need a
denominator. The bucket width must divide a UTC day evenly (1m, 5m,
1H are the defaults).

| Field | Definition | Units / range |
| --- | --- | --- |
| `trade_count` / `buy_count` / `sell_count` | Trades in the bucket | count |
| `total_volume` / `buy_volume` / `sell_volume` | Summed size | contracts |
| `cvd_delta` | buy volume − sell volume in the bucket | contracts |
| `cvd_cumulative` | Running sum of `cvd_delta` from `start_cvd` (default 0) | contracts |
| `volume_imbalance` | (buy − sell) / total volume | [−1, 1] |
| `count_imbalance` | (buy count − sell count) / trade count | [−1, 1] |
| `vwap` | Σ(price × size) / Σ(size) in the bucket | USDT |
| `large_trade_volume` | Volume from single trades with size ≥ threshold | contracts |
| `large_trade_share` | large_trade_volume / total volume | [0, 1] |
| `first_price` / `last_price` | First / last trade price in the bucket | USDT |

CVD increments are additive: summing `cvd_delta` over all buckets
gives the final cumulative CVD minus `start_cvd`. The large-trade
threshold is arbitrary — the BTC default of 1.0 contracts is a round
number, not a discovered boundary — and must be stated wherever the
metric is reported. None of these metrics is a signal: they describe
what traded, they do not predict what will trade.

## Validation dataset

`research/microstructure-4a/fetch_data.py` pulls BTC-USDT-SWAP
trades for two complete UTC hours (2026-11-18 05:00–07:00 UTC) plus
one book snapshot (sz=20) and one ticker before and after the pull.
Raw pages live only in the gitignored cache
(`data/cache/microstructure-4a/raw/`); the committed `manifest.json`
records endpoints, parameters, the time range, per-page payload
SHA-256 and RawStore record IDs, counts and the trade-ID range.
`research/microstructure-4a/validate_dataset.py` re-reads the cache
(verifying checksums), re-parses, normalizes and computes the metrics,
and writes `validation_report.md`. The manifest's own SHA-256 is not
reproducible across pulls (it embeds fetch timestamps); the data is
reproducible while the window stays inside the ~90-day depth.

**Validation results (2026-11-18).** 1,780 pages pulled in ~29 minutes;
153,971 trades in the window (trade IDs 3094107829–3094261799, exactly
contiguous — 0 missing), 28 rows before the window start and 24,001
after the window end excluded as page overshoot; 0 adapter rejections,
0 duplicate trade IDs, 0 non-monotonic event times. Mean trade rate
21.4/s over the window (a quiet 05:00–07:00 UTC period, below the
~40/s multi-week average). Buckets: 120 × 1m, 24 × 5m, 2 × 1H, none
empty. Total volume 491,235.08 contracts; final cumulative CVD
−36,499.84 contracts, with the sum of 1m CVD deltas matching exactly.
CVD direction agreed with the bucket price move in 79 of 120 1m
buckets (65.8%) — a mechanical sanity check, not prediction evidence.
Mean |VWAP − last| / last was 0.021% (max 0.091%). Both book snapshots
had a 0.1 spread (0.02 bps), no quality issues, and ticker best
bid/ask matching the snapshot. One empirical note: at the default
1.0-contract threshold the mean 1m large-trade share is 0.96, i.e.
nearly all BTC volume prints in trades of ≥ 1.0 contracts — the
default threshold is weakly discriminating for this instrument, and a
meaningful large-trade split needs a higher, empirically chosen
threshold. Full numbers: `research/microstructure-4a/validation_report.md`.

## Known limitations

- **No book history through REST.** Snapshots are points in time.
  Anything that needs the book between snapshots (queue dynamics,
  fill simulation at depth) needs the WebSocket stream.
- **No long trade history through REST.** The ~90-day window is real
  but effectively unpullable in full (~3M pages). History accumulates
  only through a forward recorder.
- **Taker side is not intent.** `side` says which side took
  liquidity; it says nothing about who traded, why, or whether the
  trade was the start or the end of a position.
- **Snapshots are not continuous.** Two snapshots seconds apart can
  differ arbitrarily; do not interpolate between them.
- **Thresholds are arbitrary.** The large-trade threshold (BTC 1.0)
  and the bucket widths (1m/5m/1H) are choices, not findings.
- **One instrument, one venue, two hours.** The validation dataset
  proves the pipeline runs end to end; it does not characterize
  BTC order flow in general.

## Forward recorder design (not implemented)

To accumulate trade history, run a forward recorder against the OKX
public WebSocket `trades` and `books` channels (free, no key). This
section is a design only: no recorder, cron job or background process
is built in this PR. Starting one is a separate decision (it is a
long-lived process with operational costs: uptime, disk, monitoring).

**Interface.**

- `Recorder(config)`: `instruments` (list of OKX instIds),
  `channels` (`trades`, `books` with depth), `out_dir` (local cache
  root), `flush_interval_seconds`, `heartbeat_timeout_seconds`.
- `Recorder.run_forever()`: connects, subscribes, and writes until
  stopped; `Recorder.stop()` flushes and closes cleanly.
- Output: append-only JSONL files per instrument per channel per UTC
  day (`trades-BTC-USDT-SWAP-2026-11-18.jsonl`), one raw message per
  line, plus a per-file SHA-256 sidecar written on rotation. Daily
  rotation bounds file size and makes retention/deletion trivial.
- A `state.json` in the output directory records the last processed
  `tradeId` per instrument and the last `seqId` per book, so a
  restart resumes without re-fetching (and can detect gaps).

**Reconnect.** On disconnect or heartbeat timeout: reconnect with
exponential backoff (1s, 2s, 4s, … capped at 60s), resubscribe, and
reconcile: for trades, backfill the gap from `/market/history-trades`
using the last recorded trade ID as the cursor (the gap is normally
seconds); for books, take a fresh REST snapshot and note the
discontinuity (book state cannot be backfilled — the stream is the
state). Every reconnect and every backfill is logged with its time
range and row counts.

**Dedup.** Trades are deduplicated by `tradeId` (the exchange ID is
unique per instrument); book messages are ordered by `seqId`, and a
message with `seqId` <= the last processed one is dropped. The
normalization layer's duplicate counting applies unchanged.

**Running it.** A single process on any always-on machine (the
research VM, or a small VPS); expected volume is ~40 trades/s per
instrument (~3.5M trades/day for BTC, roughly 500 MB/day of raw JSONL
before compression). No credentials are involved: public channels
only. Retention, compression and upload policy are deployment
decisions, not part of this design.

## Interface for Stage 4b

The fill model (Stage 4b) consumes this layer as follows:

- **Trades** (`Trade` records, ascending trade ID) are the tape the
  fill model replays: a paper order is filled against subsequent
  trades at or through its limit price, with the trade's size bounding
  the fillable quantity at each print.
- **Book snapshots** (`BookSnapshot`) supply the spread and the
  resting depth at the time of a paper order: the spread sets the
  minimum crossing cost, and the top-N depth bounds how much can fill
  without moving the price. Snapshots are sparse (REST), so 4b must
  state how it treats the time between snapshots (last snapshot held
  vs. unknown).
- **Bucket metrics** (`BucketMetrics`) are descriptive features the
  fill model may condition on (e.g. realized spread or volume regime),
  never as alpha. Any use of them in a fill or cost model must keep
  the bucket's PIT boundary: a bucket's metrics are usable only at or
  after the bucket's close.
- **What 4b must still decide:** the fill rule itself (which prints
  fill a resting paper order, and how much), the fee schedule
  (maker/taker by VIP level), the spread-crossing assumption, the
  slippage/impact model, and the latency assumption (order-to-book
  delay). None of those are fixed here.

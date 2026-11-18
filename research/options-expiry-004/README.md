# Options expiry windows: volatility and transmission (study 004)

Fourth real-data study in myquant Stage 3 (roadmap: "Options expiry and
dealer-hedging proxy study"). Research questions:

- H0005 (transmission): is lag-1 BTC perpetual return a stronger
  predictor of next-day ETH perpetual return inside Deribit monthly
  option expiry windows than outside them?
- H0006 (volatility level): is mean daily absolute log return higher on
  expiry-window days than on non-window days, for BTC (primary) and ETH
  (secondary)?

**Status: both hypotheses REJECTED.** Trial T0005 (H0005) failed all
four preregistered acceptance criteria (primary interaction −0.0358,
Holm p = 0.694, partial R² 0.00008; window-holdout OOS R² −0.00772;
net daily edge −0.0437%). Trial T0007 (H0006) failed both criteria
(BTC mean |log return| ratio 1.0001 vs the 1.15 threshold, Holm p =
1.0). Full report: `docs/studies/options-expiry-004.md`; graph edges
E0014–E0018.

Expiry window: for monthly expiry T (last Friday of the month,
settlement 08:00 UTC), the set of OKX bar-open dates in [T-3, T] (four
calendar days). The window indicator is known at the bar's open because
the expiry calendar is public in advance (point-in-time correct).

Mechanism red line: the expiry window is only a PROXY for
dealer-hedging intensity. Deribit public data reports whole-market
per-contract open interest and Greeks, not dealer positions, so no claim
about dealer net gamma, dealer positions or hedging flow can be verified
from public data. This study tests the expiry-window effect itself;
any hedging interpretation is inference, not observation. In crypto,
forced buying and selling are dominated by perpetual liquidations, open
interest and funding rates; options gamma is only an environment
variable.

## Layout

- `preregister.py` — registers the OKX and Deribit sources,
  instruments/calendar (three perpetuals plus the BTC/ETH DVOL indices)
  and hypotheses H0005 and H0006. Run once, before any expiry-window
  result is computed.
- `fetch_data.py` — pulls OKX daily/1H candles, Deribit instrument
  listings and DVOL points into the local gitignored cache and writes
  `manifest.json` (committed; endpoints, parameters, date ranges,
  payload SHA-256, calendar verification) and `panel-summary.json`
  (counts only).
- `run_trial.py` — runs trial T0005 through `ExperimentRunner`, bound to
  H0005 v1 and the data/config fingerprints.
- `run_trial_h0006.py` — runs trial T0007 through `ExperimentRunner`,
  bound to H0006 v1 and the data/config fingerprints. (The first H0006
  attempt ran as T0006 and failed inside the experiment on a
  bootstrap-weights bug; it is recorded as a failed trial in the
  ledger, and the corrected rerun is T0007.)
- `sources/`, `catalog/`, `hypotheses/` — registry roots (committed).
- `trials.jsonl` — hash-chained trial ledger (committed).
- `manifest.json` — fetch manifest (committed).
- `panel-summary.json` — panel counts only, no raw prices (committed).

Raw payloads and PIT parquet live only in the local cache
(`data/cache/options-expiry-004/`, gitignored) and are never committed:
`raw/` holds the RawStore; `pit-1d/`, `pit-1h/` and `pit-dvol/` hold the
ParquetPITStores (one store per frequency/grid — daily and hourly
observations share event times but carry different values, and DVOL
points sit on a 00:00 UTC grid).

## Timestamp conventions

- OKX daily bars open at 16:00 UTC; OKX 1H bars open on the UTC hour.
  Deribit settles Friday 08:00 UTC, so the T-day daily return spans the
  settlement moment: the T-1 bar's interval contains the settlement and
  the T bar is the first full post-settlement bar.
- `event_time` = bar open; `available_at` = bar close (open + bar
  duration); `ingested_at` = pull time. Only confirmed (OKX `confirm=1`)
  bars enter the panel; forming bars are excluded.
- DVOL daily points are timestamped at 00:00 UTC; a point's close
  becomes knowable at the next day's 00:00 UTC. DVOL is aligned to the
  expiry calendar by calendar date and is descriptive only.
- Daily windows are half-open, aligned to 16:00 UTC bar opens:
  train [2021-01-21, 2024-01-01), validation [2024-01-02, 2025-01-01),
  holdout [2025-01-02, 2026-11-18), each separated by a one-day purge
  gap. The daily panel starts at SOL's first confirmed OKX bar
  (2021-01-21T16:00Z); BTC and ETH history goes back further, but the
  synchronized three-instrument panel cannot start earlier.
- The 1H window is [2025-01-02T00:00Z, 2026-11-18T00:00Z), aligned with
  the daily holdout start; it covers about 22 monthly expiries and is
  used for the H0005 1H robustness test only.

## Expiry calendar

The calendar is rule-constructed (last Friday of each calendar month,
08:00 UTC), not pulled from historical contracts: Deribit's
`get_instruments` with `expired=true` returns only the most recent batch
of expired contracts and cannot reconstruct the historical calendar. The
rule was cross-checked two ways on 2026-11-18: (a) the listed forward
monthly/quarterly expiries all fall on last Fridays and the BTC and ETH
expiry sets are identical; (b) the official Deribit Contract
Introduction Policy states the same last-Friday rule. The verification
record is in `manifest.json` (`deribit_instruments.calendar_verification`).

## Test families (Holm, target FWER 0.05)

H0005 (3 tests):

1. A (primary): daily BTC→ETH interaction test (BTC[t] × window[t]).
2. B: daily BTC→ETH partial lead-lag on expiry-window rows only.
3. C: 1H BTC→ETH interaction test.

H0006 (2 tests):

1. (a) (primary): BTC mean daily |log return|, window vs non-window.
2. (b): ETH mean daily |log return|, window vs non-window.

Descriptive only, not in either family: the wide-window (T-5..T+1)
sensitivity, quarterly-vs-monthly and subperiod splits, and DVOL around
expiry. H0006 has no walk-forward evaluation and no cost gate: it is a
volatility-level comparison, not a forecast.

## Running

From the repo root, with the dev environment installed:

```bash
.venv/bin/python research/options-expiry-004/preregister.py
.venv/bin/python research/options-expiry-004/fetch_data.py
.venv/bin/python research/options-expiry-004/run_trial.py         # T0005
.venv/bin/python research/options-expiry-004/run_trial_h0006.py   # T0007
```

Preregistration must precede any expiry-window result. Coverage checks
(date ranges, bar counts, missing bars) are the only
pre-preregistration data contact allowed. Trials record the HEAD commit
as their code revision, so run them with a clean worktree.

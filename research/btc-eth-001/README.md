# BTC/ETH perpetual cross-market transmission (study 001)

First real-data study in myquant Stage 3. Research question: do daily
BTC-USDT perpetual returns at lag 1 predict next-day ETH-USDT perpetual
returns beyond ETH's own history and a common-factor control?

Direction choice: thesis 001 originally planned a MOVE/VIX/VXN
rates/volatility study. The user chose the crypto-perpetual direction
instead for Stage 3's first empirical study; the thesis framework (six-step
identification flow, H0, evidence policy) still applies, and MOVE/VIX/VXN
remains a planned item on the roadmap.

## Layout

- `preregister.py` — registers the OKX source, instruments/calendar and
  hypothesis H0001. Run once, before any result-level analysis.
- `fetch_data.py` — pulls OKX candles into the local gitignored cache and
  writes `manifest.json` (committed; endpoints, parameters, date ranges and
  payload SHA-256 so anyone can re-pull and verify the confirmed candles —
  the manifest's own hash is not reproducible across pulls because it embeds
  the fetch timestamp and the still-forming bar; the confirmed data and the
  panel are).
  Daily for BTC/ETH/SOL, 1H for BTC/ETH/SOL (SOL 1H is the common-factor
  control for the 1H robustness test).
- `run_trial.py` — runs trial T0001 through `ExperimentRunner`, bound to
  H0001 v1 and the data/config fingerprints.
- `sources/`, `catalog/`, `hypotheses/` — registry roots (committed).
- `trials.jsonl` — hash-chained trial ledger (committed).
- `manifest.json` — fetch manifest (committed).
- `panel-summary.json` — panel counts only, no raw prices (committed).

Raw payloads and PIT parquet live only in the local cache at
`data/cache/btc-eth-001/` (gitignored) and are never committed: `raw/`
holds the RawStore, `pit-1d/` and `pit-1h/` hold one ParquetPITStore per
frequency (daily and hourly observations share 16:00 UTC event times but
carry different values, so they must not share a store — PIT revision
resolution would silently collapse the hourly value into the daily one).

## Timestamp conventions

- OKX daily bars open at 16:00 UTC (midnight UTC+8); the bar labelled
  `2026-11-16T16:00Z` covers 16:00 UTC 16 Nov to 16:00 UTC 17 Nov.
- `event_time` = bar open; `available_at` = bar close (open + bar duration);
  `ingested_at` = pull time. Only confirmed (`confirm=1`) bars enter the
  panel; forming bars are excluded.
- Daily windows are half-open and aligned to 16:00 UTC bar opens:
  train [2023-01-01, 2025-01-01), validation [2025-01-02, 2026-01-01),
  holdout [2026-01-02, 2026-11-18), each separated by a one-day purge gap.
- 1H bars open on the UTC hour; the 1H robustness window is fixed at
  [2026-08-20T00:00Z, 2026-11-18T00:00Z).

## Test family (Holm, target FWER 0.05)

1. Primary: daily BTC→ETH partial lead-lag (lag 1, SOL common-factor control).
2. Secondary: daily BTC→SOL partial lead-lag.
3. Robustness: 1H BTC→ETH partial lead-lag.

The volatility-regime split (trailing 30-day ETH realized vol, median split)
is descriptive only and is not in the test family. SOL is itself driven by
BTC and may absorb part of the transmission effect; the no-factor result is
reported as an upper-bound control.

## Running

From the repo root, with the dev environment installed:

```bash
.venv/bin/python research/btc-eth-001/preregister.py
.venv/bin/python research/btc-eth-001/fetch_data.py
.venv/bin/python research/btc-eth-001/run_trial.py
```

Preregistration must precede any result-level analysis. Coverage checks
(date ranges, bar counts, missing bars) are the only pre-preregistration
data contact allowed.

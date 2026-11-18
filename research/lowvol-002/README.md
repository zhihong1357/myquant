# Low-volatility regime-conditional transmission (study 002)

Second real-data study in myquant Stage 3. Research question: does lag-1
BTC perpetual return predict the next-bar target perpetual return more
strongly in low-volatility regimes than in high-volatility regimes?

Origin: study 001's post-hoc descriptive split (BTC→ETH daily, trailing
30-day ETH volatility, full-sample median) showed a low-volatility
correlation of 0.149 versus −0.003 in high volatility. That observation
is the hypothesis source, not evidence. This study re-preregisters the
idea and tests it on fresh dimensions — a new pair (daily BTC→SOL) and
a new frequency (1H BTC→ETH) — with a PIT-correct regime rule. The
original BTC→ETH daily pair is reserved for a forward-only test (H0003,
pending).

## Layout

- `preregister.py` — registers the OKX and Hyperliquid sources,
  instruments/calendar and hypotheses H0002 (main) and H0003 (forward).
  Run once, before any regime-conditional result is computed.
- `fetch_data.py` — pulls Hyperliquid daily candles into the local
  gitignored cache and writes `manifest.json` (committed; endpoints,
  parameters, date ranges, payload SHA-256, plus the OKX input state
  read from study 001's manifest at fetch time) and `panel-summary.json`
  (counts only). The OKX cache is restored by re-running study 001's
  fetch script; study 001's committed manifest is left untouched.
- `run_trial.py` — runs trial T0002 through `ExperimentRunner`, bound to
  H0002 v1 and the data/config fingerprints.
- `run_trial_h0003.py` — runs trial T0003 for H0003 when the forward
  sample is ready (60 low-volatility forward rows); refuses without
  recording anything until then.
- `check_h0003_sample.py` — counts forward rows only (no test
  statistics) and records the check in `h0003-sample-check.json`.
- `sources/`, `catalog/`, `hypotheses/` — registry roots (committed).
- `trials.jsonl` — hash-chained trial ledger (committed).
- `manifest.json` — fetch manifest (committed).
- `panel-summary.json` — panel counts only, no raw prices (committed).

Raw payloads and PIT parquet live only in the local cache
(`data/cache/lowvol-002/` for Hyperliquid, `data/cache/btc-eth-001/` for
OKX, both gitignored) and are never committed: `raw/` holds the
RawStore, `pit-1d-hl/` holds the Hyperliquid daily ParquetPITStore.

## Timestamp conventions

- OKX daily bars open at 16:00 UTC; Hyperliquid daily bars open at
  00:00 UTC. The two daily grids do not align; test C builds its panel
  from Hyperliquid data alone.
- `event_time` = bar open; `available_at` = bar close (open + bar
  duration); `ingested_at` = pull time. Only confirmed (OKX `confirm=1`)
  or closed, traded (Hyperliquid) bars enter the panel; forming bars and
  zero-trade backfilled marks are excluded.
- Daily windows are half-open, aligned to 16:00 UTC bar opens (OKX):
  train [2023-01-01, 2025-01-01), validation [2025-01-02, 2026-01-01),
  holdout [2026-01-02, 2026-11-18), each separated by a one-day purge gap.
- 1H bars open on the UTC hour; the 1H window is [2026-08-20T00:00Z,
  2026-11-18T00:00Z), split at 2026-10-19T00:00Z (first 60 days / last
  30 days) for a descriptive stability check.

## Regime rule (PIT-correct)

Study 001's descriptive split used the full-sample median of trailing
volatility, which leaks future information into a predictive test. Here:

- Daily: RV30[t] is the sample standard deviation of the target's
  trailing 30 returns ending at t; lowvol[t] is RV30[t] below the median
  of the trailing 252 RV30 values strictly before t. The first 281
  return rows carry no label.
- 1H: RV30[t] is the standard deviation of the trailing 720 hourly
  returns; lowvol[t] is RV30[t] below the expanding median of all prior
  RV30 values (at least 30 of them). The first 749 return rows carry no
  label.

## Test family (Holm, target FWER 0.05)

1. A1 (primary): daily BTC→SOL interaction test.
2. A2: daily BTC→SOL partial lead-lag on low-volatility rows only.
3. B1: 1H BTC→ETH interaction test.
4. B2: 1H BTC→ETH partial lead-lag on low-volatility rows only.

The Hyperliquid cross-venue check (test C) is descriptive only and is
not in the family: same-period Hyperliquid prices are highly correlated
with OKX prices, so it can only rule out venue-specific data problems,
not serve as independent evidence.

## Running

From the repo root, with the dev environment installed:

```bash
.venv/bin/python research/lowvol-002/preregister.py
.venv/bin/python research/btc-eth-001/fetch_data.py   # restore OKX cache
.venv/bin/python research/lowvol-002/fetch_data.py    # Hyperliquid
.venv/bin/python research/lowvol-002/run_trial.py     # T0002
.venv/bin/python research/lowvol-002/check_h0003_sample.py  # H0003 readiness
```

Preregistration must precede any regime-conditional result. Coverage
checks (date ranges, bar counts, missing bars) are the only
pre-preregistration data contact allowed.

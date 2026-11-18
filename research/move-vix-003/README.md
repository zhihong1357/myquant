# MOVE/VIX/VXN conditional repricing (study 003)

Third real-data study in myquant Stage 3, and thesis 001's original H2:
does a lag-1 log change in rates implied volatility predict the next-day
VIX log change beyond VIX's own history and the SPX common-factor
control?

Rate-volatility source: the MOVE index has no free source (Yahoo `^MOVE`
is an ETF, Stooq is JS-blocked, FRED has no MOVE series), so the study
uses the CBOE TYVIX history from FRED series `VXTYN` (2003-01-02 to
2020-05-15). TYVIX measures expected volatility of 10-year Treasury
futures *prices*; MOVE measures yield volatility — the substitution is
approximate and is stated as a limitation in the report. See
`docs/studies/move-vix-transmission-003.md` for the full substitution
chain.

## Layout

- `preregister.py` — registers the FRED and Yahoo Finance sources,
  instruments/calendar and hypothesis H0004 (v1, then the v2 amendment
  pinning the SPX factor to the predictor day). Run once, before any
  result-level analysis.
- `fetch_data.py` — pulls five FRED series and Yahoo ^GSPC daily closes
  into the local gitignored cache and writes `manifest.json` (committed;
  endpoints, parameters, date ranges, payload SHA-256) and
  `panel-summary.json` (counts only).
- `run_trial.py` — runs trial T0004 through `ExperimentRunner`, bound to
  H0004 v2 and the data/config fingerprints. (T0003 is reserved for
  H0003's forward trial in study 002.)
- `sources/`, `catalog/`, `hypotheses/` — registry roots (committed).
- `trials.jsonl` — hash-chained trial ledger (committed).
- `manifest.json` — fetch manifest (committed).
- `panel-summary.json` — panel counts only, no raw prices (committed).

Raw payloads and PIT parquet live only in the local cache
(`data/cache/move-vix-003/`, gitignored) and are never committed: `raw/`
holds the RawStore, `pit-1d/` holds the daily ParquetPITStore.

## Timestamp conventions

- FRED daily values are closing values dated `observation_date`; Yahoo
  daily bars are timestamped at the market open (09:30 ET). Both are
  recorded at a shared event time of 21:00 UTC (16:00 ET close, fixed;
  DST is not modelled), with `available_at` equal to the event time.
  FRED's actual publication lag is not modelled (stated limitation).
- Daily windows are half-open, aligned to 21:00 UTC closes: train
  [2003-01-02, 2012-01-01), validation [2012-01-02, 2017-01-01),
  holdout [2017-01-02, 2020-05-15), each separated by a one-day purge gap.
- Weekly bars are Friday closes (last trading day of the week when Friday
  is a holiday), week-over-week log changes.

## Missing values

FRED fredgraph CSVs carry one row per weekday with an **empty** value
field on market holidays (not `"."` as FRED's API documentation
suggests; the adapter treats both as missing). Empty-value counts over
the window: VIXCLS 158, VXNCLS 161, VXTYN 169, DGS10 185, BAA10Y 186.
Yahoo ^GSPC had 0 null closes. Missing rows are excluded at fetch time
and counted; no forward filling anywhere. The synchronized panel drops
54 close rows (partial holidays where some series trade and others do
not).

## Test family (Holm, target FWER 0.05)

1. (a) Primary: daily TYVIX→VIX partial lead-lag, SPX control.
2. (b) Secondary: daily TYVIX→VXN partial lead-lag, SPX control.
3. (c) Robustness: weekly TYVIX→VIX partial lead-lag, SPX control.

The cost gate is informational, not a verdict criterion: volatility
indices are not tradable and no free VIX futures series exists, so roll
costs cannot be measured. The reverse placebo (VIX→TYVIX), sub-period
stability, rolling-percentile claim check, z-score robustness and
factor-timing sensitivity are descriptive only and are not in the family.

## Running

From the repo root, with the dev environment installed:

```bash
.venv/bin/python research/move-vix-003/preregister.py
.venv/bin/python research/move-vix-003/fetch_data.py
.venv/bin/python research/move-vix-003/run_trial.py     # T0004
```

Preregistration must precede any result-level analysis. Coverage checks
(date ranges, bar counts, missing values) are the only
pre-preregistration data contact allowed.

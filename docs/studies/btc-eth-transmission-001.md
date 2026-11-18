# BTC/ETH perpetual cross-market transmission (study 001)

- **Study:** `research/btc-eth-001/` — hypothesis **H0001 v1**, trial **T0001**
- **Verdict: REJECTED.** No evidence that lag-1 BTC perpetual daily returns
  predict next-day ETH perpetual returns beyond ETH's own history and a
  common-factor control. All four preregistered acceptance criteria failed.
- **Status:** hypothesis H0001 v1 transitioned to REJECTED after trial T0001.

## Question

Do daily BTC-USDT perpetual returns at lag 1 contain incremental
information about next-day ETH-USDT perpetual returns beyond ETH's own
history and a common-factor control?

- **H0:** Lagged BTC daily returns have no incremental predictive value for
  next-day ETH returns over ETH's own history and the common-factor control,
  after costs and dependence controls.
- **H1:** Lagged BTC daily returns explain a positive, out-of-sample
  component of next-day ETH returns beyond ETH's own lagged return and the
  SOL common-factor control.

This is Stage 3's first empirical study. Thesis 001 originally planned a
MOVE/VIX/VXN rates/volatility study; the user chose the crypto-perpetual
direction instead. The thesis framework (six-step identification flow, H0,
evidence policy) still applies, and MOVE/VIX/VXN remains a planned item.

## Data and provenance

- **Source:** OKX public REST (`okx-public` v1), no API key. Endpoints
  `/market/candles` and `/market/history-candles` for `BTC-USDT-SWAP`,
  `ETH-USDT-SWAP`, `SOL-USDT-SWAP`.
- **Sample:** daily bars 2023-01-01 → 2026-11-18 (1,416 confirmed bars per
  instrument); 1H bars 2026-08-20 → 2026-11-18 (2,160 confirmed bars per
  instrument). Zero missing bars on either grid.
- **Panels:** daily log-return panel 1,415 rows (2023-01-02 → 2026-11-16);
  hourly panel 2,159 rows (2026-08-20T01:00Z → 2026-11-17T23:00Z). The single
  dropped return row on each panel is the first row (no prior close).
- **Raw payloads and PIT parquet** live only in the local gitignored cache
  (`data/cache/btc-eth-001/`); they are not committed. The committed
  `manifest.json` records every fetch (endpoint, parameters, date ranges,
  payload SHA-256) so anyone can re-pull and verify the confirmed candles:
  a re-pull on 2026-11-18 reproduced 108 of 111 payload pages byte-identical
  (the 3 differing pages are the newest daily pages, whose still-forming bar
  had moved) and the same panel counts. Note the manifest's own SHA-256 is
  not reproducible across pulls: it embeds the fetch timestamp, and record
  hashes embed ingestion time. What is reproducible is the confirmed data
  and every number in this report.
  Manifest SHA-256: `1b0a735d1f6683d18ba3727e76fa1d9dc4a6decaae9688b3a7a41cc98456ccc9`.
- **Quality:** 21,240 daily + 32,400 hourly observation rows, no quality
  issues, no missing expected series.

## Timestamp conventions

- OKX daily bars open at **16:00 UTC** (midnight UTC+8). The bar labelled
  `2026-11-16T16:00Z` covers 16:00 UTC 16 Nov to 16:00 UTC 17 Nov. 1H bars
  open on the UTC hour.
- `event_time` = bar open; `available_at` = bar close (open + bar duration);
  `ingested_at` = pull time. Only confirmed (`confirm=1`) bars enter the
  panel; forming bars are excluded.
- Daily windows are half-open, aligned to 16:00 UTC bar opens, each
  separated by a one-day purge gap: train [2023-01-01, 2025-01-01),
  validation [2025-01-02, 2026-01-01), holdout [2026-01-02, 2026-11-18).
  The 1H window is [2026-08-20T00:00Z, 2026-11-18T00:00Z).
- Daily and hourly observations live in separate PIT stores (`pit-1d/`,
  `pit-1h/`): they share 16:00 UTC event times but carry different values,
  so sharing one store would silently collapse the hourly value into the
  daily one under PIT revision resolution.

## Definitions and transformations

- **Returns:** close-to-close log returns, computed per instrument on its
  own series before synchronization; a return is admitted only when its two
  closes are exactly one bar apart, so no multi-bar return enters the panel.
- **Missing-data policy:** no forward filling; incomplete synchronized rows
  are dropped and the dropped count is reported (0 close rows, 1 return row
  per panel — the structural first row).
- **Primary test:** partial lead-lag OLS of ETH[t+1] on ETH[t] and SOL[t]
  (base) versus the same plus BTC[t] (augmented), lag 1, Newey-West HAC
  standard errors (max lag 5 daily, 12 hourly). The SOL factor is the return
  over the same bar as the source BTC return — both are known at the
  decision time, so no future information enters.
- **Test family (Holm, target FWER 0.05):** (a) daily BTC→ETH with SOL
  control (primary); (b) daily BTC→SOL with ETH control (secondary; the
  third asset mirrors test (a)'s control structure); (c) 1H BTC→ETH with
  SOL control (robustness). No-factor versions of each test are reported as
  upper-bound controls.
- **Walk-forward:** purged chronological splits, initial train 365 rows,
  test windows 90 rows, 1-day embargo. A regression row's label (the ETH
  return over the next bar) is known two days after the row's bar open, so
  `label_end = decision_time + 2 days` for purging. OOS R² is scored on all
  folds and, for the acceptance criterion, on the preregistered holdout
  window only.
- **Cost gate:** sign rule on holdout OOS augmented forecasts, 1x, always
  invested while positioned. Entry from flat and final exit cost one taker
  side each (0.05%); a direction flip costs a full round trip (0.10%).
  The 0.05% OKX VIP0 taker fee is a labelled assumption from the public fee
  schedule (okx.com/fees, checked 2026-11-18), not verified for any account.
  Funding, slippage and market impact are ignored (stated limitations).
- **Volatility split (descriptive only, not in the test family):** trailing
  30-day realized volatility of ETH log returns, median split; regime
  statistics are descriptive, with no p-values.

## Results

### Step 1 — Naive scan (descriptive)

Correlation between BTC[t] and ETH[t+k], daily, n = 1,415 at lag 0:

| lag | 0 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| correlation | 0.811 | 0.066 | 0.030 | 0.003 | 0.015 | 0.044 |

Same-day co-movement is strong (0.811); the raw lag-1 correlation is small
(0.066) and vanishes under controls (below).

### Steps 3–4 — Partial lead-lag tests

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) daily BTC→ETH, SOL control | 1,414 | 0.0252 | 0.0697 | 0.36 | 0.718 | 1.0 | 0.00011 | 0.00011 |
| (a) no-factor control | 1,414 | 0.0317 | 0.0668 | 0.47 | 0.635 | — | 0.00020 | 0.00020 |
| (b) daily BTC→SOL, ETH control | 1,414 | 0.0648 | 0.1213 | 0.53 | 0.593 | 1.0 | 0.00038 | 0.00038 |
| (b) no-factor control | 1,414 | −0.0311 | 0.0891 | −0.35 | 0.727 | — | 0.00014 | 0.00014 |
| (c) 1H BTC→ETH, SOL control | 2,158 | −0.0150 | 0.0918 | −0.16 | 0.870 | 1.0 | 0.00003 | 0.00003 |
| (c) no-factor control | 2,158 | −0.0154 | 0.1008 | −0.15 | 0.878 | — | 0.00003 | 0.00003 |

No test in the family rejects. The primary coefficient (0.025 ± 0.070) is
consistent with zero, and its partial R² (0.00011) is 45x below the
preregistered minimum effect size of 0.005. The no-factor upper-bound
controls are equally null, so the null is not an artefact of the SOL factor
absorbing the effect. The 1H test agrees with the daily test (coefficient
near zero, wrong sign). Base-model R² is ~0.005 daily and ~0.0003 hourly:
next-bar returns are close to unpredictable on both grids, as expected.

### Step 5 — Purged walk-forward OOS

12 folds, 0 skipped, 1,049 test rows. All-folds incremental OOS R² is
**−0.00212**; holdout-only (4 folds, 318 rows) is **−0.00095** (baseline MSE
0.000887 vs augmented MSE 0.000888). Per-fold incremental OOS R²: 3 of 12
folds positive (best +0.0057), 9 negative — no stability in either direction.
Adding lag-1 BTC does not improve out-of-sample forecasts; it slightly
worsens them.

### Step 6 — Cost gate

Sign rule on the 318 holdout OOS days: 150 flips, gross daily edge
−0.0397%, total trading cost 15.1% over the holdout (0.0475%/day), net daily
edge **−0.0872%**, block-bootstrap 95% CI [−0.44%, +0.28%], bootstrap
p = 0.657 (block length 10, 2,000 resamples, seed 42). The edge is negative
before costs and more negative after them; the interval comfortably includes
zero.

### Volatility split (descriptive only)

Median trailing 30-day ETH volatility 0.0295. Low-vol regime (n = 693):
BTC[t]–ETH[t+1] correlation 0.149, OLS slope 0.202, R² 0.0223. High-vol
regime (n = 692): correlation −0.0027, slope −0.0035, R² 0.00001.

This split was observed post hoc and is **not** a finding: it carries no
p-value, was not in the test family, and was not adjusted for multiple
comparisons. It is recorded here only as a hypothesis-generating observation
for a possible future preregistered study (e.g., whether transmission is
stronger in low-volatility regimes). It does not change this study's verdict.

## Verdict against the preregistered criteria

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted primary p < 0.05 | 1.0 | no |
| Primary partial R² ≥ 0.005 | 0.00011 | no |
| Holdout OOS incremental R² > 0 | −0.00095 | no |
| Net daily edge after costs > 0 | −0.0872%/day | no |

All four acceptance criteria failed; all four complementary rejection
criteria triggered. **H0001 v1 is REJECTED.** There is no evidence of
lag-1 BTC→ETH daily transmission on the OKX perpetual market over
2023–2026, and no evidence at the 1H frequency either. The result is a
null, not a failure of method: the sample is large (1,414 daily
observations), the design was preregistered, and the null survives with and
without the common-factor control, in-sample and out-of-sample, before and
after costs.

## Limitations

- **Single venue, single grid.** OKX only; daily bars anchored at 16:00 UTC.
  Transmission at other intraday horizons (minutes) or on other venues is
  not tested. The 1H window covers only 90 days.
- **SOL factor caveat.** SOL is itself driven by BTC and may absorb part of
  the transmission effect. The no-factor controls bound this concern and
  are equally null.
- **Linear, lag-1 only.** The test is a linear lag-1 effect. Nonlinear,
  longer-lag, or volatility-mediated transmission is not tested.
- **Cost model is stylized.** Funding rates (which can exceed taker fees),
  slippage and market impact are ignored; log returns proxy 1x P&L. All of
  these would make the net edge worse, not better.
- **HAC p-values are asymptotic.** With n = 1,414 the asymptotics are
  comfortable, but the p-values are not exact.
- **The low-vol regime observation is post hoc** (see above) and must not be
  traded on or cited as evidence without a fresh preregistration.

## Reproducibility

- Preregistration: `research/btc-eth-001/preregister.py` → H0001 v1,
  spec fingerprint
  `1938d1bd8e5aef94c938ef0576987fa42f6d0f02649cd4955cb432511a21d008`,
  registration hash
  `126672f6dd160c2b69cd53a5296eadecf36e562959a114152dbc43e7cd65f45c`.
- Fetch: `research/btc-eth-001/fetch_data.py` → `manifest.json`
  (SHA-256 `1b0a735d…56ccc9`, full value in the Data section above).
- Trial: `research/btc-eth-001/run_trial.py` → trial T0001, ledger record
  `7cf678cdaffae790217827a2b3c3c7b5ab27231972f27edb9407bb1229c8dd1d`,
  code revision `5aae4adb8b17bcd22c89d40ef17638809268d7a5`,
  config fingerprint
  `7bdf6fa68f4cca617ed06dd34fae54f18c733e198821d79929e415d66b89da84`.
- Re-run from the repo root (after `fetch_data.py` restores the local
  cache): `.venv/bin/python research/btc-eth-001/run_trial.py`. The trial
  refuses to run twice under the same trial id; the ledger is the permanent
  record.

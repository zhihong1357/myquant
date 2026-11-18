# Low-volatility regime-conditional transmission (study 002)

- **Study:** `research/lowvol-002/` — hypothesis **H0002 v1**, trial **T0002**
- **Verdict: REJECTED.** No evidence that lag-1 BTC perpetual returns
  predict next-bar target returns more strongly in low-volatility
  regimes. One of four preregistered acceptance criteria passed (the
  out-of-sample criterion); the primary test, the effect-size threshold
  and the cost gate all failed.
- **Status:** hypothesis H0002 v1 transitioned to REJECTED after trial T0002.
  Hypothesis **H0003 v1** (forward BTC→ETH test) remains REGISTERED and
  pending; its trial runs when 60 low-volatility forward rows exist.

## Question

Study 001 found no unconditional lag-1 BTC→ETH daily transmission, but
its post-hoc descriptive split suggested the effect might concentrate in
low-volatility regimes (BTC[t]–ETH[t+1] correlation 0.149 in low
volatility versus −0.003 in high volatility, n ≈ 693 per regime). That
observation was computed on the full OKX 2023–2026 sample with a
full-sample median split, so it cannot be re-tested on the same data.
This study turns it into a preregistered hypothesis and tests it on
fresh dimensions:

- **H0:** Lag-1 BTC returns have no regime-dependent incremental
  predictive value: the interaction coefficient is zero and lag-1 BTC
  does not predict target returns within low-volatility rows, beyond the
  target's own history and the common-factor control, after costs and
  dependence controls.
- **H1:** The lag-1 BTC coefficient is larger in low-volatility regimes
  than in high-volatility regimes (positive interaction), and lag-1 BTC
  explains a positive out-of-sample component of next-bar target returns
  within low-volatility rows.

## What is fresh here, and what is not

- **Fresh:** the pair (daily BTC→SOL was never regime-split) and the
  frequency (study 001 never split the 1H panel by regime).
- **Not fresh:** the regime definition. The 30-day volatility window and
  the median-split rule mirror study 001's descriptive split; only the
  pair and frequency are new.
- **Not independent evidence:** the Hyperliquid cross-venue check (test
  C). Same-period Hyperliquid prices are highly correlated with OKX
  prices, so it can only rule out OKX-venue-specific data problems. The
  genuinely clean test is H0003's forward sample, which is pending.
- **Changed from study 001:** the regime rule. Study 001's descriptive
  split used the full-sample median of trailing volatility — acceptable
  for description, but it leaks future information into a predictive
  test (a row's label at t would depend on volatility observed after t).
  This study's rule uses only strictly prior data (see below).

## Data and provenance

- **Sources:** OKX public REST (`okx-public` v1) and Hyperliquid public
  REST (`hyperliquid-public` v1), no API keys. OKX endpoints
  `/market/candles` and `/market/history-candles` for `BTC-USDT-SWAP`,
  `ETH-USDT-SWAP`, `SOL-USDT-SWAP`; Hyperliquid `POST /info`
  `candleSnapshot` for `BTC`, `ETH`, `SOL` daily bars.
- **Sample (OKX):** daily bars 2023-01-01 → 2026-11-18 (1,416 confirmed
  bars per instrument); 1H bars 2026-08-20 → 2026-11-18 (2,160 confirmed
  bars per instrument). Zero missing bars on either grid. The OKX cache
  was restored by re-running study 001's fetch script; study 001's
  committed manifest is untouched, and this study's manifest records the
  OKX fetch state at trial time (manifest SHA-256
  `03a125f619957510c24e8742bf151387a846273432b17d861e09d67638dd9973`).
- **Sample (Hyperliquid):** daily bars from the first traded bar per
  coin (BTC/ETH 2023-02-26, SOL 2023-03-04) → 2026-11-17 (1,361 / 1,361 /
  1,355 bars). Pre-launch candles carry zero trades and zero volume
  (backfilled marks, no venue price discovery): 56 excluded for BTC/ETH,
  62 for SOL. Zero missing bars after the first traded bar.
- **Panels:** OKX daily log-return panel 1,415 rows (2023-01-02 →
  2026-11-16); OKX hourly panel 2,159 rows (2026-08-20T01:00Z →
  2026-11-17T23:00Z); Hyperliquid daily panel 1,354 rows (2023-03-05 →
  2026-11-17; 6 close rows dropped because SOL starts 6 days after
  BTC/ETH, plus the structural first return row).
- **Raw payloads and PIT parquet** live only in the local gitignored
  caches (`data/cache/lowvol-002/` and `data/cache/btc-eth-001/`); they
  are not committed. The committed `manifest.json` records every fetch
  (endpoint, parameters, date ranges, payload SHA-256) so anyone can
  re-pull and verify the confirmed candles. As in study 001, the
  manifest's own SHA-256 is not reproducible across pulls (it embeds the
  fetch timestamp); what is reproducible is the confirmed data and every
  number in this report.
  Manifest SHA-256: `8e0c235525dba56492bd025efdcafa3d5512eb4fd551b310977584f78239a814`.
- **Quality:** 20,385 Hyperliquid observation rows, no quality issues, no
  missing expected series.

## Timestamp conventions

- OKX daily bars open at **16:00 UTC**; Hyperliquid daily bars open at
  **00:00 UTC**. The two daily grids do not align; test C builds its
  panel from Hyperliquid data alone. 1H bars open on the UTC hour.
- `event_time` = bar open; `available_at` = bar close (open + bar duration);
  `ingested_at` = pull time. Only confirmed (OKX `confirm=1`) or closed,
  traded (Hyperliquid) bars enter the panel; forming bars and zero-trade
  marks are excluded.
- Daily windows are half-open, aligned to 16:00 UTC bar opens, each
  separated by a one-day purge gap: train [2023-01-01, 2025-01-01),
  validation [2025-01-02, 2026-01-01), holdout [2026-01-02, 2026-11-18).
  The 1H window is [2026-08-20T00:00Z, 2026-11-18T00:00Z), split at
  2026-10-19T00:00Z (first 60 days / last 30 days) for a descriptive
  stability check.

## Definitions and transformations

- **Returns:** close-to-close log returns, computed per instrument on its
  own series before synchronization; a return is admitted only when its two
  closes are exactly one bar apart.
- **Missing-data policy:** no forward filling; incomplete synchronized rows
  are dropped and the dropped count is reported.
- **Regime rule (PIT-correct):** RV30[t] is the sample standard deviation
  of the target's trailing 30 returns ending at t (720 hourly returns
  for 1H). Daily lowvol[t] is RV30[t] below the median of the trailing
  252 RV30 values strictly before t; 1H lowvol[t] is RV30[t] below the
  expanding median of all prior RV30 values (at least 30 of them). The
  current value is never included in its own threshold. Rows without a
  label are excluded: the first 281 daily return rows and the first 749
  hourly return rows. Label counts: daily 1,134 labelled rows (615 low /
  519 high), 1,133 regression rows; 1H 1,410 labelled rows (940 low /
  470 high), 1,409 regression rows; Hyperliquid 1,073 labelled rows (527
  low / 546 high).
- **Primary test (A1):** interaction OLS of SOL[t+1] on SOL[t], ETH[t]
  (factor control), BTC[t] and BTC[t]×lowvol[t], Newey-West HAC standard
  errors (max lag 5 daily, 12 hourly), testing the interaction
  coefficient. Partial R² is the nested comparison against the model
  without the interaction. (The specification follows the preregistration
  exactly: no separate lowvol main effect is included, so the interaction
  coefficient is the slope difference between regimes.)
- **Subsample tests (A2/B2):** partial lead-lag on low-volatility rows
  only, built by aligning regression rows first and then subsetting (the
  existing `partial_lead_lag` primitive aligns internally and cannot take
  a row mask, so the nested comparison is assembled from the OLS/HAC
  primitives; it reproduces `partial_lead_lag` exactly on the same rows).
- **Test family (Holm, target FWER 0.05):** A1 daily BTC→SOL interaction
  (primary), A2 daily BTC→SOL low-volatility subsample, B1 1H BTC→ETH
  interaction, B2 1H BTC→ETH low-volatility subsample. No-factor versions
  of each test are reported as upper-bound controls.
- **Walk-forward:** purged chronological splits over the labelled daily
  regression rows, initial train 365 rows, test windows 90 rows, 1-day
  embargo, label_end = decision_time + 2 days. Base model excludes the
  interaction; augmented model includes it. The acceptance criterion is
  the incremental OOS R² on low-volatility holdout rows only.
- **Cost gate:** sign rule on holdout OOS augmented forecasts, 1x,
  positioned on low-volatility holdout rows only and flat on
  high-volatility rows. Entry from flat and final exit cost one taker
  side each (0.05%); a direction flip costs a full round trip (0.10%).
  The 0.05% OKX VIP0 taker fee is a labelled assumption from the public
  fee schedule (okx.com/fees, checked 2026-11-18), not verified for any
  account. Funding, slippage and market impact are ignored (stated
  limitations). The net daily edge is averaged over all holdout test
  rows, including flat high-volatility rows.
- **Cross-venue check (test C, descriptive only):** Hyperliquid daily
  BTC→ETH low-volatility subsample regression (SOL factor control).
  Correlation, OLS slope, R² and the factor-controlled coefficient are
  reported; no p-values, not in the test family.

## Results

### Four-test family

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 daily BTC→SOL interaction, ETH control | 1,133 | 0.2217 | 0.1227 | 1.81 | 0.071 | 0.283 | 0.00376 | 0.00374 |
| A1 no-factor control | 1,133 | 0.2168 | 0.1230 | 1.76 | 0.078 | — | 0.00360 | 0.00359 |
| A2 daily BTC→SOL low-vol subsample, ETH control | 615 | 0.2004 | 0.1862 | 1.08 | 0.282 | 0.845 | 0.00422 | 0.00421 |
| A2 no-factor control | 615 | 0.1276 | 0.1652 | 0.77 | 0.440 | — | 0.00226 | 0.00226 |
| B1 1H BTC→ETH interaction, SOL control | 1,409 | 0.0332 | 0.1213 | 0.27 | 0.785 | 1.0 | 0.00015 | 0.00015 |
| B1 no-factor control | 1,409 | 0.0388 | 0.1134 | 0.34 | 0.733 | — | 0.00021 | 0.00021 |
| B2 1H BTC→ETH low-vol subsample, SOL control | 940 | −0.0046 | 0.1608 | −0.03 | 0.977 | 1.0 | 0.00000 | 0.00000 |
| B2 no-factor control | 940 | −0.0151 | 0.1640 | −0.09 | 0.927 | — | 0.00003 | 0.00003 |

No test in the family rejects. A1 is the closest: the interaction
coefficient is positive (0.22 ± 0.12, the expected direction) with a raw
p of 0.071, but the Holm-adjusted p is 0.283 and its partial R² (0.00376)
is below the preregistered 0.005 threshold. A2, the direct test of the
low-volatility subsample on the same pair, is clearly null (p = 0.282),
so the A1 near-miss does not survive its own companion test. The 1H
tests are cleanly null: B2's coefficient is −0.005, effectively zero.
The no-factor upper-bound controls agree with the factor-controlled
results throughout, so the nulls are not artefacts of the factor control
absorbing the effect.

### 1H stability (descriptive only)

B1 interaction coefficient on the preregistered 1H split: first 60 days
−0.330 (n = 690, partial R² 0.00033); last 30 days +0.017 (n = 719,
partial R² 0.00002). The sign flips between halves; there is no stable
regime-conditional pattern at 1H.

### Purged walk-forward OOS

9 folds, 0 skipped, 768 test rows. All-folds incremental OOS R² is
**+0.00067**; holdout-only (4 folds, 318 rows) is **+0.01126**; the
preregistered criterion — low-volatility holdout rows only (193 rows) —
is **+0.01041** (baseline MSE 0.001045 vs augmented MSE 0.001034). Per-fold
incremental OOS R²: 6 of 9 folds positive (best +0.0255), 3 negative
(worst −0.0160). The interaction model forecasts slightly better than the
no-interaction baseline out of sample, but the improvement is small and
the per-fold pattern is mixed.

### Cost gate

Sign rule on the 318 holdout OOS days (193 low-volatility days): 77
flips, gross daily edge −0.0332%, total trading cost 8.4% over the
holdout, net daily edge **−0.0596%**, block-bootstrap 95% CI [−0.39%,
+0.27%], bootstrap p = 0.720 (block length 10, 2,000 resamples, seed 42).
The edge is negative before costs and more negative after them. A
positive OOS R² with a negative trading edge means the forecasts improve
squared error slightly but carry no sign accuracy worth trading — which
is why the verdict requires both criteria, not either one alone.

### Cross-venue check (test C, descriptive only)

Hyperliquid daily BTC→ETH low-volatility subsample (n = 527): raw
correlation 0.047, OLS slope 0.077, R² 0.00216; factor-controlled
coefficient **−0.107** (wrong sign), partial R² 0.00135. The descriptive
correlation is far weaker than study 001's OKX descriptive observation
(0.149), and the controlled coefficient points the other way. The venue,
the daily grid (00:00 UTC vs 16:00 UTC) and the regime rule (trailing
median vs full-sample median) all differ, so this is a qualitative
contrast, not a decomposition — but it does not support the hypothesis.

## Verdict against the preregistered criteria

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted A1 p < 0.05 | 0.283 | no |
| A1 interaction partial R² ≥ 0.005 | 0.00376 | no |
| Low-vol holdout OOS incremental R² > 0 | +0.01041 | yes |
| Net daily edge after costs > 0 | −0.0596%/day | no |

One of four criteria passed. **H0002 v1 is REJECTED.** There is no
evidence of regime-conditional BTC transmission on the new pair or the
new frequency: the primary interaction is not significant after
correction, its effect size is below threshold, the direct subsample
test is null, the 1H tests are null, the cross-venue controlled
coefficient is negative, and the trading rule loses money. The single
passing criterion (a small positive OOS R²) does not rescue the verdict:
the preregistered criteria are conjunctive, and the OOS improvement does
not survive the cost gate.

## H0003 (forward test, pending)

H0003 preregisters the original BTC→ETH daily pair for bars observed
after 2026-11-18T16:00Z, with the same PIT-correct regime rule and the
same interaction + subsample structure (2-test Holm family, no
walk-forward or cost-gate criterion — the forward sample is too small
for them). The trial runs when 60 low-volatility forward rows exist
(about 120 days of new bars, expected around 2027-03). Sample check on
2026-11-18: 0 forward rows, 0/60 low-volatility rows, not ready
(`research/lowvol-002/h0003-sample-check.json`). The trial script
(`run_trial_h0003.py`) and the sample-size check script
(`check_h0003_sample.py`, counts only, no test statistics) are delivered
in this study; no H0003 trial has run.

One recorded detail for the future trial run: the H0003 spec's
`holdout_window` starts 2026-11-19T16:00Z (a structural requirement of
the spec schema), while the fixed parameter `forward_window_start` is
2026-11-18T16:00Z and the exclusion text uses the same date. The trial
and sample-check scripts use the fixed parameter (2026-11-18T16:00Z) as
the operative cutoff; the one-bar difference is noted here so the
future run is unambiguous.

## Limitations

- **Regime labels are persistent.** The 720-hour trailing volatility
  behind the 1H labels barely moves within the 90-day window, and the
  expanding median adapts slowly, so the 1H split is 940 low-volatility
  rows versus 470 high (67/33), not the near-even split the daily rule
  produces (615/519). The effective sample size for the regime dimension
  at 1H is small; the 1H null is still informative (the coefficients are
  near zero), but the design has less power than the row counts suggest.
- **The regime definition is inherited, not fresh.** The 30-day window
  and median-split rule mirror study 001's post-hoc descriptive split.
  A different window or threshold could behave differently; this study
  tests the inherited rule on new pairs and frequencies, nothing more.
- **No low-volatility main effect.** The preregistered interaction
  specification omits the regime dummy's main effect, so the interaction
  coefficient is the slope difference between regimes under the
  assumption of equal regime intercepts. Daily log-return means are near
  zero in both regimes, so the practical impact is small, but the
  specification choice is recorded here.
- **Single grid per venue.** OKX daily bars anchor at 16:00 UTC,
  Hyperliquid at 00:00 UTC; transmission at other intraday horizons or
  on other grids is not tested. The 1H window covers only 90 days.
- **Cost model is stylized.** Funding rates (which can exceed taker
  fees), slippage and market impact are ignored; log returns proxy 1x
  P&L. All of these would make the net edge worse, not better.
- **HAC p-values are asymptotic.** With n = 1,133 (daily) and n = 1,409
  (1H) the asymptotics are comfortable, but the p-values are not exact.
- **A1 is a near-miss, not a finding.** The raw p of 0.071 and the
  positive OOS R² are the only hints in the hypothesis's favour, and
  both are below their preregistered bars. They motivate H0003's forward
  test; they do not change this study's verdict.

## Reproducibility

- Preregistration: `research/lowvol-002/preregister.py` → H0002 v1,
  spec fingerprint
  `08b43b7d4769885f86e37007783ece903b42eec772783a6124b14032b06a82df`,
  registration hash
  `874353f1b3c652e0e05632466e24db86b60892efd24444e8c205bb1d019c9ae0`;
  H0003 v1, spec fingerprint
  `488dbf031f23a0544ae281643e54debefcfcad41f1337eb11492206f52aec4d0`,
  registration hash
  `85f51033a3b13e4075f8ce7677278346b09212a7e3acfcdaac37b9c6652b9550`.
- Fetch: `research/lowvol-002/fetch_data.py` → `manifest.json`
  (SHA-256 `8e0c2355…39a814`, full value in the Data section above).
  OKX cache restored with `research/btc-eth-001/fetch_data.py`.
- Trial: `research/lowvol-002/run_trial.py` → trial T0002, ledger record
  `1240f8d7a520897f5525c3ca8be9dcc1145c32fb8c420e8e8e7497af823d5024`,
  code revision `edccf22730fb2346604058ee0e6dea17a7b872a4`,
  config fingerprint
  `b23e3a34cad80e8e4dcfc873dbf48081cb8c90f52a53b035b6c850fb3be728bd`.
- Re-run from the repo root (after the fetch scripts restore the local
  caches): `.venv/bin/python research/lowvol-002/run_trial.py`. The trial
  refuses to run twice under the same trial id; the ledger is the
  permanent record.
- H0003 readiness: `.venv/bin/python
  research/lowvol-002/check_h0003_sample.py` (counts only); trial:
  `.venv/bin/python research/lowvol-002/run_trial_h0003.py` (refuses
  until 60 low-volatility forward rows exist).

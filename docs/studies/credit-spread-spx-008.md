# BAA10Y → SPX credit-spread transmission (study 008)

- **Study:** `research/credit-spread-spx-008/` — hypothesis **H0013 v1**,
  trial **T0016**
- **Verdict: REJECTED.** No evidence that the latest available BAA10Y
  spread change predicts next-day SPX returns beyond SPX's own history and
  the lagged VIX control. The primary coefficient is essentially zero
  (+1.8e-05 per bp, p = 0.89) with the wrong sign, and its partial R² is
  228x below the preregistered minimum effect size. Two of four
  preregistered acceptance criteria pass, but both by a hair on noise (see
  the verdict section); the two decisive criteria fail by orders of
  magnitude.
- **Status:** hypothesis H0013 v1 transitioned to REJECTED after trial
  T0016.

This is the planner's (6a) rank-1 candidate pair and the first real use of
the 6c experiment-assistant scaffold. Scaffold feedback from this first
real use is recorded in its own section below.

## Question

Does the most recent BAA10Y spread change available at the close contain
incremental information about the next-day SPX log return, beyond SPX's
own history and the lagged VIX common-factor control?

- **H0:** Lagged BAA10Y changes have no incremental predictive value for
  next-day SPX returns over the S&P 500's own history and the lagged VIX
  common-factor control, after costs and dependence controls.
- **H1:** The lagged BAA10Y change (basis points, latest available at the
  decision close) has a negative coefficient in the daily BAA10Y→SPX
  partial lead-lag regression (spread widening predicts weaker next-day
  SPX returns), with partial R-squared at least 0.005 and a positive
  holdout out-of-sample incremental R-squared. Note on wording: the
  planner draft's "positive, out-of-sample component" refers to positive
  incremental explanatory power (incremental R-squared above zero), not to
  a positive coefficient — the expected coefficient sign is negative.

BAA10Y is a credit spread (BAA corporate yield minus the 10-year Treasury
yield, in percentage points), so the predictor is its daily *level change*
in basis points, not a log return — a spread has no meaningful log return.
(The planner draft's `target_definition` named the "daily log return of
BAA10Y"; that was wrong for a spread and was corrected in the
preregistration — see the scaffold-feedback section.)

## Data and provenance

- **Sources:** FRED fredgraph CSV, no key, no custom User-Agent
  (`fred` v1): BAA10Y and VIXCLS. Yahoo query2 chart endpoint
  (`yahoo-finance` v1), `User-Agent: Mozilla/5.0`: ^GSPC, with the
  study-003 fail-fast checks (meta longName must be "S&P 500", closes
  must be positive).
- **Fetch:** 2026-11-19T00:25:01Z (2026-11-18 19:25 EST, after the US
  close). BAA10Y: 5,968 values, 261 missing (empty fields), 2003-01-02 →
  2026-11-17. VIX: 6,042 values, 187 missing, same window. SPX: 6,009 bars
  fetched, 6,008 in the window (the 2026-11-18 bar is excluded by the
  half-open window end), 0 missing.
- **Panels:** synchronized close panel 5,961 rows (87 dropped close rows);
  log-return panel 5,960 rows (2003-01-03 → 2026-11-17, 88 dropped return
  rows — the 87 incomplete close rows plus the structural first row). The
  regression frame drops the first 2 panel rows (no lagged BAA10Y change
  exists there): 5,958 rows, 2003-01-07 → 2026-11-17. The panel size is
  close to the planner's estimate of 5,967 joint rows.
- **Raw payloads and PIT parquet** live only in the local gitignored cache
  (`data/cache/credit-spread-spx-008/`); they are not committed. The
  committed `manifest.json` records every fetch (endpoint, parameters,
  date ranges, payload SHA-256).
  Manifest SHA-256:
  `12979e14c176fdeaebaaa7531c7e4448728e78289e45a7d2f832b590eb33925e`.
- **Quality:** no quality issues, no missing expected series.

### Publication-lag verification (the study's core PIT issue)

The 6b evidence register records BAA10Y posting about a day later than
other FRED series. This fetch verified the lag behaviourally, in the
study-007 pattern (unbounded re-fetch of BAA10Y and VIXCLS at fetch time,
recorded in the manifest's `fred_lag_check`):

- At fetch time (2026-11-19T00:25Z, 2026-11-18 19:25 EST), BAA10Y and
  VIXCLS both end **2026-11-17**. The most recent trading day was
  2026-11-18 (Wednesday).
- The 6b probe earlier the same day (2026-11-18T21:45Z, 45 minutes after
  the close) showed BAA10Y still at 2026-11-16 while VIXCLS was already
  at 2026-11-17.
- The two probes bracket BAA10Y's posting to the **post-close evening
  window** (between 16:45 and 19:25 EST): at Wednesday's close, the latest
  available BAA10Y value was Monday's. The effective 2-trading-day BAA10Y
  lag stands, and the trial uses it: the predictor at decision close t is
  the BAA10Y change ending at t−2 — **a lag-2 predictor by value date**,
  deliberately, as the preregistration states. The VIX control uses the
  standard 1-trading-day FRED lag (VIXCLS last 2026-11-17 = the previous
  trading day, consistent with N=1).

The lag check is time-aware: study 007's check ran before the US open and
stepped back a day unconditionally; this fetch runs after the close, so a
weekday fetch after 16:00 ET counts today as the most recent trading day.

## Timestamp conventions

- US equity closes are recorded at **21:00 UTC** fixed (DST not modelled).
- Daily windows are half-open, each separated by a one-day purge gap:
  train [2003-01-02, 2020-01-01), validation [2020-01-02, 2024-01-01),
  holdout [2024-01-02, 2026-11-18).
- The PIT store records `available_at` = event time (an adapter
  limitation: the FRED adapter does not model publication lag). The lag is
  enforced in the trial's panel construction via the study-007
  lagged-changes module, not in the stored observations. This is a known
  lab limitation, recorded in the preregistration's confounders.

## Definitions and transformations

- **Returns/changes:** diff-then-join — computed per series on its own
  dates first, then joined (study 003 proved join-then-diff does not
  reproduce the numbers). SPX and VIX are log changes; BAA10Y is the level
  change × 100 (basis points). No forward filling; incomplete rows are
  dropped and the dropped count is reported.
- **Predictor:** the BAA10Y bp change lagged 2 positions on BAA10Y's own
  dates, then aligned to the panel index (study-007 `lagged_changes_on_index`,
  shift between diff and join). **Control:** the VIX log change lagged 1
  position the same way. **Target:** the SPX log return.
- **Primary test:** partial lead-lag OLS of SPX[t+1] on SPX[t] and the
  lagged VIX change at t (base) versus the same plus the lagged BAA10Y
  change at t (augmented), lag 1 in regression terms, Newey-West HAC
  standard errors (max lag 5). All predictors are known at the decision
  close, so no future information enters.
- **Test family (Holm, target FWER 0.05):** the primary test only
  (planned_test_count = 1). The no-factor version is reported as an
  upper-bound control.
- **Walk-forward:** purged chronological splits, initial train 1,000 rows,
  test windows 126 rows, 1-day embargo. A regression row's label (the SPX
  return over the next row) ends at the exact next-row event time, so
  weekends and holidays are handled exactly (a Friday row's label ends
  Monday). OOS R² is scored on all folds and, for the acceptance criterion,
  on the preregistered holdout window only.
- **Cost gate:** sign rule on holdout OOS augmented forecasts, 1x, always
  invested while positioned. Entry from flat and final exit cost one SPY
  spread side each (1bp); a direction flip costs a full round trip (2bp).
  The 1bp-per-side SPY spread is a deliberately conservative labelled
  assumption (realised SPY spreads are about 0.1–0.2bp). Slippage and
  market impact are ignored (stated limitations).
- **Descriptives (not in the family):** the naive unlagged alignment (the
  lookahead version — what ignoring the publication lag would buy), the
  reverse placebo (SPX→BAA10Y), sub-period stability (five preregistered
  windows), and the naive lead-lag scan (lags 0–5).

## Results

### Step 1 — Naive scan (descriptive)

Correlation between the unlagged BAA10Y bp change at t and the SPX return
at t+k, n = 5,958 at lag 0:

| lag | 0 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| correlation | −0.2182 | 0.0054 | −0.0532 | 0.0108 | 0.0280 | −0.0479 |

Same-day co-movement is strong (−0.2182): spread widening coincides with
SPX weakness on the same value date, in the expected direction. Lag 3
(+0.0108) is the tradeable, PIT-correct alignment — the change ending at t
paired with the return over t+3 is the same pairing as the primary test
(the change ending two days before the decision close predicting the
next-day return) — and it is null. Lag 2 (−0.0532) is the largest lagged
correlation, but it pairs the change with the return on the day the change
becomes available (the value-date change ending at t posts after the close
of t+2), so it is not a prediction; it is recorded here as a descriptive
curiosity, not a finding.

### Steps 3–4 — Partial lead-lag tests

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily BAA10Y→SPX, VIX control (primary) | 5,957 | 1.80e-05 | 1.35e-04 | 0.13 | 0.8935 | 0.8935 | 2.19e-05 | 2.16e-05 |
| no-factor control | 5,957 | 1.82e-05 | 1.35e-04 | 0.14 | 0.8924 | — | 2.23e-05 | 2.20e-05 |
| naive (unlagged) alignment | 5,957 | −8.41e-05 | 9.31e-05 | −0.90 | 0.3665 | — | 0.000451 | 0.000445 |
| reverse placebo (SPX→BAA10Y) | 5,957 | −24.4787 | 6.9165 | −3.54 | 0.0004 | — | 0.008716 | 0.008533 |

The primary coefficient (+1.80e-05 ± 1.35e-04 per bp) is consistent with
zero and has the **wrong sign** (the preregistered expectation was
negative). In economic terms: a one-standard-deviation (3bp) spread move
predicts a +0.005% ± 0.04% next-day SPX return — nothing. Its partial R²
(2.19e-05) is 228x below the preregistered minimum effect size of 0.005.
The no-factor upper-bound control is the same null, so the null is not an
artefact of the VIX factor absorbing the effect. Base-model R² is 0.01436
and augmented R² is 0.01438: the lagged spread change adds nothing to a
baseline that is itself barely predictive.

The naive (lookahead) alignment is also null (p = 0.3665, partial R² =
0.000451): **the publication lag is not what killed the effect.** Even
with the change ending at t — data that was not available at close t — the
next-day relationship is absent. The lag-2-vs-lag-1 question is moot for
the verdict, though the PIT discipline still matters: the trial ran the
available-data alignment because that is the only honest one.

The reverse placebo is nominally significant (p = 0.0004, partial R² =
0.0087): a +1% SPX day predicts a −0.24bp narrowing of the spread the next
day. This is **descriptive only** — it was not in the test family, carries
no multiplicity correction, and is not a finding. It is recorded as a
hypothesis-generating observation: information appears to flow from
equities to credit, not the reverse, consistent with equities being the
faster, more liquid market. A follow-up study would need a fresh
preregistration (SPX→BAA10Y as the primary hypothesis) before any claim.

### Sub-period stability (descriptive)

| sub-period | n | coef | SE | partial R² |
| --- | --- | --- | --- | --- |
| 2003–2007 | 1,245 | −3.47e-05 | 1.12e-04 | 8.8e-05 |
| 2008–2012 | 1,248 | 1.80e-05 | 2.46e-04 | 2.0e-05 |
| 2013–2017 | 1,248 | 1.01e-04 | 1.27e-04 | 0.000783 |
| 2018–2022 | 1,247 | −8.53e-05 | 3.54e-04 | 0.000468 |
| 2023–2026 | 965 | 1.81e-04 | 1.01e-04 | 0.002835 |

Coefficients flip sign across the five windows and stay tiny in all of
them; there is no stable sub-period effect. (No p-values: descriptive
only, not in the test family.)

### Step 5 — Purged walk-forward OOS

40 folds, 0 skipped, 4,957 test rows. All-folds incremental OOS R² is
**−0.00339** (baseline MSE 0.00015049 vs augmented MSE 0.00015100):
adding the lagged spread change worsens out-of-sample forecasts overall.
Holdout-only (7 folds, 716 rows) is **+0.000146** (baseline MSE
9.4474e-05 vs augmented MSE 9.4460e-05) — positive, but the MSE
improvement is 1.4e-08 in absolute terms, essentially zero. Per-fold
incremental OOS R² hovers around ±0.001 with one outlier: fold 5 (test
decisions 2009-01-13 → 2009-07-14, the crisis trough) at −0.03895, where
the augmented model badly hurt. There is no stable out-of-sample edge in
either direction.

### Step 6 — Cost gate

Sign rule on the 716 holdout OOS days: 366 flips (the forecasts change
sign on more than half the days), gross daily edge +0.0208%, total spread
cost 7.34% over the holdout (0.0103%/day), net daily edge **+0.0106%**,
block-bootstrap 95% CI [−0.0446%, +0.0719%], bootstrap p = 0.7236 (block
length 10, 2,000 resamples, seed 42). The net edge is positive but
statistically indistinguishable from zero; the interval comfortably
includes zero. Turnover is brutal: 366 flips at 2bp each is the entire
story of the cost side, and the gross edge (+0.0208%/day) is half eaten by
spreads even at the conservative 1bp assumption.

## Verdict against the preregistered criteria

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted primary p < 0.05 | 0.8935 | no |
| Primary partial R² ≥ 0.005 | 2.19e-05 | no |
| Holdout OOS incremental R² > 0 | +0.000146 | yes |
| Net daily edge after costs > 0 | +0.0106%/day | yes |

Two of four criteria pass, but both pass by a hair on noise: the holdout
OOS R² of +0.000146 is a 1.4e-08 MSE improvement, and the net edge's
bootstrap p-value is 0.72. The two decisive criteria — the primary test's
significance and its effect size — fail by orders of magnitude.
**H0013 v1 is REJECTED.** There is no evidence that the latest available
BAA10Y spread change predicts next-day SPX returns over 2003–2026, at the
available-data alignment or at the (lookahead) naive alignment, with or
without the VIX control, in-sample or out-of-sample.

This is a null, not a failure of method. The sample is large (5,957
regression observations — the largest lead-lag sample in the lab), the
design was preregistered, and the null survives every robustness cut. The
minimum detectable effect for the lead-lag partial R² at 80% power is
**0.00132** (2B audit formula, n = 5,957), so the study rules out any
partial R² at or above ~0.0013 — the observed 2.19e-05 is 60x below the
MDE and the 0.005 threshold is ~3.8x above it. What the study cannot rule
out is an effect smaller than ~0.0013 in partial R² terms — which, at
that size, would be economically negligible for a daily signal (a 3bp
spread move predicting less than 0.01% of next-day return variance).

## Limitations

- **The 2-day lag is assumed constant across the sample.** It was verified
  only at fetch time (2026-11-18/19). FRED's posting schedule for BAA10Y
  may have changed over 2003–2026; the trial applies the current lag to
  the whole history. (The naive alignment's null makes this unlikely to
  matter for the verdict.)
- **FRED revisions are unmodelled.** The trial uses the current vintage;
  real-time (as-first-posted) values are not available for these series.
- **The PIT store does not model publication lag** (`available_at` =
  event time). The lag is enforced in the trial's panel construction, not
  in the stored observations — a known lab limitation.
- **Linear, lag-1 (regression) only.** Nonlinear, longer-lag, or
  volatility-mediated transmission is not tested. The scan's lag-2
  correlation (−0.053) is a descriptive curiosity, not a tested effect.
- **BAA10Y nets out the rates level by definition** (BAA − DGS10), so
  DGS10 is not a separate control — a documented design choice. A
  rates-level effect would appear through the spread only to the extent
  it moves BAA and DGS10 differently.
- **Cost model is stylized.** Slippage and market impact are ignored; log
  returns proxy 1x P&L. All of these would make the net edge worse, not
  better. The 1bp SPY spread assumption is conservative; even at zero
  cost the gross edge (+0.0208%/day) would be statistically zero.
- **HAC p-values are asymptotic.** With n = 5,957 the asymptotics are
  comfortable, but the p-values are not exact.
- **The reverse placebo is descriptive** (see above) and must not be cited
  as evidence without a fresh preregistration.

## Scaffold feedback (6c's first real use)

The study was generated from the planner template with the 6c scaffold
(`spec_from_planner_draft` + the three generated scripts). The scaffold
produced a working skeleton — the registration flow, the manifest shape,
the trial/ledger wiring and the report template all worked — but first
real use exposed seven gaps, all fixed by hand during this study:

1. **The generated `run_trial.py` wired only the primary test and a
   two-criterion verdict.** The walk-forward OOS evaluation and the cost
   gate were `NotImplementedError` stubs (documented in the scaffold docs,
   but real work for first use). The full study-001/003 pipeline had to be
   written by hand.
2. **The generated `run_trial.py` passed `bar_seconds=86400` to
   `build_synchronized_panel`.** For real US equity data with weekend
   gaps, that would invalidate every Monday/post-holiday return (~30%+ of
   rows). The 6c synthetic panel used consecutive calendar days, so it
   never showed. Study 003 correctly omits it.
3. **The generated `fetch_data.py` had no Yahoo fail-fast checks** (the
   ^MOVE lesson from study 003: verify the longName and the positivity of
   closes) and hard-coded `content_type="application/json"` for every raw
   page — FRED pages are CSV.
4. **The generated `preregister.py` was not idempotent** — re-running it
   would attempt a duplicate registration. Studies 001/003 check for an
   existing registration first; this study's script was extended the same
   way.
5. **The planner draft's `target_definition` was wrong for a spread**
   ("daily log return of BAA10Y"), and the scaffold passes draft text
   through verbatim. The researcher must catch domain errors the scaffold
   cannot see.
6. **`spec_from_planner_draft` requires exactly a 2-instrument universe.**
   Adding a control leg (VIX) required hand-editing `design.json`'s
   universe, `preregister.py`'s constants, and both scripts after
   generation. (The scaffold's `_control_id()` convention anticipates a
   third instrument, but the generator does not produce one.)
7. **The generated primary test used `panel.returns[SOURCE]` (log
   returns) for the predictor** — the wrong transform for a spread, which
   needs level changes via the study-007 lagged-changes module. The
   scaffold has no notion of per-instrument transforms.

None of these blocked the study, and the scaffold still saved real work
(the registration flow and ledger wiring worked first time). But the
scaffold is a skeleton, not a study: a researcher who ran the generated
scripts unmodified would have produced a wrong panel (item 2), a wrong
predictor (item 7), and an incomplete verdict (item 1).

## Reproducibility

- Preregistration: `research/credit-spread-spx-008/preregister.py` →
  H0013 v1, spec fingerprint
  `e7f98ea75dd4c2a9b545e71b3f2fd0c9dd1d8dcef42add42987dd1d44861a39a`,
  registration hash
  `be3aa894038671c10e4f0c47355d06d6e496ec606e3084e3877bfb7e263b792a`.
- Fetch: `research/credit-spread-spx-008/fetch_data.py` →
  `manifest.json` (SHA-256 `12979e14…925e`, full value in the Data section
  above).
- Trial: `research/credit-spread-spx-008/run_trial.py` → trial T0016,
  ledger record
  `5e2ca06ab5c3c417df84dac18f71e435ec10114411c1c867d4beb10d98426170`,
  code revision `91bde7822ddbfc60edaeb1039892dfae037f60ab`,
  config fingerprint
  `4a369728e472c9087d169976fcf822c7ac891cea8173ef21c0070ac192664aa4`,
  spec fingerprint
  `1f1916a0b0fb9731d756b046b788f5e611b71d8c87a72feddd783e1871de07b6`.
- Independent verification: every headline number in this report was
  recomputed from the raw payloads with plain numpy (no repo imports) —
  panel counts, all four partial tests, all six scan correlations, both
  OOS R² values, and the full cost gate including the bootstrap CI and
  p-value — and matches the ledger to ~1e-12 relative tolerance.
- Re-run from the repo root (after `fetch_data.py` restores the local
  cache): `.venv/bin/python research/credit-spread-spx-008/run_trial.py`.
  The trial refuses to run twice under the same trial id; the ledger is
  the permanent record.

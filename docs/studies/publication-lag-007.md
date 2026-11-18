# Publication-lag-aware positioning (study 007)

- **Study:** `research/publication-lag-007/` — hypotheses **H0011 v1**
  (trial **T0013**) and **H0012 v1** (trial **T0015**). Trial T0014, the
  first H0012 attempt, failed inside the experiment on the
  skipped-release guard before any results were computed; see
  [Reproducibility](#reproducibility).
- **Verdict H0011: SUPPORTED.** The FOMC TYVIX event response survives a
  one-trading-day FRED publication lag: the lagged TYVIX CAR[0,+1] is
  −0.0302 (z = −5.99, Holm p = 5.2e-09) with a standardized mean CAR of
  −0.516, past the preregistered −0.3 threshold. Both acceptance
  criteria passed.
- **Verdict H0012: REJECTED.** No evidence that the latest published CPI
  month-on-month value predicts next-day SPX returns: the primary
  coefficient is −0.0374 with a Holm-adjusted p-value of 0.755, partial
  R² is 0.00010, and the holdout out-of-sample incremental R² is
  −0.00034. All three acceptance criteria failed.
- **Status:** hypothesis H0011 v1 transitioned to SUPPORTED after trial
  T0013; hypothesis H0012 v1 transitioned to REJECTED after trial T0015.

This is the roadmap's "Publication-lag-aware positioning study" item —
the last unchecked Stage 3 empirical item — and it closes the stated
limitation recorded in study 005: "FRED publication lag is not
modelled". The lag turns out to matter less than feared for the event
study (the TYVIX finding survives it, and the VIX leg even becomes
significant under the lag) and not at all for the CPI signal (both the
point-in-time and the naive alignments are null on the daily tests).

## Question

**H0011 (event-study lag sensitivity).** Does study 005's TYVIX event
response (CAR[0,+1] = −0.0381, Holm p = 5.0e-08) survive when every FRED
series is shifted one trading day to match FRED's publication rhythm —
that is, when the reader sees each FRED value only the next trading day?

- **H0:** The lagged TYVIX CAR[0,+1] is zero: under FRED's publication
  rhythm the statement-day response is not visible in the [0,+1]
  availability window.
- **H1:** The lagged TYVIX CAR[0,+1] is negative, with a Holm-adjusted
  one-sided p-value below 0.05 and a standardized mean CAR at or below
  −0.3.

**H0012 (release-day-aligned CPI transmission).** Does the latest
published CPI month-on-month value (FRED CPIAUCSL, aligned by release
date as a step function) predict next-day S&P 500 returns?

- **H0:** The latest published CPI MoM has no incremental predictive
  value for next-day returns: the step coefficient is zero and the
  predictor does not improve out-of-sample forecasts.
- **H1:** The CPI step predictor has incremental predictive value for
  next-day SPX returns beyond SPX's own lagged return, with a
  Holm-adjusted p-value below 0.05, a partial R² of at least 0.005 and
  a positive holdout out-of-sample incremental R². The expected
  direction is negative (a higher CPI MoM tightens policy expectations
  and should weigh on next-day equities), but the tests are two-sided
  and the sign is not a verdict criterion.

## The FRED publication lag: verification

The one-day lag is verified by behaviour, not assumed. Two checks, at
two time points on 2026-11-18, both before any trial ran:

**Preregistration check (2026-11-18, 06:26 UTC = 01:26 EST, about 9.4
hours after Tuesday 2026-11-17's close).** The VIXCLS and DGS10
fredgraph CSVs both end at 2026-11-16 (Monday). Tuesday's value is not
posted yet, which rules out same-evening posting, while Monday's value
is already available, which rules out a two-business-day posting delay
(a two-day lag would have left Monday's value unposted until Wednesday
morning). So a FRED value dated t is posted on the next business day,
and at the close of day t the latest available FRED value is the
previous trading day's: a **one-trading-day availability lag (N=1)**.

**Fetch-time re-check (recorded in the manifest).** Unbounded VIXCLS
and DGS10 fetches at fetch time again end at 2026-11-16, while the most
recent trading day is 2026-11-17 — consistent with N=1 (the fetch ran
before Wednesday morning's posting). The fetch script enforces the
check: a last available date older than the previous trading day would
have falsified N=1 and failed the fetch.

A note on what the lag is and is not: it is a *publication* lag (when
the data becomes available), not a market-response lag (when prices
move). Yahoo and OKX market data carry no such lag — the close is
knowable at the close — so only the FRED legs are shifted. The residual
risk is a historical change in FRED's posting behaviour, which cannot
be verified from current data; the lag is verified for the present,
and the study applies it uniformly across 2003–2020.

## Data and provenance

- **Sources:** FRED free fredgraph CSV (`fred` v1, no API key) for
  VIXCLS (VIX), VXTYN (TYVIX), DGS10 (10-year Treasury yield), BAA10Y
  (Baa minus 10-year Treasury spread) and CPIAUCSL (seasonally adjusted
  CPI, monthly); Yahoo Finance public chart endpoint (`yahoo-finance`
  v1, no key) for the S&P 500 index (`^GSPC`, meta longName verified as
  "S&P 500" at fetch time); OKX public REST (`okx-public` v1, no key)
  for BTC-USDT-SWAP daily candles. The FOMC calendar is study 005's
  (`research/fomc-event-study-005/fomc_calendar.json`, 199 scheduled
  meetings, validated through the loader) and the CPI calendar is study
  006's (`research/macro-windows-006/cpi_calendar.json`, 71 releases,
  validated through the loader); neither was re-extracted.
- **Sample:** FRED daily 2003-01-02 → 2020-05-15; CPIAUCSL monthly
  2020-11-01 → 2026-10-01; ^GSPC 2003-01-02 → 2026-11-17; OKX BTC daily
  2021-01-01 → 2026-11-18. Rows fetched per series: VIXCLS 4,374;
  VXTYN 4,363 (ends 2020-05-15, discontinued); DGS10 4,347; BAA10Y
  4,346; CPIAUCSL 71; ^GSPC 6,008; BTC 2,146 candles.
- **Missing values:** FRED fredgraph CSVs carry one row per weekday, with
  an **empty** value field on market holidays — not `"."` as FRED's API
  documentation suggests (verified in study 003; the adapter treats both
  as missing). Empty-value counts over the window: VIXCLS 158, VXTYN
  169, DGS10 185, BAA10Y 186. CPIAUCSL has exactly one missing month:
  **2025-10, never published** (2025 lapse in appropriations) — see
  [Definitions and transformations](#definitions-and-transformations).
  Yahoo ^GSPC had 0 null closes; OKX BTC had 0 missing bars. Missing
  rows are excluded at fetch time and counted; no forward filling
  anywhere.
- **Panels:** H0011 panel (five legs through the TYVIX coverage end)
  **4,330 unlagged return rows** (2003-01-03 → 2020-05-15), 51 dropped
  close rows and 52 dropped return rows — identical to study 005's
  panel; the lagged panel drops its first row (no lagged change) for
  **4,329 return rows** (2003-01-06 → 2020-05-15). H0012 SPX panel
  **1,475 return rows** (2021-01-05 → 2026-11-17), 0 dropped close rows;
  H0012 BTC panel **2,145 return rows** (2021-01-02 → 2026-11-16), 0
  dropped close rows. Dropped rows in the H0011 panel are partial
  holidays where some series trade and others do not (e.g., bond
  holidays when equities trade).
- **Raw payloads and PIT parquet** live only in the local gitignored
  cache (`data/cache/publication-lag-007/`); they are not committed.
  The committed `manifest.json` records every fetch (endpoint,
  parameters, date ranges, payload SHA-256), the FRED lag re-check and
  the calendar validation. Note the manifest's own SHA-256 is not
  reproducible across pulls: it embeds the fetch timestamp, and record
  hashes embed ingestion time. What is reproducible is the fetched data
  and every number in this report.
  Manifest SHA-256: `ea77390999601466a32fb2b523dbaf3f5a84630666d5236257da102b2e805967`.
- **Quality:** 23,509 observation rows across 6 series in `pit-1d`
  (FRED + Yahoo, 21:00 UTC closes) and 10,730 rows across 5 series in
  `pit-okx-1d` (OKX BTC, 16:00 UTC opens); no quality issues, no missing
  expected series. The two stores are separate because OKX bars and
  FRED/Yahoo closes use different event-time conventions.
- **TYVIX substitution (from study 003, stated limitation).** TYVIX
  measures expected 30-day volatility of 10-year Treasury futures
  *prices*; the MOVE index measures Treasury *yield* volatility. TYVIX
  is the closest free substitute but the substitution is approximate,
  and TYVIX was discontinued in May 2020, so the H0011 sample excludes
  the post-2020 rate-hiking cycle.

## Timestamp conventions

- FRED daily values are closing values dated `observation_date`; Yahoo
  daily bars carry the trading date derived in America/New_York. Both
  are recorded at a shared event time of **21:00 UTC** (16:00 ET close,
  fixed; DST is not modelled), with `available_at` equal to the event
  time in the store. The one-day FRED availability lag is applied by
  the analysis (the lag module), not by the store: the stored
  `available_at` is the reference-date close, and the lagged transforms
  shift the FRED legs by one trading day on their own dates.
- **FOMC statement timing (fixed in preregistration, as in study 005):**
  the statement is released at about 14:00 ET on the last meeting day,
  and the daily close (16:00 ET) already contains the reaction. t=0 is
  the statement day; the event window [0,+1] is the statement day plus
  the next trading day.
- **CPI release timing:** every release is 08:30 Eastern Time, always
  before the 16:00 ET close, so a release on date D is knowable at the
  close of D and release-day rows carry the fresh print. The CPI step
  is evaluated at each bar's **close date**: for SPX the close date is
  the trading date; for OKX daily bars (open 16:00 UTC) the close date
  is the open date plus one day. A release on D falls inside the OKX
  bar opening D−1 16:00 UTC, which closes D 16:00 UTC — the same
  release-date rule serves both venues once each bar is dated by its
  close.
- H0011 windows (21:00 UTC daily closes), mirroring study 005: train
  [2003-01-02, 2012-01-01), validation [2012-01-03, 2017-01-01),
  holdout [2017-01-03, 2020-05-15). The windows exist for registry
  compatibility; the event study uses the full main sample, not the
  splits.
- H0012 windows (21:00 UTC daily closes): train [2021-01-04,
  2024-01-01), validation [2024-01-02, 2025-01-01), holdout
  [2025-01-02, 2026-11-18). The predictor is undefined before the first
  calendar release (2021-01-13), so the effective sample starts
  2021-01-13; the train window starts 2021-01-04 to keep the
  calendar-month boundary clean.

## Definitions and transformations

- **The lag operation (H0011).** A lagged FRED level series is the
  original level series shifted forward by one position on the series'
  own dates: the value dated t becomes the value available at t+1. Its
  changes are the original changes shifted by the same amount, so the
  lagged change at own-date t is the original change at the previous
  own date. Changes are computed per series on its own dates first
  (diff-then-join), shifted, then aligned to the panel's return index;
  the shift sits between diff and join. A partial holiday in one leg is
  handled per series on its own dates: a lagged change at t is the
  original change at the previous own date, even when that date is not
  in the panel index. The first panel return row (2003-01-03) has no
  lagged change and is dropped; the lagged panel has 4,329 rows.
- **What the lag does to the event window.** A lagged [0,+1] window in
  availability terms covers reference-date changes **[−1,0]**: the
  statement-day change plus the day-before change, not the day-after
  change. The estimation window shifts back by the same amount
  ([−60,−11] availability = [−61,−12] reference), which moves a 50-day
  mean by one day and is second-order. The verdict question is whether
  study 005's TYVIX finding survives that shift — not whether study 005
  was wrong: both alignments are conditionally correct, under different
  availability assumptions. Study 005's conclusion is correct under
  reference-date alignment; this study asks what a reader or system
  depending on FRED's publication rhythm would conclude.
- **Events (H0011):** scheduled FOMC meetings only; t=0 is the statement
  day. Main sample: 138 scheduled statements from 2003-01-29 to
  2020-04-29. **135 events are included** — the same 135 as study 005,
  enforced by a machinery guard in the trial script; 3 are excluded and
  counted: 2003-01-29 and 2003-03-18 (the estimation window extends
  before the panel start) and 2004-11-10 (t=0 is absent from the panel —
  the genuine two-day VXTYN gap documented in study 005). First included
  event 2003-05-06, last 2020-04-29.
- **Machinery guards (H0011).** Two guards fail the trial if they break.
  First, the SPX control (unlagged, on the truncated index) must
  reproduce study 005's SPX CAR exactly (+0.000669, p = 0.634) — it
  does, to the last digit, because the dropped first row is in no
  included event's estimation window. Second, the same 135 events must
  be included with the same three excluded — they are. A descriptive
  unlagged replication on the truncated index reproduces all five study
  005 legs exactly (TYVIX −0.038112, VIX −0.015517, DGS10 −0.9499 bp,
  BAA10Y +0.2717 bp, SPX +0.000669), isolating the truncation effect
  (zero) from the lag effect.
- **Estimator (H0011):** the repo's `event_study()`
  (`src/myquant/stats/event_study.py`), with the constant-mean expected
  series supplied per event (`src/myquant/studies/event_windows.py`).
  Scheduled meetings are at least four weeks apart, so [0,+1] windows
  never overlap: every event is its own cluster (135 events, 135
  clusters in every family test). Inference is the cluster-based normal
  reference: SE = cross-event CAR standard deviation / √n.
- **One-sided p-values** for the lagged volatility legs are derived from
  the z-statistic as Φ(z) for the "less than" direction, as
  preregistered. **Effect size** is the standardized mean CAR (mean CAR
  divided by the cross-event standard deviation of CARs); the 0.3
  threshold is a small-to-medium standardized effect.
- **The CPI step predictor (H0012).** The predictor is the FRED
  CPIAUCSL month-on-month log change, aligned by **release date** as a
  step function: each trading day's value is the most recent published
  CPI MoM as of that day (release dates from study 006's calendar, 71
  releases). CPIAUCSL is the seasonally adjusted series (the "S"), the
  right one for headline MoM. The step is evaluated at each bar's close
  date (see [Timestamp conventions](#timestamp-conventions)).
  Regression row j predicts the target return over bar j+1 from
  predictors known at bar j's close (the CPI step at bar j's close date
  and the target's own lagged return). SPX regression rows: 1,468
  (2021-01-13 → 2026-11-16; 6 rows dropped before the first release).
  BTC regression rows: 2,134 (bars opening 2021-01-12 → 2026-11-15).
- **The missing October 2025 CPI.** The October 2025 CPI was never
  published, so CPIAUCSL has no 2025-10 level: the MoM is undefined for
  2025-10 and for 2025-11 (no comparison base). The November 2025
  release (2025-12-18) therefore publishes no usable MoM and does not
  move the step — the September 2025 value (released 2025-10-24,
  delayed by the shutdown) holds until the December 2025 release
  (2026-01-13), about eleven weeks. The preregistered rule ("most
  recent published CPI MoM") already covers this: a release that
  publishes no usable MoM does not update the step. The trial enforces
  it as a machinery guard: the only in-sample release without a usable
  MoM must be the November 2025 CPI. The out-of-sample November 2026
  release (2026-12-10) also has no usable MoM — its value is not
  published yet at fetch time — and is recorded separately.
- **Effective sample (H0012).** The step predictor takes only **69
  distinct values** over 2021–2026 (70 in-sample releases minus the
  November 2025 release, which carries no usable MoM); the 1,468 daily
  regression rows are NOT the effective sample size. The release-day
  subsample test (B, n = 70 — every in-sample release is an SPX trading
  day) is the cleaner read: each row is a fresh-information event.
- **HAC lags (H0012, fixed in preregistration).** The daily tests use
  max lag 21 because the step predictor's run length is about 21
  trading days (one release per month), so the regression residuals
  inherit roughly monthly autocorrelation; the release-day subsample
  uses max lag 5 because its rows are about 21 trading days apart and
  only short-range dependence remains. The lags were fixed before any
  result was computed and were not tuned afterwards.
- **Naive alignment (descriptive, not in the family).** The same CPI
  MoM aligned by **reference month**: the value at close date d is the
  MoM of the reference month containing d — as if the month's CPI were
  known during the month itself. That is 2–6 weeks of lookahead. The
  same three regressions are run with the naive predictor and the
  coefficients and partial R² compared against the PIT step, to quantify
  the lookahead bias. Rows in October–November 2025 and November 2026
  have no naive value (their reference months' MoM is undefined) and
  are dropped (SPX naive n = 1,415; BTC naive n = 2,057; naive
  release-day n = 68).
- **Walk-forward (H0012).** Purged walk-forward OOS evaluation of the
  SPX model: base model is SPX own lag only, augmented model adds the
  CPI step; initial train 365 days, test 90 days, 1-day embargo.
  Regression row j's label (the return over bar j+1) is known at bar
  j+1's close — one day after the decision time — so label_end =
  decision_time + 1 day. 13 folds, 1,103 test rows; holdout (decision
  times from 2025-01-02): 6 folds, 470 test rows.
- **Cost gate (H0012, informational only).** The S&P 500 index is not
  directly tradable and no free SPX futures or ETF price series is used
  in this study, so the cost gate reports the gross sign-rule edge on
  holdout OOS forecasts (1x, always invested while positioned; no costs
  applied) with a block-bootstrap confidence interval, mirroring study
  003's treatment. The gross edge is an upper bound on any tradable
  edge, not a verdict criterion.
- **Not a surprise (red line).** The predictor is the published CPI
  month-on-month level, not a surprise: no consensus data is used (no
  free source), so this study does not measure CPI surprises and
  nothing in this report claims to.

## Results

### H0011 — event-study lag sensitivity (trial T0013)

The preregistered five-test Holm family on the lagged [0,+1] window,
n = 135 events, 135 clusters:

| test | leg | mean CAR | SE | z | raw p | Holm p | std. mean CAR | reject |
|---|---|---|---|---|---|---|---|---|
| tyvix_lagged_car (primary, one-sided < 0) | TYVIX (log pts) | −0.030216 | 0.005043 | −5.9914 | 1.040e-09 | 5.201e-09 | −0.5157 | **yes** |
| vix_lagged_car (one-sided < 0) | VIX (log pts) | −0.024380 | 0.008193 | −2.9756 | 0.001462 | 0.005848 | −0.2561 | **yes** |
| dgs10_lagged_car (two-sided) | DGS10 (bp) | −1.176593 | 0.785382 | −1.4981 | 0.1341 | 0.4023 | −0.1289 | no |
| baa10y_lagged_car (two-sided) | BAA10Y (bp) | +0.607111 | 0.492365 | +1.2331 | 0.2176 | 0.4351 | +0.1061 | no |
| spx_car (two-sided, unlagged control) | SPX (log pts) | +0.000669 | 0.001407 | +0.4757 | 0.6343 | 0.6343 | +0.0409 | no |

The TYVIX event response survives the one-day FRED lag: the lagged CAR
is −0.0302 against the unlagged −0.0381 — about 79% of the effect
remains — and the rejection is as strong as ever (Holm p = 5.2e-09,
standardized −0.52 against the −0.3 threshold). The lag costs the day
+1 piece of the response and nothing else; the finding is not an
artefact of the publication rhythm.

The VIX leg is the surprise of this study: it is **significant under
the lag** (Holm p = 0.0058) while the unlagged VIX test was not (study
005: Holm p = 0.160). The per-day decomposition below explains why —
the unlagged VIX CAR mixes the day-0 drop with a day +1 rebound, and
the lagged window drops the rebound day. Under FRED's publication
rhythm, the equity-volatility drop after FOMC statements is visible;
under reference-date alignment it is diluted by the next day's
bounce. Both readings are conditionally correct; the difference is
which days the window covers, not which data is real.

DGS10 and BAA10Y lagged CARs are null, as their unlagged versions were.
The SPX control reproduces study 005 exactly, as the machinery guard
requires.

**Per-day abnormal-return decomposition (unlagged, descriptive).** Mean
abnormal return on days −1, 0 and +1, n = 135 events. The lagged
CAR[0,+1] is approximately the sum of the day −1 and day 0 mean ARs
(the estimation window also shifts by one day, so the match is
approximate, not exact):

| leg | mean AR day −1 | mean AR day 0 | mean AR day +1 | day −1 + day 0 | lagged CAR[0,+1] |
|---|---|---|---|---|---|
| TYVIX (log pts) | +0.003405 | −0.033642 | −0.004470 | −0.030237 | −0.030216 |
| VIX (log pts) | +0.000962 | −0.025351 | +0.009834 | −0.024389 | −0.024380 |
| DGS10 (bp) | −0.734222 | −0.460148 | −0.489778 | −1.194370 | −1.176593 |
| BAA10Y (bp) | +0.209926 | +0.409926 | −0.138222 | +0.619852 | +0.607111 |
| SPX (log pts) | +0.000598 | +0.002907 | −0.002238 | +0.003505 | +0.000669* |

\* SPX is not lagged; its lagged-window CAR is the unlagged [0,+1] CAR
(+0.000669), shown here for reference only — the day −1 + day 0 column
does not apply to it.

The decomposition explains both findings. For TYVIX, the drop is
concentrated on day 0 (−0.0336) with only −0.0045 on day +1, so the
lagged window keeps most of the effect. For VIX, day 0 drops −0.0254
but day +1 rebounds +0.0098 — the unlagged CAR (−0.0155) is the drop
minus the rebound, while the lagged CAR (−0.0244) is the drop alone.
The day −1 means are small on every leg (|mean AR| ≤ 0.0034 log points,
≤ 0.74 bp), so the lagged window's inclusion of the pre-statement day
adds noise, not signal. The decomposition sums match the lagged CARs
to within 2.1e-5 on the log legs (0.018 bp on DGS10, where the
one-day estimation-window shift matters slightly more) — the lag
changes the conclusion exactly as the day-by-day arithmetic says it
should, with no unexplained remainder.

Per-event lagged CAR dispersion (n = 135): TYVIX CARs range −0.1758 to
+0.1641 (std 0.0586); VIX −0.2595 to +0.2704 (std 0.0952); DGS10
−48.16 to +19.12 bp (std 9.13 bp); BAA10Y −13.76 to +34.28 bp (std
5.72 bp); SPX −0.0588 to +0.0579 (std 0.0163). Event-window moves are
large in both directions; the nulls are nulls of the *average*
response, not of event-day volatility.

### H0012 — release-day-aligned CPI transmission (trial T0015)

The preregistered three-test Holm family of partial lead-lag OLS with
HAC standard errors (target next-day return on the CPI step, controlling
for the target's own lagged return):

| test | coef | SE | t | raw p | Holm p | partial R² | n | reject |
|---|---|---|---|---|---|---|---|---|
| spx_daily (primary) | −0.037402 | 0.119794 | −0.3122 | 0.7549 | 0.7549 | 0.000102 | 1,468 | no |
| spx_release_day | −0.862592 | 0.363623 | −2.3722 | 0.0177 | 0.0530 | 0.060222 | 70 | no |
| btc_daily | −0.487509 | 0.282633 | −1.7249 | 0.0845 | 0.1691 | 0.002168 | 2,134 | no |

The primary test is a clean null: the CPI step coefficient is −0.037
with a standard error three times its size, and the partial R² is
0.0001 — the latest published CPI MoM explains one ten-thousandth of
next-day SPX return variance beyond SPX's own lag. The sign is negative
as expected, but the magnitude is negligible and the p-value is 0.75.

The release-day subsample is the closest read in the study: on the 70
fresh-information rows the coefficient is −0.863 with a raw p-value of
0.018 and a partial R² of 0.060 — the signal, if any, is concentrated
on release days, where the predictor is genuinely new information
rather than a month-old print. But it does not survive the preregistered
multiplicity control (Holm p = 0.053, just above 0.05), it is a
secondary test, and n = 70 with a step predictor that takes only 69
distinct values is a thin base for a claim. It is recorded here as a
hypothesis-generating observation for a future preregistered test, not
as evidence for H0012: the hypothesis is decided by the primary test,
and the primary test is null. The BTC robustness test is also null
(raw p = 0.085, Holm p = 0.169), in the expected direction but well
short of significance.

**Walk-forward.** The augmented model (SPX lag + CPI step) does worse
than the own-lag baseline out of sample: holdout OOS incremental R² is
**−0.000336** (6 folds, 470 test rows), and the all-folds OOS
incremental R² is −0.0109 (13 folds, 1,103 test rows). The CPI step
adds no out-of-sample predictive value.

**Cost gate (informational only).** Gross sign-rule edge on holdout OOS
forecasts: **+0.0293%/day**, block-bootstrap p = 0.423, 95% CI
[−0.046%, +0.099%], sign accuracy 53.6%, 470 days. The interval
includes zero comfortably; no edge, before any costs at all.

**Descriptive naive alignment (not in the family).** The same three
regressions with the reference-month-aligned CPI predictor (2–6 weeks
of lookahead). Coefficients and partial R² only — no p-values, following
the repo's descriptive convention:

| test | PIT coef | PIT partial R² | naive coef | naive partial R² | naive n |
|---|---|---|---|---|---|
| spx_daily | −0.0374 | 0.000102 | −0.0381 | 0.000112 | 1,415 |
| spx_release_day | −0.8626 | 0.060222 | −1.4014 | 0.159820 | 68 |
| btc_daily | −0.4875 | 0.002168 | −0.2920 | 0.000806 | 2,057 |

On the daily tests, the naive alignment is indistinguishable from the
PIT alignment — both null, with nearly identical coefficients. **The
publication lag does not manufacture a false advantage on the daily
tests**: a researcher who aligned CPI by reference month would reach
the same null conclusion as one who aligned it by release date. The
lookahead bites only on the release-day subsample, where the naive
partial R² (0.160) is about 2.7x the PIT partial R² (0.060): on a
release day, the naive predictor is the *next* month's MoM — genuinely
future information — while the PIT predictor is the just-released
print. That is the one place where the alignment choice changes the
reading, and it changes it in the direction the lookahead story
predicts. The honest summary is therefore split: no lookahead bias on
the headline daily tests, material lookahead inflation on the
release-day subsample — and the release-day subsample is exactly where
a careless alignment would be most tempting, because it is where the
signal is concentrated.

## Verdicts against the preregistered criteria

**H0011 (trial T0013): SUPPORTED.** Both criteria passed: the
Holm-adjusted lagged TYVIX p-value is 5.2e-09 (criterion: < 0.05) and
the standardized mean lagged TYVIX CAR is −0.516 (criterion: ≤ −0.3).
The FOMC TYVIX event response survives a one-trading-day FRED
publication lag.

**H0012 (trial T0015): REJECTED.** All three criteria failed: the
Holm-adjusted primary p-value is 0.755 (criterion: < 0.05), the primary
partial R² is 0.00010 (criterion: ≥ 0.005), and the holdout
out-of-sample incremental R² is −0.00034 (criterion: > 0). The latest
published CPI MoM does not predict next-day SPX returns in this sample.

## Limitations

- **The H0011 sample ends 2020-05-15** (TYVIX discontinued) and excludes
  the post-2020 hiking cycle. The lag finding is a 2003–2020 statement;
  whether the day-0 concentration of the TYVIX drop holds in the
  post-2020 regime is untested here.
- **The FRED lag is verified for the present only.** The posting
  behaviour is confirmed at two time points on 2026-11-18; a historical
  change in FRED's posting rhythm cannot be verified from current data.
  If FRED posted same-evening in the 2000s, the early-sample lagged
  CARs would be misaligned — but the finding's strength (z = −5.99)
  leaves room for some early-sample misalignment without changing the
  verdict.
- **The lagged window answers a different question.** The lagged [0,+1]
  window covers reference-date changes [−1,0]; it is not a re-test of
  study 005's [0,+1] window. The two studies' conclusions are both
  conditionally correct under different availability assumptions, and
  neither invalidates the other.
- **CPIAUCSL is the current vintage.** Seasonal factors are revised
  annually, so the historical values differ slightly from the
  as-released prints; as-released values would need ALFRED (API key
  required). The revision effect is small relative to the MoM signal,
  but it is a stated limitation. FRED's own posting lag for CPIAUCSL
  relative to the BLS release date is a second-order effect and is not
  modelled: the step uses the BLS release date, not the FRED posting
  date.
- **The CPI step has only 69 distinct values.** The daily regressions'
  1,468 rows overstate the effective sample; the release-day subsample
  (n = 70) is the cleaner read, and it is small. The near-miss there
  (Holm p = 0.053) is suggestive, not significant, and a future
  preregistered test on a longer release-day sample would be needed to
  settle it.
- **No surprise measure.** The predictor is the published CPI MoM
  level, not actual-minus-consensus. A null here does not rule out
  transmission of true CPI surprises.
- **The naive comparison is descriptive.** The naive alignment's
  release-day inflation (partial R² 0.160 vs 0.060) is reported without
  p-values, as preregistered; it quantifies the lookahead bias, it does
  not test a hypothesis.
- **A significant CAR is not tradable alpha.** The event study measures
  announcement responses on realized data; it does not produce a
  forecast, a signal, or a costed trading rule. The H0012 cost gate is
  informational only and shows no edge before costs.
- **Single sample, single regime for H0012.** 2021–2026 covers one
  hiking cycle, one cutting cycle and the 2025 shutdown gap; the CPI
  null is a statement about this window, not about CPI transmission in
  general.

## Reproducibility

- **Preregistration:** H0011 v1 spec fingerprint
  `b1d626ddffb3d3be4564011edca6ec5b2b0b58d98a1e451a4faf69b474048b63`,
  H0012 v1 spec fingerprint
  `8526ef1ce9d5620463668319c9d3e7b0b31293dd524f157e90032207fccdc6e5`
  (`research/publication-lag-007/preregister.py`, run before any
  result-level analysis; the FRED lag was verified before
  preregistration, and the calendars were validated before registration).
- **Trials:** T0013 record
  `a4852f550c5e11d555786712820c6c8b698c19cf566bef1f691fb5f3b119fa23`,
  T0015 record
  `6d757217ecab7b2e573ba8260579fc08bf643e22ce3a4ba7b3cd53f9eb6e9976`
  (hash-chained ledger `research/publication-lag-007/trials.jsonl`).
  Trial T0014 (the first H0012 attempt, record
  `19a7c75980631eab20eeeb64d280c9de407f7e7cb8090e5a570dd4294d00c101`)
  failed inside the experiment on the skipped-release guard: the guard
  checked all 71 calendar releases, including the out-of-sample
  November 2026 release (2026-12-10), whose MoM is undefined only
  because the value is not published yet at fetch time — not a data
  error. No T0014 results were computed or recorded; the guard was
  corrected to check in-sample releases only and the trial re-ran as
  T0015 (trial IDs are unique per attempt).
- **Code:** fetch `research/publication-lag-007/fetch_data.py`; lag
  alignment and CPI step functions `src/myquant/studies/
  publication_lag.py` (tests `tests/test_studies_publication_lag.py`);
  event-study helpers `src/myquant/studies/event_windows.py`;
  estimator `src/myquant/stats/event_study.py`; partial lead-lag
  `src/myquant/studies/regime.py`; trials
  `research/publication-lag-007/run_trial.py` (T0013) and
  `run_trial_h0012.py` (T0014/T0015).
- **Manifest:** `research/publication-lag-007/manifest.json`, SHA-256
  `ea77390999601466a32fb2b523dbaf3f5a84630666d5236257da102b2e805967`
  (see the note in [Data and provenance](#data-and-provenance) on what
  the manifest hash does and does not reproduce).

### Independent recomputation

Before delivery, the headline numbers were recomputed independently
with plain numpy from freshly re-pulled data, without using any repo
code. For H0011: FRED (VIXCLS, VXTYN, DGS10, BAA10Y) and Yahoo SPX
re-fetched, the 4,330-row unlagged panel and 4,329-row lagged panel
rebuilt, and all five lagged CARs recomputed (estimation [−60,−11],
event [0,+1], constant mean, cluster SE) — TYVIX −0.030216 (z = −5.99,
Holm p = 5.2e-09), VIX −0.024380 (Holm p = 0.0058), DGS10 −1.18 bp,
BAA10Y +0.61 bp, SPX +0.000669 — plus the per-day abnormal-return
decomposition (TYVIX day 0 −0.033642, VIX day 0 −0.025351 with a day
+1 rebound of +0.009834), all matching the ledger to four decimals,
with the same three excluded events. The FRED one-day lag was also
re-checked independently: VIXCLS's last available value was still
2026-11-16 at about 02:00 EST on 2026-11-18, with Tuesday 2026-11-17
unposted. For H0012: CPIAUCSL, SPX and OKX BTC re-fetched, the CPI
step rebuilt from study 006's calendar, and all three family tests
(SPX daily −0.0374, p = 0.755; release-day subsample −0.8626, raw
p = 0.0177, n = 70; BTC −0.4875, p = 0.085) plus the three
naive-alignment descriptives (SPX daily −0.0381, release-day −1.4014,
BTC −0.2920) reproduced to four decimals. The walk-forward OOS and
cost-gate figures were not recomputed independently.

# MOVE/VIX/VXN conditional repricing (study 003)

- **Study:** `research/move-vix-003/` — hypothesis **H0004 v2**, trial **T0004**
- **Verdict: REJECTED.** No evidence that lag-1 rates implied-volatility
  (TYVIX) log changes predict next-day VIX log changes beyond VIX's own
  history and the same-day SPX control. All three preregistered acceptance
  criteria failed.
- **Status:** hypothesis H0004 v2 transitioned to REJECTED after trial T0004.
  H0004 v1 was superseded by a pre-trial amendment (see below); no trial
  ran against v1.

## Question

Does the lag-1 log change in rates implied volatility predict the next-day
VIX log change beyond VIX's own history and the SPX common-factor control?

- **H0:** Lag-1 TYVIX log changes have no incremental predictive value for
  next-day VIX log changes beyond VIX's own history and the SPX
  common-factor control, after dependence controls.
- **H1:** Lag-1 TYVIX log changes explain a positive, out-of-sample
  component of next-day VIX log changes beyond VIX's own lagged log change
  and the SPX control (rates volatility up predicts equity volatility up
  the next day).

This is thesis 001's original H2 — the rates/volatility direction the
thesis planned first, deferred while studies 001 and 002 followed the
user-chosen crypto-perpetual direction. H2 explicitly allows the
relationship to be "conditional, unstable or absent"; this study tests
which one it is on 2003–2020 data.

## Rate-volatility source: the substitution chain

The thesis names the ICE BofA MOVE index as the rates-volatility measure,
"subject to licensing and history availability". No free MOVE source
exists. The chain below was verified by coverage checks on 2026-11-18,
before preregistration and before any result-level analysis:

1. **MOVE — unavailable.** Yahoo `^MOVE` is not the MOVE index: its meta
   longName is a Northern Trust iBoxx ETF. Stooq serves a JS anti-scrape
   page. FRED has no MOVE series.
2. **CBOE TYVIX — available via FRED, not via CBOE or Yahoo.** The CBOE
   history CSV (`TYVIX_History.csv` on the CBOE CDN) returns 403
   (the VIX file from the same CDN returns 200); Yahoo `^TYVIX` is
   delisted ("No data found, symbol may be delisted"); FRED has no
   `TYVIX` series. But **FRED series `VXTYN` is the TYVIX history**:
   2003-01-02 → 2020-05-15, 4,532 rows, zero missing values. TYVIX is
   used as the rates implied-volatility source.
3. **Fallback not needed.** A trailing realized-volatility proxy computed
   from DGS10 daily yield changes was the planned fallback; it was not
   used, since VXTYN provides genuine implied volatility.

**Conceptual difference (stated limitation).** TYVIX measures expected
30-day volatility of 10-year Treasury futures *prices* (in percent);
MOVE measures expected 30-day volatility of Treasury *yields* (in basis
points). Both are rates implied volatility, and TYVIX is the closest
free substitute, but the substitution is approximate: price volatility
and yield volatility differ by duration, which varies over time. TYVIX
was discontinued in May 2020, so the sample ends 2020-05-15 and excludes
the post-2020 rate-hiking cycle.

**Preregistration amendment (v2).** v1's known-confounders said the SPX
factor is contemporaneous with the target (day t+1). That cannot be
implemented: the preregistered `partial_lead_lag` interface requires
every predictor to be known at the forecast time (day t), and the
walk-forward evaluation cannot use a t+1 control without leaking the
future into the forecasts. v2 pins the factor to the predictor day
(SPX[t], now in `fixed_parameters`) and predeclares a descriptive
factor-timing sensitivity (SPX[t+1] control, not in the test family).
No change to the test family, acceptance criteria, sample windows, or
hypotheses. The amendment was made before any result-level analysis;
the factor-timing sensitivity came back null (below), so the ambiguity
is empirically moot.

## Data and provenance

- **Sources:** FRED free fredgraph CSV (`fred` v1, no API key) for VIXCLS
  (VIX), VXNCLS (VXN), VXTYN (TYVIX), DGS10 (10-year Treasury yield) and
  BAA10Y (Baa minus 10-year Treasury spread); Yahoo Finance public chart
  endpoint (`yahoo-finance` v1, no key) for the S&P 500 index (`^GSPC`,
  meta longName verified as "S&P 500" at fetch time).
- **Sample:** daily closes 2003-01-02 → 2020-05-15 (the TYVIX coverage
  window). Rows fetched per series: VIXCLS 4,374; VXNCLS 4,372; VXTYN
  4,363; DGS10 4,347; BAA10Y 4,346; ^GSPC 4,373.
- **Missing values:** FRED fredgraph CSVs carry one row per weekday, with
  an **empty** value field on market holidays — not `"."` as FRED's API
  documentation suggests (verified 2026-11-18; the adapter treats both
  as missing). Empty-value counts over the window: VIXCLS 158, VXNCLS
  161, VXTYN 169, DGS10 185, BAA10Y 186. Yahoo ^GSPC had 0 null closes.
  Missing rows are excluded at fetch time and counted; no forward
  filling anywhere.
- **Panels:** synchronized daily close panel 4,329 rows; daily log-return
  panel **4,328 rows** (2003-01-03 → 2020-05-15); weekly (Friday-close)
  log-change panel **906 rows** (2003-01-10 → 2020-05-15). 54 close rows
  and 55 return rows were dropped for incompleteness — partial holidays
  where some series trade and others do not (e.g., bond holidays when
  equities trade). Full market holidays appear in no series and never
  enter the panel.
- **Raw payloads and PIT parquet** live only in the local gitignored cache
  (`data/cache/move-vix-003/`); they are not committed. The committed
  `manifest.json` records every fetch (endpoint, parameters, date ranges,
  payload SHA-256). Note the manifest's own SHA-256 is not reproducible
  across pulls: it embeds the fetch timestamp, and record hashes embed
  ingestion time. What is reproducible is the fetched data and every
  number in this report.
  Manifest SHA-256: `cde576cdc26826c736cf27c0764221f8f7d92c3e8c40e1f5e93431b732059878`.
- **Quality:** 26,175 observation rows across 6 series, no quality issues,
  no missing expected series.
- **Credit-spread note.** The ICE BofA US High Yield OAS (`BAMLH0A0HYM2`)
  is truncated to recent years on FRED (793 rows from 2023-11-20; licensed
  series are truncated), as is FRED's own `SP500` series (262 rows). The
  study uses BAA10Y (full history) as the credit-spread panel context and
  Yahoo ^GSPC as the SPX factor. Neither enters the test family except
  SPX as the control.

## Timestamp conventions

- FRED daily values are closing values dated `observation_date`; Yahoo
  daily bars are timestamped at the market open (09:30 ET) with the
  trading date derived in America/New_York. Both are recorded at a shared
  event time of **21:00 UTC** (16:00 ET close, fixed; DST is not
  modelled), with `available_at` equal to the event time.
- **FRED publication lag is not modelled** (stated limitation): values are
  posted after the close, sometimes the next morning, so `available_at`
  is optimistic by up to a day. The lag-1 design assumes the previous
  day's close is usable at the next day's close, which holds for all but
  the most delayed postings.
- Daily windows are half-open, aligned to 21:00 UTC closes, each separated
  by a one-day purge gap: train [2003-01-02, 2012-01-01), validation
  [2012-01-02, 2017-01-01), holdout [2017-01-02, 2020-05-15).
- All six series share one PIT store (`pit-1d/`): every series is daily
  at 21:00 UTC, so no cross-frequency collision of the kind study 001
  found between daily and hourly stores can occur.

## Definitions and transformations

- **Variables are log changes.** Volatility levels are mean-reverting and
  thesis H2 concerns standardized moves, so every test uses close-to-close
  log changes of the index levels (the panel's per-trading-day log
  returns; no `bar_seconds` filter, since US trading days have weekend
  gaps).
- **Missing-data policy:** no forward filling; incomplete synchronized
  rows are dropped and the dropped count is reported (54 close rows, 55
  return rows).
- **Primary test:** partial lead-lag OLS of VIX[t+1] on VIX[t] and SPX[t]
  (base) versus the same plus TYVIX[t] (augmented), lag 1, Newey-West HAC
  standard errors (max lag 5 daily, 4 weekly). The SPX factor is the
  return over the same day as the source TYVIX move — both are known at
  the decision time, so no future information enters.
- **Test family (Holm, target FWER 0.05):** (a) daily TYVIX→VIX with SPX
  control (primary); (b) daily TYVIX→VXN with SPX control (secondary);
  (c) weekly TYVIX→VIX with SPX control (robustness; Friday-close to
  Friday-close log changes, last trading day of the week when Friday is
  a holiday). No-factor versions of each test are reported as upper-bound
  controls.
- **Walk-forward:** purged chronological splits, initial train 1,000 rows,
  test windows 126 rows, 1-day embargo. A regression row's label (the VIX
  log change over the next trading day) is known at the next row's close,
  so label ends are the exact next-row event times — a Friday row's label
  ends Monday, handling weekends and holidays exactly. OOS R² is scored
  on all folds and, for the acceptance criterion, on the preregistered
  holdout window only.
- **Cost gate (INFORMATIONAL, not a verdict criterion):** volatility
  indices are not tradable; VIX exposure requires VIX futures, and no
  reliable free VIX futures series exists (Yahoo `VX=F` returns no data,
  verified 2026-11-18), so futures roll costs cannot be measured from
  free data. The trial reports the gross sign-rule edge on holdout OOS
  augmented forecasts (1x, always invested while positioned, no costs
  applied) as an upper bound on any tradable edge, with a block-bootstrap
  CI. The holdout OOS incremental R² criterion carries the economic
  weight.
- **Descriptives (not in the test family, no verdict weight):** reverse
  placebo (VIX→TYVIX lag 1); sub-period stability of the primary
  coefficient (2003–2007, 2008–2012, 2013–2017, 2018–2020); the
  rolling-percentile check of the thesis's MOVE-99th / VXN-34th claim
  (trailing 252-day percentile ranks); the trailing-z-score robustness
  (252-day window, strictly prior); the factor-timing sensitivity
  (primary test with the SPX factor on the target day).

## Results

### Step 1 — Naive scan (descriptive)

Correlation between TYVIX[t] and VIX[t+k], daily, n = 4,328 at lag 0:

| lag | 0 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| correlation | 0.362 | −0.039 | −0.015 | −0.010 | −0.036 | −0.016 |

Same-day co-movement is substantial (0.362): rates volatility and equity
volatility move together within the day. The raw lag-1 correlation is
essentially zero (−0.039, wrong sign) and every longer lag is near zero.
As in study 001, information is contemporaneous, not lagged.

### Steps 3–4 — Partial lead-lag tests

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) daily TYVIX→VIX, SPX control | 4,327 | −0.0093 | 0.0328 | −0.28 | 0.776 | 1.0 | 0.000035 | 0.000035 |
| (a) no-factor control | 4,327 | −0.0078 | 0.0337 | −0.23 | 0.818 | — | 0.000024 | 0.000024 |
| (b) daily TYVIX→VXN, SPX control | 4,327 | −0.0137 | 0.0322 | −0.43 | 0.670 | 1.0 | 0.00010 | 0.00010 |
| (b) no-factor control | 4,327 | −0.0140 | 0.0328 | −0.43 | 0.671 | — | 0.00011 | 0.00011 |
| (c) weekly TYVIX→VIX, SPX control | 905 | −0.0047 | 0.0583 | −0.08 | 0.936 | 1.0 | 0.0000086 | 0.0000086 |
| (c) no-factor control | 905 | −0.0047 | 0.0586 | −0.08 | 0.936 | — | 0.0000086 | 0.0000086 |

No test in the family rejects. The primary coefficient (−0.009 ± 0.033)
is consistent with zero and wrong-signed, and its partial R² (0.000035)
is ~144x below the preregistered minimum effect size of 0.005. The
no-factor upper-bound controls are equally null, so the null is not an
artefact of the SPX factor absorbing the effect. The weekly test agrees
with the daily tests (coefficient near zero, wrong sign). Base-model R²
is ~0.012 daily and ~0.030 weekly: next-day VIX log changes are close to
unpredictable, as expected for a volatility index.

### Step 5 — Purged walk-forward OOS

27 folds, 0 skipped, 3,327 test rows. All-folds incremental OOS R² is
**−0.00099**; holdout-only (8 folds, 841 rows) is **−0.00154** (baseline
MSE 0.007405 vs augmented MSE 0.007416). Adding lag-1 TYVIX does not
improve out-of-sample forecasts; it slightly worsens them, in full and
on holdout alike.

### Step 6 — Cost gate (informational)

Sign rule on the 841 holdout OOS days: gross daily edge **+0.39%**,
block-bootstrap 95% CI [−0.10%, +0.88%], bootstrap p = 0.127 (block
length 10, 2,000 resamples, seed 42), sign accuracy 53.2%. The gross
edge is positive but not significant — the interval includes zero — and
it is gross: no costs of any kind are applied, and VIX futures roll
costs (unmeasurable from free data) would reduce it. It is reported for
completeness only and carries no verdict weight. Note the tension with
the OOS R²: the sign rule gets the direction right slightly more often
than not, but the augmented model's squared-error forecasts are worse
than the baseline's — direction accuracy without magnitude accuracy.

### Descriptives (not in the test family)

**Reverse placebo (VIX→TYVIX, lag 1).** Coefficient +0.043 ± 0.021,
p = 0.045, partial R² = 0.0018, n = 4,327. Nominally significant at
0.05 but small (below the 0.005 effect threshold) and uncorrected for
multiple comparisons across the descriptives. It does not support the
forward hypothesis; if anything, it weakly suggests any lead-lag runs
equity→rates, not rates→equity. Treated as noise-consistent, not as a
finding.

**Sub-period stability.** Primary-test coefficient by sub-period:

| sub-period | n | coef | SE | partial R² |
| --- | --- | --- | --- | --- |
| 2003–2007 | 1,236 | −0.020 | 0.050 | 0.00020 |
| 2008–2012 | 1,248 | +0.089 | 0.068 | 0.00310 |
| 2013–2017 | 1,248 | +0.021 | 0.051 | 0.00013 |
| 2018–2020 | 592 | −0.108 | 0.081 | 0.00450 |

The sign flips across sub-periods and no sub-period reaches the 0.005
partial-R² threshold. The relationship is unstable in the direction H2
allowed — and, pooled, absent.

**Rolling-percentile claim check.** Trailing 252-day percentile ranks of
TYVIX and VXN levels (4,073 rows; percentile correlation 0.44 — the two
vol percentiles usually move together, which is why divergences are
rare). The thesis's claimed configuration — TYVIX near its 99th
percentile while VXN sits near its 34th — is rare: the broad version
(TYVIX ≥ 99th, VXN ≤ 50th) occurred on **8 days (0.20%)**, the strict
version (VXN ≤ 34th) on **4 days (0.10%)**. What followed was VIX
*falling*, not rising: mean next-day VIX log change −3.4% (broad) /
−1.3% (strict); mean next-5-day −5.6% / −2.9%. With n = 8 and n = 4,
these means are descriptive only — but they point the opposite way from
any "rates vol extreme foreshadows equity vol spike" reading.

**Z-score sensitivity.** Primary test on trailing-252-day z-scored log
changes: coefficient +0.0071, p = 0.758, partial R² = 0.000044,
n = 4,075. Null, consistent with the primary test.

**Factor-timing sensitivity.** Primary test with the SPX factor measured
on the target day (t+1) instead of the predictor day: coefficient
+0.0044, p = 0.845, partial R² = 0.000016, n = 4,326. Null — the result
does not depend on the factor alignment, so the v1/v2 wording ambiguity
is empirically moot. (The t+1 control is not forecastable; this is an
explanatory decomposition only.)

## Verdict against the preregistered criteria

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted primary p < 0.05 | 1.0 | no |
| Primary partial R² ≥ 0.005 | 0.000035 | no |
| Holdout OOS incremental R² > 0 | −0.00154 | no |

All three acceptance criteria failed; all three complementary rejection
criteria triggered. **H0004 v2 is REJECTED.** There is no evidence that
lag-1 rates implied volatility predicts next-day VIX log changes on
2003–2020 data, at daily or weekly frequency, for VIX or VXN. The result
is a null, not a failure of method: the sample is large (4,327 daily
observations over 17 years), the design was preregistered, and the null
survives with and without the common-factor control, in-sample and
out-of-sample, on raw and z-scored changes, and under either factor
alignment. The two volatility markets move together within the day
(lag-0 correlation 0.362) and do not lead each other across days.

## Limitations

- **TYVIX is not MOVE.** Price volatility vs yield volatility differ by
  duration; a MOVE-based test could in principle differ. No free MOVE
  source exists, so this cannot be checked without licensed data.
- **Sample ends May 2020.** TYVIX was discontinued; the post-2020
  rate-hiking cycle — the largest rates-volatility regime in decades —
  is out of sample. Whether transmission exists in that regime is
  untested.
- **FRED publication lag is not modelled.** `available_at` equals the
  close; the most delayed postings could in principle blur the lag-1
  alignment by a day. The lag-0 correlation (0.362) is unaffected by
  this; the lag-1 null would need a systematic one-day misdating to be
  an artefact, which the shared 21:00 UTC convention makes unlikely.
- **Linear, lag-1 only.** The test is a linear lag-1 effect. Nonlinear,
  longer-lag, or volatility-level (rather than log-change) transmission
  is not tested. The naive scan's lags 2–5 are all near zero, which
  bounds the longer-lag concern descriptively.
- **SPX factor timing.** The factor is measured on the predictor day (t),
  controlling the day-t common shock; the day-t+1 common shock is not
  controlled. It is orthogonal to TYVIX[t] (future news at t), so
  omitting it costs power, not unbiasedness — and the factor-timing
  sensitivity (SPX[t+1] control) is equally null.
- **Cost assessment is gross only.** No VIX futures data, no roll-cost
  measurement, no tradability claim. The +0.39% gross edge is
  insignificant and would shrink under any realistic cost model.
- **HAC p-values are asymptotic.** With n = 4,327 the asymptotics are
  comfortable, but the p-values are not exact.
- **The reverse placebo is descriptive.** Its nominal p = 0.045 is
  uncorrected and the effect is small; it must not be cited as evidence
  of equity→rates transmission without a fresh preregistration.

## Reproducibility

- Preregistration: `research/move-vix-003/preregister.py` → H0004 v1,
  spec fingerprint
  `e188b2ff99df563d4ed6a4869e4c4a4f7a89c8c8724105cb2e6078c22877d27b`,
  superseded pre-trial by H0004 v2, spec fingerprint
  `c3923f5a530e924b68cce06ca8eb8c1d7aa4368f65d396d4f5dfbf4f454c5050`,
  registration hash
  `815e949a4fc706048a7c406456381b1f8c354fdfdca68d7c7cbfd68ccaaa1394`.
- Fetch: `research/move-vix-003/fetch_data.py` → `manifest.json`
  (SHA-256 `cde576cdc26826c736cf27c0764221f8f7d92c3e8c40e1f5e93431b732059878`).
- Trial: `research/move-vix-003/run_trial.py` → trial T0004, ledger record
  `77f2789ca1ea9540e0f89baede80cad82c8e80c2ea0b8eae39c8b1ba0494375b`,
  code revision `b2b025febcd147fa0a540eebc05442543e83d877`,
  config fingerprint
  `892fcd446fb3656ea19a51bd2852146c7d2188a5d5daed2c4941e2fc55b0ef8b`.
- Re-run from the repo root (after `fetch_data.py` restores the local
  cache): `.venv/bin/python research/move-vix-003/run_trial.py`. The trial
  refuses to run twice under the same trial id; the ledger is the permanent
  record.

# Credit-spread changes lead Nasdaq-100 volatility (study 011)

Eleventh empirical study in myquant Stage 3, and the fourth real use
of the Stage 6c scaffold. Research question: does the latest available
BAA10Y credit-spread change predict the next-day VXN log change,
beyond VXN's own history and the SPX common-factor control?
This is the planner's rank-1 candidate pair after study 010 consumed
BAA10Y→VIX (6a, total score 1.00, adjacent supported edge E0026).
It is also the first study to use the refreshed VXN panel (PR #25),
which extended VXNCLS to 2026-11-17.

**Verdict: H0016 v1 REJECTED** (trial T0019). The latest available
BAA10Y change does not predict the next-day VXN log change: the
primary coefficient is negative (the opposite of the preregistered
positive expectation), p = 0.8001, partial R² = 2.29e-05 — 219x below
the preregistered minimum effect size. The holdout out-of-sample
incremental R² is positive (+0.000024) and passes its criterion, but
by a hair: it is an MSE difference of 9.7e-08, pure noise. One of
three preregistered acceptance criteria passes; the two decisive ones
fail by orders of magnitude.

All numbers in this report are quoted from the trial ledger record
`44686089ef56366aed448d23b43672a4dd868504511cd10be788a5f5b8228be4`
(recorded 2026-11-19T03:54:43Z, code revision
`4dce59279bd87f40d7ff1a39a386a08383bff921`), the fetch manifest
(SHA-256
`bb95030be14d098ce95826ba32ad9002aaa4ed25f9becd52e185f389908466f6`),
and the panel summary. Nothing here is hand-transcribed from a
screen; the ledger is the source.

## Design

H0016 v1 was preregistered before any result was examined
(registration hash
`ecfc42e1cf2d687b6195ad10e6ff2da20b93c0cd83107549c1bba0db4c6e624e`,
spec fingerprint
`2d7b9758a204e4f86a7e27ec7c5a60679293bedd942e6e88c451ff4d87d8691b`).
The full design is in
`research/credit-spread-vxn-011/design.json`; the registered spec
is in `research/credit-spread-vxn-011/hypotheses/registrations/H0016/v1.json`.

- **Predictor**: the daily BAA10Y level change in basis points (not
  the log return the planner draft names — a spread quoted in
  percentage points has no meaningful log return; the same correction
  studies 008/009/010 made). **Lagged 2 trading days by availability**
  (see the publication-lag section below).
- **Target**: the VXN daily **log change**. VXN is an index level,
  so the log change is the correct target; the draft's "VXN return"
  is loose wording for the same thing.
- **Control**: the SPX log return (SPX[t], unlagged — Yahoo posts
  the close the same evening, so the day-t SPX change is knowable at
  the decision close; study 003's factor-alignment precedent). Lagged
  VIX is deliberately not the control: VIX and VXN are highly
  correlated equity-volatility indices, so a VIX control would absorb
  the common volatility factor the hypothesis is about and make the
  test overly conservative. TYVIX would truncate the sample at 2020.
  SPX returns are the natural equity common factor.
- **Expected direction: positive.** Credit-spread widening reflects
  credit stress, and credit stress usually accompanies rising equity
  volatility; the Nasdaq-100 is growth- and technology-heavy, so its
  volatility may be at least as sensitive to credit conditions as
  broad-market volatility. The draft's "positive, out-of-sample
  component" refers to positive incremental explanatory power
  (incremental R² > 0), not to a positive coefficient — the two are
  stated separately in the preregistration.
- **Model**: the base model predicts the next-day VXN log change
  from VXN's own lagged log change and the SPX log return; the
  augmented model adds the lagged BAA10Y change. HAC standard
  errors (Newey-West, max lag 5). The test family has one test (the
  primary), Holm-adjusted.
- **Verdict criteria (study 003's three)**: Holm-adjusted primary p
  below 0.05; primary partial R² at least 0.005; holdout out-of-sample
  incremental R² above 0. There is no cost gate criterion in the
  verdict — see the cost-gate section.
- **Windows** (21:00 UTC daily closes, one-day purge gaps):
  train [2003-01-02, 2020-01-01), validation [2020-01-02, 2024-01-01),
  holdout [2024-01-02, 2026-11-19). Minimum observations:
  1000 / 500 / 300. Walk-forward: initial train 1000 rows, test
  window 126, embargo 1 day. Bootstrap: block length 10, 2000
  resamples, seed 42.
- **Sub-periods** (study 003's 5-year blocks, extended to the full
  window — the same split studies 008/010 used): 2003–2007, 2008–2012,
  2013–2017, 2018–2022, 2023–2026.

### Full window: first study on the refreshed VXN panel

VXN is still published, so the sample runs 2003-01-02 → 2026-11-17
(the FRED legs bind one trading day behind the fetch date). This is
the first study to use the refreshed VXN panel from PR #25, which
re-pulled the full VXNCLS series to 2026-11-17 (6,487 valued rows,
2001-02-02 → 2026-11-17). At n = 5,955 this is the lab's third-largest
lead-lag sample, after studies 008 and 010 (both n = 5,957). The
sample covers the 2008 crisis, the 2020 COVID crash, and the 2022–2023
rate-shock period.

### Publication lag (the core PIT issue)

BAA10Y posts about a day later than other FRED series (6b evidence
probe 2026-11-18T21:45Z: BAA10Y latest 2026-11-16, VXNCLS already
2026-11-17). FRED daily values generally post on the next business day
(study 007, N=1), so BAA10Y's effective availability lag is
**2 trading days**: at the close of day t, the latest available
BAA10Y value is dated t-2, and the latest available change is the
change ending t-2. The predictor for the VXN log change over t+1 is
therefore the BAA10Y change ending at t-2 — a lag-2 predictor by
value date, deliberately. The SPX control carries no lag: Yahoo posts
the close the same evening, so SPX[t] is knowable at the decision
close. Both lags are applied in the trial's panel construction via
the study-007 lagged-changes module
(`myquant.studies.publication_lag.lagged_changes_on_index`); the PIT
store itself records `available_at` equal to the event time (adapter
limitation — see the design's known confounders). The fetch script
re-verifies the posting pattern behaviorally and records the observed
last dates in the manifest.

The trial's descriptive naive alignment (unlagged changes, the
lookahead version) quantifies what ignoring the publication lag would
buy; it is not part of the test family.

One convention to note: the own-history baseline uses the VXN log
change over day t as a predictor for the change over t+1. Under the
study's source-based PIT convention (FRED posts day-t values the next
business day), the day-t VXN value is published the next morning, so
the baseline uses information the FRED source had not yet published
at the decision close. The same convention was used in studies 003,
009 and 010. It strengthens the baseline against the source, so the
incremental test is conservative: the source must beat a baseline
that already knows the target's most recent change.

### Cost gate: informational only

VXN is a volatility index and is not tradable. VXN futures (VN) did
exist on CFE — CFTC-certified 2012-05-08, listed through at least
2019 — but they are not in CFE's current product list (the March 2026
expiration circular lists no VN; broker specification pages list only
VX/VXM/VXT for CFE volatility), and no free VXN futures price series
exists from which roll costs could be measured: Yahoo VN=F returns no
data (verified 2026-11-19 — HTTP 404). (The study brief assumed VXN
futures do not exist at all; verification corrected that — they
existed historically but are no longer listed. The informational
treatment stands, on the corrected facts.) Following study 003's
precedent for a volatility-index target, the cost gate is
**informational, not a verdict criterion**: the trial reports the
gross sign-rule edge on holdout out-of-sample augmented forecasts
(1x, always invested while positioned, no costs applied) with a
block-bootstrap CI, under the metrics key `cost_gate_informational`.
The verdict takes only the three criteria above. This was fixed in the
preregistration, before any result was seen.

## Data

Universe:

- `credit:baa-10y-spread` (FRED BAA10Y)
- `index:vxn` (FRED VXNCLS)
- `index:sp500` (Yahoo ^GSPC, control leg)

Sources: `fred`, `yahoo-finance`. Calendar: `us-equity`. Fetched
2026-11-19T03:53:45Z from the public fredgraph CSV endpoints (no API
key, no custom User-Agent — study 003's lesson: requests with a
custom User-Agent hang) and the Yahoo query2 chart endpoint
(`User-Agent: Mozilla/5.0`, with the longName and positivity
fail-fast checks from studies 003/008).

| Series | Values | Missing | First | Last |
| --- | --- | --- | --- | --- |
| BAA10Y | 5,968 | 261 | 2003-01-02 | 2026-11-17 |
| VXN (VXNCLS) | 6,009 | 221 | 2003-01-02 | 2026-11-17 |
| SPX (^GSPC) | 6,009 | 0 | 2003-01-02 | 2026-11-18 |

The per-instrument counts match study 010's manifest exactly for the
BAA10Y and SPX legs (same series, same window). The VXN counts match
the PR #25 refresh record exactly: the overlap segment
(2003-01-02 → 2020-05-15, 4,372 valued / 161 missing) plus the new
segment (2020-05-18 → 2026-11-17, 1,637 valued / 60 missing) sum to
6,009 valued / 221 missing in this study's window. The full-series
VXNCLS payload SHA-256 matches the refresh record (`8d356b55…`), and
the full-series BAA10Y payload SHA-256 matches studies 008/010
(`d803ed7c…`), so the shared data are the same FRED vintage. The
planner template estimated 5,967 joint rows; the panel came in at
5,958 return rows.

Panel (diff-then-join: changes computed per series on its own dates
first, then joined — the study-003 method): **5,959 close rows,
5,958 return rows, 2003-01-03 → 2026-11-17, 60 dropped close rows,
61 dropped return rows**. The regression frame drops the first two
rows (no lag-2 BAA10Y change exists there): 5,956 rows,
2003-01-07 → 2026-11-17. The primary test uses 5,955 rows (one row
is lost to the target's one-day-ahead shift).

Quality issues: none. Raw payloads live only in the local cache at
`data/cache/credit-spread-vxn-011/` (gitignored) and are never
committed.

### Publication-lag verification

The fetch re-checked the posting lag behaviorally (same procedure as
studies 008/009/010). At fetch time (2026-11-19T03:53:45Z, i.e.
2026-11-18 22:53 US Eastern), BAA10Y and VXNCLS both ended
2026-11-17, with 2026-11-18 the most recent trading day. Combined
with the 6b probe (2026-11-18T21:45Z, 45 minutes after the US close:
BAA10Y one trading day behind the reference series), the picture is
the same as studies 008/009/010's: BAA10Y posts in the post-close
evening window (US Eastern 16:45–19:25), so at any close the latest
available value is two trading days old, and the effective
2-trading-day lag stands. The lag-check details are in the manifest
and the panel summary.

## Results

All results are from trial T0019 (ledger record
`44686089…`, recorded 2026-11-19T03:54:43Z). The test family has one
test — the primary — so the Holm adjustment is the identity on it.

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily BAA10Y→VXN, SPX control (primary) | 5,955 | −0.000097 | 0.000384 | −0.25 | 0.8001 | 0.8001 | 2.29e-05 | 2.27e-05 |
| no-factor control | 5,955 | −0.000187 | 0.000367 | −0.51 | 0.6110 | — | 8.47e-05 | 8.43e-05 |
| naive (unlagged) alignment | 5,955 | −0.000074 | 0.000323 | −0.23 | 0.8177 | — | 1.29e-05 | 1.28e-05 |
| reverse placebo (VXN→BAA10Y) | 5,955 | −1.3717 | 1.1511 | −1.19 | 0.2334 | — | 0.000397 | 0.000387 |

### Primary test: lagged BAA10Y change → next-day VXN log change

| Statistic | Value |
| --- | --- |
| Observations | 5,955 |
| Coefficient (per bp) | −0.000097 |
| HAC standard error (lag 5) | 0.000384 |
| t-statistic | −0.253 |
| p-value | 0.8001 |
| Holm-adjusted p-value | 0.8001 |
| Partial R² | 2.29e-05 |
| Incremental R² | 2.27e-05 |
| Base R² → augmented R² | 0.007742 → 0.007765 |

The coefficient has the **wrong sign** against the preregistered
positive expectation, is a quarter of its own standard error, and the
partial R² is 219x below the preregistered minimum effect size of
0.005. In economic terms: a one-standard-deviation BAA10Y move
(3.01bp) predicts a −0.029% ± 0.116% next-day VXN log change —
nothing, on a target whose daily log-change standard deviation is
6.12%.

The no-factor upper bound (no SPX control, same predictor) is the
same null: coefficient −0.000187/bp, p = 0.6110, partial R² =
8.47e-05. The control is not masking an effect.

### Power: what this null rules out

The minimum detectable effect at 80% power (λ = 2.8016, n = 5,955,
one added regressor) is partial R² ≈ 0.001316 — the same MDE as
studies 008/010, which had the same sample size. The observed 2.29e-05
is ~58x below the MDE, and the 0.005 threshold is 3.80x above it — the
study was powered to detect effects far smaller than the
preregistered minimum, and found nothing. The null rules out any
effect at or above partial R² ≈ 0.0013. It does not rule out a tiny
effect below that bound; but an effect that small is not a
transmission mechanism worth chasing.

### Naive lead-lag scan (descriptive)

Pearson correlations between the BAA10Y change and the VXN log
change at lags 0–5 (unlagged changes, descriptive only):

| Lag | n | r |
| --- | --- | --- |
| 0 (same day) | 5,956 | +0.1600 |
| 1 | 5,955 | −0.0226 |
| 2 | 5,954 | −0.0072 |
| 3 (tradeable, PIT-correct) | 5,953 | −0.0080 |
| 4 | 5,952 | −0.0165 |
| 5 | 5,951 | +0.0202 |

The same-day correlation is +0.1600 — credit spreads and Nasdaq-100
volatility move together **within** the day, as the mechanism would
suggest — but every lagged correlation is near zero. The pattern is
the lab's recurring one: information moves same-day and does not
carry over to the next day. (The tradeable alignment is lag 3 in scan
terms — lag 1 in regression terms plus the 2-trading-day publication
lag — and it is −0.0080, nothing.)

### Naive alignment (lookahead, descriptive)

Running the primary regression with unlagged (same-day) BAA10Y
changes — the version that peeks at data not yet available at the
close — also gives nothing: coefficient −0.000074/bp (wrong sign),
p = 0.8177, partial R² = 1.29e-05, n = 5,955. It is not significant
and its partial R² is 100x below the MDE (0.001316).
**The publication lag is not what killed the effect**: even with
lookahead, the lagged transmission is absent.

### Reverse placebo (descriptive, not in the test family)

VXN → BAA10Y (lagged VXN log change predicting the next-day BAA10Y
change): coefficient −1.3717 bp per unit log change, p = 0.2334,
partial R² = 0.000397, n = 5,955. Not significant. A +10% VXN day
predicts a −0.14bp narrowing the next day — small, and the interval
covers zero. Unlike study 008, where the reverse placebo was
nominally significant (p = 0.0004, partial R² = 0.0087), here even
the reverse direction is a null — as in studies 009 and 010.
Descriptive only; it enters no verdict.

### Sub-period stability (descriptive)

| Sub-period | n | Coefficient (per bp) | SE | Partial R² |
| --- | --- | --- | --- | --- |
| 2003–2007 | 1,243 | +0.000724 | 0.000659 | 0.001169 |
| 2008–2012 | 1,248 | −0.000381 | 0.000563 | 0.000599 |
| 2013–2017 | 1,248 | −0.000050 | 0.001029 | 2.49e-06 |
| 2018–2022 | 1,247 | +0.000199 | 0.001070 | 0.000100 |
| 2023–2026 | 965 | −0.000691 | 0.000592 | 0.001034 |

No stable effect. The coefficient flips sign across sub-periods
(positive in 2003–2007 and 2018–2022, negative in the other three),
and no sub-period's partial R² comes within 4x of the 0.005
threshold. The 2003–2007 partial R² (0.001169) is the largest of the
five — still below the full-sample MDE (0.001316) — and it is the
only sub-period value above 0.001. There is no regime in which the
preregistered effect appears.

### Walk-forward out-of-sample

40 folds, 0 skipped, 4,955 test rows. All-folds OOS incremental R²
= −0.000985 (baseline MSE 0.0041425, augmented MSE 0.0041466);
**holdout (7 folds, 716 rows): OOS incremental R² = +0.000024**
(baseline MSE 0.0041175, augmented MSE 0.0041174 — a 9.7e-08 MSE
difference, noise). The holdout criterion passes, but only in the
sense that a coin landing on its edge counts as heads: the augmented
model's holdout forecasts are better than the baseline's by less than
one part in 40,000 of the MSE. Per-fold incremental R² values hover
within ±0.004 of zero with no pattern, except fold 5 (2009-01-13 →
2009-07-14, the crisis fold) at −0.03786 — the same fold that was
the outlier in studies 008 (−0.03895) and 010 (−0.03694). Adding the
BAA10Y predictor makes out-of-sample forecasts slightly worse in
full, and negligibly better on the holdout by an amount that is
indistinguishable from zero.

### Informational cost assessment (not a verdict criterion)

The gross sign-rule edge on the 716 holdout OOS augmented forecasts
is **+0.306% per day**, block-bootstrap 95% CI [−0.142%, +0.727%],
bootstrap p = 0.1714, sign accuracy 51.1%. The interval includes zero
and the bootstrap p is 0.17 — the one number that looked positive in
study 009 (p = 0.0375) does not even do that here, as in study 010.
And the same caveats apply regardless:

1. It is **gross with zero costs applied**, on an index that is not
   tradable. There is no instrument that pays the VXN log change, so
   the "edge" has no P&L meaning; it is an upper bound on a tradable
   edge that does not exist.
2. It contradicts the all-folds negative OOS R². The sign rule is
   direction accuracy without magnitude accuracy: the augmented
   model's forecasts get the sign right barely more often than chance
   (51.1%) while its squared-error forecasts are worse than the
   baseline in full. A model that is directionally lucky and
   magnitude-wrong is not a transmission mechanism.
3. It is **not in the verdict** — the preregistration fixed the
   three-criterion verdict before any result was seen, and the
   informational assessment carries no verdict weight. The same
   tension (positive gross edge, negative OOS R²) appeared in
   studies 003, 009 and 010 and was treated the same way.

The informational assessment is reported because the preregistration
said it would be reported — not because it changes anything.

## Verdict

| Criterion | Threshold | Observed | Pass |
| --- | --- | --- | --- |
| Holm-adjusted primary p | < 0.05 | 0.8001 | No |
| Primary partial R² | ≥ 0.005 | 2.29e-05 | No |
| Holdout OOS incremental R² | > 0 | +0.000024 | Yes (by a hair) |

**H0016 v1 REJECTED** — 1 of 3 criteria pass. The state transition
was recorded with the trial numbers as the reason; the ledger is
anchored (`trials.jsonl.anchor`, 1 record, latest hash
`44686089…`).

The rejection is not a borderline call: the primary p is 0.80, the
effect size is 219x below the minimum, the lookahead version is also
null, and no sub-period shows the effect. The one passing criterion
is a 9.7e-08 MSE improvement on the holdout — a rounding-level
difference, not evidence of transmission. The mechanism — credit
stress today lifting Nasdaq-100 volatility tomorrow — does not survive
contact with 23 years of daily data. Same-day co-movement (+0.1600)
is real, but it is not transmission: the information is in the price
the same day and does not carry over.

## Limitations

- **Daily frequency.** The transmission, if it exists at intraday
  horizons, is invisible here. The same-day correlation (+0.1600)
  hints that whatever co-movement exists is fast; daily data cannot
  say which side moves first within the day.
- **One control.** Only the SPX log return was controlled for.
  Other common factors (rates level changes, credit conditions,
  rates volatility) were not in the model. The no-factor upper bound
  is also null, which limits how much a missing control could be
  hiding, but it does not eliminate the possibility.
- **The holdout OOS criterion passes by a hair (+0.000024).** It is
  a 9.7e-08 MSE difference on 716 rows — indistinguishable from zero,
  and the all-folds OOS R² is negative (−0.000985). It is not a
  finding; it is a reminder that a > 0 threshold with no magnitude
  floor can pass on noise, and that the verdict rests on the two
  decisive criteria, which fail by orders of magnitude.
- **The informational gross edge (+0.306%/day, p = 0.1714) is a
  descriptive statistic on an untradable index.** See the
  cost-assessment section for why it carries no weight.
- **The 2-trading-day BAA10Y lag is assumed constant across
  2003–2026** (verified only at fetch time). If the historical
  posting lag differed, the predictor alignment is wrong for those
  periods — but the naive unlagged alignment is also null, so a
  different lag assumption would not rescue the effect.
- **The refreshed VXN panel's overlap with study 003's window was
  verified at the aggregate level only** (row and missing counts
  match; the full-series payload SHA matches the PR #25 refresh). A
  count-preserving value revision in the pre-2020 VXNCLS data cannot
  be excluded — see `research/planner-6a/vxn_refresh.json`.

## Reproducibility

```bash
.venv/bin/python research/credit-spread-vxn-011/preregister.py   # idempotent after registration
.venv/bin/python research/credit-spread-vxn-011/fetch_data.py    # re-fetches; manifest SHA changes with fetch time
.venv/bin/python research/credit-spread-vxn-011/run_trial.py     # trial T0019 (already recorded; re-running creates T0020)
```

The trial binds the preregistered spec fingerprint
(`2d7b9758…`), the manifest SHA-256 (`bb95030b…`), and the code
revision (`4dce592b…`). Re-running the trial script records a new
trial against the current HEAD; it does not overwrite T0019.

## Scaffold feedback (fourth real use)

Study 008 recorded seven gaps from the 6c scaffold's first real use,
and studies 009 and 010 found no new gaps. This study hit **no new
gaps either**. Every hand-adaptation the study needed was a repeat of
a known item:

- The generated `run_trial.py` wired only the primary test and a
  two-criterion verdict, with walk-forward and the cost gate as
  `NotImplementedError` stubs — 008's item 1. Same replacement, same
  full pipeline.
- `preregister.py` was not idempotent — 008's item 4. Same fix
  (re-running after registration leaves the registration untouched).
- The scaffold generated a 2-instrument universe; the SPX control leg
  was added by hand — 008's item 6.
- The draft's predictor transform (log return of a spread) and target
  wording ("VXN return") needed the researcher's correction in the
  design — 008's items 5/7.
- The generated `fetch_data.py` had no Yahoo fail-fast checks and a
  hard-coded content type — 008's item 3 — and no publication-lag
  check (the lag check is study-specific work the scaffold never
  claimed to do).

One fix from study 008 verified: the generated `run_trial.py` now
passes `BAR_SECONDS = None` (the 008 bug, `bar_seconds=86400`, would
have voided every Monday return). Confirmed in the generated file
before adaptation.

One placeholder-hygiene check from study 009 verified: the generated
files contain no real-ID placeholder specs — only the real H0016
appears (the H9002/H9003/H9004 placeholders live only in the 6c
validation, not in generation).

# Credit-spread changes lead Treasury volatility (study 009)

Ninth empirical study in myquant Stage 3, and the second real use of
the Stage 6c scaffold. Research question: does the latest available
BAA10Y credit-spread change predict the next-day TYVIX log change,
beyond TYVIX's own history and the lagged VIX common-factor control?
This is the planner's rank-1 candidate pair after study 008 consumed
BAA10Y→SPX (6a, total score 1.00, adjacent supported edges E0023,
E0026, E0032).

**Verdict: H0014 v1 REJECTED** (trial T0017). The latest available
BAA10Y change does not predict the next-day TYVIX log change: the
primary coefficient is negative (the opposite of the preregistered
positive expectation), p = 0.7540, partial R² = 6.10e-05 — 82x below
the preregistered minimum effect size — and the holdout out-of-sample
incremental R² is negative (−0.000983). All three preregistered
acceptance criteria fail.

All numbers in this report are quoted from the trial ledger record
`4daa54ed5167d4644bbe65ebcff4ef10d5a53cd3ac85c9361e8eaf3e5813d7c5`
(recorded 2026-11-19T02:07:50Z, code revision
`f428fa664eed088367af8f60241ea8e5556952c7`), the fetch manifest
(SHA-256
`c7ba88626a716706936df2497a8ccad253378edf6e2f569299a1137969153f8c`),
and the panel summary. Nothing here is hand-transcribed from a
screen; the ledger is the source.

## Design

H0014 v1 was preregistered before any result was examined
(registration hash
`83ce945ffe7cc3666276dbf9e2dc11010ea179b89d82770ddf35e6b7633e6436`,
spec fingerprint
`435ae25855fdce42053a658c55ddeaa86503a8a5921d8ce03f8a0c7a4a26e655`).
The full design is in
`research/credit-spread-tyvix-009/design.json`; the registered spec
is in `research/credit-spread-tyvix-009/hypotheses/registrations/H0014/v1.json`.

- **Predictor**: the daily BAA10Y level change in basis points (not
  the log return the planner draft names — a spread quoted in
  percentage points has no meaningful log return; the same correction
  study 008 made). **Lagged 2 trading days by availability** (see the
  publication-lag section below).
- **Target**: the TYVIX daily **log change**. TYVIX is an index
  level like VIX, so the log change is the correct target; the draft's
  "TYVIX return" is loose wording for the same thing.
- **Control**: the lagged VIX log change (lag 1, VIXCLS's own
  1-trading-day FRED lag) — the same control study 008 used, chosen
  for comparability. Equity volatility is the common factor behind
  rates volatility; lagged SPX returns were the alternative and were
  not used.
- **Expected direction: positive.** Credit-spread widening reflects
  credit stress, and credit stress usually accompanies rising rates
  volatility. The draft's "positive, out-of-sample component" refers
  to positive incremental explanatory power (incremental R² > 0), not
  to a positive coefficient — the two are stated separately in the
  preregistration.
- **Model**: the base model predicts the next-day TYVIX log change
  from TYVIX's own lagged log change and the lagged VIX log change;
  the augmented model adds the lagged BAA10Y change. HAC standard
  errors (Newey-West, max lag 5). The test family has one test (the
  primary), Holm-adjusted.
- **Verdict criteria (study 003's three)**: Holm-adjusted primary p
  below 0.05; primary partial R² at least 0.005; holdout out-of-sample
  incremental R² above 0. There is no cost gate criterion in the
  verdict — see the cost-gate section.
- **Windows** (21:00 UTC daily closes, one-day purge gaps):
  train [2003-01-02, 2012-01-01), validation [2012-01-02, 2017-01-01),
  holdout [2017-01-02, 2020-05-16). Minimum observations:
  1000 / 500 / 300. Walk-forward: initial train 1000 rows, test
  window 126, embargo 1 day. Bootstrap: block length 10, 2000
  resamples, seed 42.
- **Sub-periods** (study 003's split): 2003–2007, 2008–2012,
  2013–2017, 2018–2020.

### Truncated sample: TYVIX is discontinued

TYVIX (FRED series VXTYN) stopped publishing on 2020-05-15, so the
sample window is 2003-01-02 → 2020-05-15 by construction. This is a
historical-sample study: its conclusions cover 2003–2020 only and say
nothing about the post-2020 regime (including the 2022–2023 rate-shock
period, which is outside the sample). The holdout window ends
2020-05-16 because the fetch window is half-open on 21:00 UTC event
times; the last panel row is 2020-05-15.

### Publication lag (the core PIT issue)

BAA10Y posts about a day later than other FRED series (6b evidence
probe 2026-11-18T21:45Z: BAA10Y latest 2026-11-16, VIXCLS already
2026-11-17). FRED daily values generally post on the next business day
(study 007, N=1), so BAA10Y's effective availability lag is
**2 trading days**: at the close of day t, the latest available
BAA10Y value is dated t-2, and the latest available change is the
change ending t-2. The predictor for the TYVIX log change over t+1 is
therefore the BAA10Y change ending at t-2 — a lag-2 predictor by
value date, deliberately. The VIX control carries the standard
1-trading-day lag. Both lags are applied in the trial's panel
construction via the study-007 lagged-changes module
(`myquant.studies.publication_lag.lagged_changes_on_index`); the PIT
store itself records `available_at` equal to the event time (adapter
limitation — see the design's known confounders). The fetch script
re-verifies the posting pattern behaviorally and records the observed
last dates in the manifest.

The trial's descriptive naive alignment (unlagged changes, the
lookahead version) quantifies what ignoring the publication lag would
buy; it is not part of the test family.

### Cost gate: informational only

TYVIX is a volatility index and is not tradable; there are no listed
TYVIX futures, and Treasury-volatility exposure through options on
Treasury futures has no clean free price series from which costs could
be measured. Following study 003's precedent for a volatility-index
target (VIX is likewise not directly tradable), the cost gate is
**informational, not a verdict criterion**: the trial reports the
gross sign-rule edge on holdout out-of-sample augmented forecasts
(1x, always invested while positioned, no costs applied) with a
block-bootstrap CI, under the metrics key `cost_gate_informational`.
The verdict takes only the three criteria above. This was fixed in the
preregistration, before any result was seen.

## Data

Universe:

- `credit:baa-10y-spread` (FRED BAA10Y)
- `index:tyvix` (FRED VXTYN)
- `index:vix` (FRED VIXCLS, control leg)

Source: `fred` only. Calendar: `us-equity`. Fetched
2026-11-19T02:06:25Z from the public fredgraph CSV endpoints, no
API key, no custom User-Agent (study 003's lesson: requests with a
custom User-Agent hang).

| Series | Values | Missing | First | Last |
| --- | --- | --- | --- | --- |
| BAA10Y | 4,346 | 186 | 2003-01-02 | 2020-05-15 |
| TYVIX (VXTYN) | 4,363 | 169 | 2003-01-02 | 2020-05-15 |
| VIX (VIXCLS) | 4,374 | 158 | 2003-01-02 | 2020-05-15 |

The per-instrument counts match study 003's manifest exactly (same
series, same window). The planner template estimated 4,341 joint
rows; the panel came in at 4,330 return rows.

Panel (diff-then-join: changes computed per series on its own dates
first, then joined — the study-003 method): **4,331 close rows,
4,330 return rows, 2003-01-03 → 2020-05-15, 51 dropped close rows,
52 dropped return rows**. The regression frame drops the first two
rows (no lag-2 BAA10Y change exists there): 4,328 rows,
2003-01-07 → 2020-05-15. The primary test uses 4,327 rows (one row
is lost to the target's one-day-ahead shift).

Quality issues: none. Raw payloads live only in the local cache at
`data/cache/credit-spread-tyvix-009/` (gitignored) and are never
committed.

### Publication-lag verification

The fetch re-checked the posting lag behaviorally (same procedure as
study 008). At fetch time (2026-11-19T02:06:25Z, i.e. 2026-11-18
21:06 US Eastern), BAA10Y and VIXCLS both ended 2026-11-17, with
2026-11-18 the most recent trading day. Combined with the 6b probe
(2026-11-18T21:45Z, 45 minutes after the US close: BAA10Y one trading
day behind the reference series), the picture is the same as study
008's: BAA10Y posts in the post-close evening window (US Eastern
16:45–19:25), so at any close the latest available value is two
trading days old, and the effective 2-trading-day lag stands. The
full-series BAA10Y payload SHA-256 matches study 008's
(`d803ed7c…`), so the two studies' BAA10Y data are identical up to
the fetch moment. The lag-check details are in the manifest and the
panel summary.

## Results

All results are from trial T0017 (ledger record
`4daa54ed…`, recorded 2026-11-19T02:07:50Z). The test family has one
test — the primary — so the Holm adjustment is the identity on it.

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily BAA10Y→TYVIX, VIX control (primary) | 4,327 | −0.000126 | 0.000401 | −0.31 | 0.7540 | 0.7540 | 6.10e-05 | 6.08e-05 |
| no-factor control | 4,327 | −0.000133 | 0.000400 | −0.33 | 0.7387 | — | 6.89e-05 | 6.88e-05 |
| naive (unlagged) alignment | 4,327 | −0.000537 | 0.000421 | −1.28 | 0.2020 | — | 0.001098 | 0.001095 |
| reverse placebo (TYVIX→BAA10Y) | 4,327 | 2.5326 | 1.5971 | 1.59 | 0.1128 | — | 0.001691 | 0.001640 |

### Primary test: lagged BAA10Y change → next-day TYVIX log change

| Statistic | Value |
| --- | --- |
| Observations | 4,327 |
| Coefficient (per bp) | −0.000126 |
| HAC standard error (lag 5) | 0.000401 |
| t-statistic | −0.313 |
| p-value | 0.7540 |
| Holm-adjusted p-value | 0.7540 |
| Partial R² | 6.10e-05 |
| Incremental R² | 6.08e-05 |
| Base R² → augmented R² | 0.002670 → 0.002731 |

The coefficient has the **wrong sign** against the preregistered
positive expectation, is a third of its own standard error, and the
partial R² is 82x below the preregistered minimum effect size of
0.005. In economic terms: a one-standard-deviation BAA10Y move
(3.03bp) predicts a −0.038% ± 0.12% next-day TYVIX log change —
nothing, on a target whose daily log-change standard deviation is
4.88%.

The no-factor upper bound (no VIX control, same predictor) is the
same null: coefficient −0.000133/bp, p = 0.7387, partial R² =
6.89e-05. The control is not masking an effect.

### Power: what this null rules out

The minimum detectable effect at 80% power (λ = 2.8016, n = 4,327,
one added regressor) is partial R² ≈ 0.00181. The observed
6.10e-05 is ~30x below the MDE, and the 0.005 threshold is 2.76x
above it — the study was powered to detect effects far smaller than
the preregistered minimum, and found nothing. The null rules out any
effect at or above partial R² ≈ 0.0018. It does not rule out a tiny
effect below that bound; but an effect that small is not a
transmission mechanism worth chasing.

### Naive lead-lag scan (descriptive)

Pearson correlations between the BAA10Y change and the TYVIX log
change at lags 0–5 (unlagged changes, descriptive only):

| Lag | n | r |
| --- | --- | --- |
| 0 (same day) | 4,328 | +0.1081 |
| 1 | 4,327 | −0.0373 |
| 2 | 4,326 | −0.0057 |
| 3 (tradeable, PIT-correct) | 4,325 | −0.0074 |
| 4 | 4,324 | −0.0252 |
| 5 | 4,323 | +0.0154 |

The same-day correlation is +0.1081 — credit spreads and rates
volatility move together **within** the day, as the mechanism would
suggest — but every lagged correlation is near zero and most are
negative. The pattern is the lab's recurring one: information moves
same-day and does not carry over to the next day. (The tradeable
alignment is lag 3 in scan terms — lag 1 in regression terms plus the
2-trading-day publication lag — and it is −0.0074, nothing.)

### Naive alignment (lookahead, descriptive)

Running the primary regression with unlagged (same-day) BAA10Y
changes — the version that peeks at data not yet available at the
close — also gives nothing: coefficient −0.000537/bp (wrong sign),
p = 0.2020, partial R² = 0.001098, n = 4,327. It is the largest
partial R² among the four regressions, but it is still below the MDE
(0.00181), not significant, and wrong-signed. **The publication lag is
not what killed the effect**: even with lookahead, the lagged
transmission is absent.

### Reverse placebo (descriptive, not in the test family)

TYVIX → BAA10Y (lagged TYVIX log change predicting the next-day
BAA10Y change): coefficient +2.533 bp per unit log change,
p = 0.1128, partial R² = 0.001691, n = 4,327. Not significant. A
+10% TYVIX day predicts a +0.25bp widening the next day — small, and
the interval covers zero. Unlike study 008, where the reverse placebo
was nominally significant (p = 0.0004, partial R² = 0.0087), here
even the reverse direction is a null. Descriptive only; it enters no
verdict.

### Sub-period stability (descriptive)

| Sub-period | n | Coefficient (per bp) | SE | Partial R² |
| --- | --- | --- | --- | --- |
| 2003–2007 | 1,236 | −0.000181 | 0.000557 | 8.70e-05 |
| 2008–2012 | 1,248 | −0.000119 | 0.000336 | 1.07e-04 |
| 2013–2017 | 1,248 | −0.001017 | 0.000646 | 0.002132 |
| 2018–2020 | 592 | +0.000514 | 0.001693 | 0.000779 |

No stable effect. The coefficient is negative in three of four
sub-periods (the opposite of the expected sign) and positive only in
the shortest one, where its standard error is three times its size.
The 2013–2017 partial R² (0.002132) is the largest of the four but
is still below the 0.005 threshold, below the full-sample MDE, and
wrong-signed. There is no regime in which the preregistered effect
appears.

### Walk-forward out-of-sample

27 folds, 0 skipped, 3,327 test rows. All-folds OOS incremental R²
= −0.000778 (baseline MSE 0.0026023, augmented MSE 0.0026043);
**holdout (8 folds, 841 rows): OOS incremental R² = −0.000983**
(baseline MSE 0.0037506, augmented MSE 0.0037543). Per-fold
incremental R² values hover within ±0.003 of zero with no pattern
(worst fold −0.00872, best +0.00250). Adding the BAA10Y predictor
makes out-of-sample forecasts slightly worse, in full and on the
holdout.

### Informational cost assessment (not a verdict criterion)

The gross sign-rule edge on the 841 holdout OOS augmented forecasts
is **+0.457% per day**, block-bootstrap 95% CI [+0.048%, +0.915%],
bootstrap p = 0.0375, sign accuracy 54.9%. Read carefully — this is
the one number in the trial that looks positive, and it does not
rescue the rejection:

1. It is **gross with zero costs applied**, on an index that is not
   tradable. There is no instrument that pays the TYVIX log change,
   so the "edge" has no P&L meaning; it is an upper bound on a
   tradable edge that does not exist.
2. It contradicts the negative holdout OOS R². The sign rule is
   direction accuracy without magnitude accuracy: the augmented
   model's forecasts get the sign right slightly more often than
   chance (54.9%) while its squared-error forecasts are worse than
   the baseline. A model that is directionally lucky and
   magnitude-wrong is not a transmission mechanism.
3. It is **not in the verdict** — the preregistration fixed the
   three-criterion verdict before any result was seen, and the
   informational assessment carries no verdict weight. The same
   tension (positive gross edge, negative OOS R²) appeared in
   study 003 and was treated the same way.
4. The bootstrap p = 0.0375 is a single unadjusted descriptive
   statistic. It is not a test in any family, and it would not
   survive the lab's multiple-testing discipline if it were.

The informational assessment is reported because the preregistration
said it would be reported — not because it changes anything.

## Verdict

| Criterion | Threshold | Observed | Pass |
| --- | --- | --- | --- |
| Holm-adjusted primary p | < 0.05 | 0.7540 | No |
| Primary partial R² | ≥ 0.005 | 6.10e-05 | No |
| Holdout OOS incremental R² | > 0 | −0.000983 | No |

**H0014 v1 REJECTED** — 0 of 3 criteria pass. The state transition
was recorded with the trial numbers as the reason; the ledger is
anchored (`trials.jsonl.anchor`, 1 record, latest hash
`4daa54ed…`).

The rejection is not a borderline call: the primary p is 0.75, the
effect size is 82x below the minimum, the out-of-sample evaluation
is negative, the lookahead version is also null, and no sub-period
shows the effect. The mechanism — credit stress today lifting rates
volatility tomorrow — does not survive contact with 17 years of
daily data. Same-day co-movement (+0.1081) is real, but it is not
transmission: the information is in the price the same day and does
not carry over.

## Limitations

- **Historical sample only.** TYVIX ended in 2020-05, so nothing here
  speaks to the post-2020 regime. A TYVIX-like series for 2020+
  (e.g. an implied-vol index rebuilt from Treasury options) would be
  a different study with different data, not an extension of this one.
- **Daily frequency.** The transmission, if it exists at intraday
  horizons, is invisible here. The same-day correlation (+0.1081)
  hints that whatever co-movement exists is fast; daily data cannot
  say which side moves first within the day.
- **One control.** Only the lagged VIX log change was controlled for.
  Other common factors (rates level changes, equity returns, credit
  conditions) were not in the model. The no-factor upper bound is
  also null, which limits how much a missing control could be hiding,
  but it does not eliminate the possibility.
- **The naive alignment's partial R² (0.001098) is the largest in
  the trial.** It is below the MDE, not significant, and wrong-signed
  — but it is the only number that is not orders of magnitude below
  the bound. It is not a finding; it is a reminder that the
  lookahead version of this regression is the closest thing to
  signal in the study, and it is still noise.
- **The informational gross edge (+0.457%/day, p = 0.0375) is a
  descriptive statistic on an untradable index.** See the
  cost-assessment section for why it carries no weight.

## Reproducibility

```bash
.venv/bin/python research/credit-spread-tyvix-009/preregister.py   # idempotent after registration
.venv/bin/python research/credit-spread-tyvix-009/fetch_data.py    # re-fetches; manifest SHA changes with fetch time
.venv/bin/python research/credit-spread-tyvix-009/run_trial.py     # trial T0017 (already recorded; re-running creates T0018)
```

The trial binds the preregistered spec fingerprint
(`435ae258…`), the manifest SHA-256 (`c7ba8862…`), and the code
revision (`f428fa66…`). Re-running the trial script records a new
trial against the current HEAD; it does not overwrite T0017.

## Scaffold feedback (second real use)

Study 008 recorded seven gaps from the 6c scaffold's first real use.
This study hit **no new gaps**. Every hand-adaptation the study
needed was a repeat of a known item:

- The generated `run_trial.py` wired only the primary test and a
  two-criterion verdict, with walk-forward and the cost gate as
  `NotImplementedError` stubs — 008's item 1. Same replacement, same
  full pipeline.
- `preregister.py` was not idempotent — 008's item 3. Same fix
  (re-running after registration leaves the registration untouched).
- The scaffold generated a 2-instrument universe; the VIX control leg
  was added by hand — 008's item 4.
- The draft's predictor transform (log return of a spread) and target
  wording ("TYVIX return") needed the researcher's correction in the
  design — 008's items 5/6.
- The generated `fetch_data.py` had no publication-lag check and a
  hard-coded content type — 008's item 7.

One fix from study 008 verified: the generated `run_trial.py` now
passes `BAR_SECONDS = None` (the 008 bug, `bar_seconds=86400`, would
have voided every Monday return). Confirmed in the generated file
before adaptation.

The 6c validation's placeholder hypothesis ID `H0014`
(`research/scaffold-6c/validate_scaffold.py`, a mean-comparison spec
with study_number=9 and slug `btc-window-vol-009`) now coincides
with this study's real H0014. It is tmp-dir only and is never
registered — the other test types are generated and lint-checked
only — so there is no fingerprint collision. It is stale by the 6c
review precedent (the validation placeholder H0013 was renamed to
H9001 for exactly this reason) and should be renamed (e.g. H9002)
in a follow-up; it was not renamed in this study because it is
outside the study's scope and the validation still passes as-is.

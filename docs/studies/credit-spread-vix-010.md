# Credit-spread changes lead equity volatility (study 010)

Tenth empirical study in myquant Stage 3, and the third real use of
the Stage 6c scaffold. Research question: does the latest available
BAA10Y credit-spread change predict the next-day VIX log change,
beyond VIX's own history and the SPX common-factor control?
This is the planner's rank-1 candidate pair after study 009 consumed
BAA10Y→TYVIX (6a, total score 1.00, adjacent supported edges E0026,
E0033).

**Verdict: H0015 v1 REJECTED** (trial T0018). The latest available
BAA10Y change does not predict the next-day VIX log change: the
primary coefficient is negative (the opposite of the preregistered
positive expectation), p = 0.8896, partial R² = 6.55e-06 — 763x below
the preregistered minimum effect size — and the holdout out-of-sample
incremental R² is negative (−0.000019). All three preregistered
acceptance criteria fail.

All numbers in this report are quoted from the trial ledger record
`f97982756713de749850358a86a51e788bc134401ff3e24ef808dd6c4e7c8a2a`
(recorded 2026-11-19T02:55:55Z, code revision
`7ae59d7fe9302c606d64043a9cf2f6a81a7123c9`), the fetch manifest
(SHA-256
`8802891b81c3d3e71aa87fa9252c7127c1c40f33dcb63be3c02628e45ec891d0`),
and the panel summary. Nothing here is hand-transcribed from a
screen; the ledger is the source.

## Design

H0015 v1 was preregistered before any result was examined
(registration hash
`68d2db47661f7ec9feef48c0e20f161ec81d60efd7bac8fc61d6c51939a00e97`,
spec fingerprint
`eb8b21955fcf8ece287a15372b6ee845297a47d348325f5eae2bc728a1f001cf`).
The full design is in
`research/credit-spread-vix-010/design.json`; the registered spec
is in `research/credit-spread-vix-010/hypotheses/registrations/H0015/v1.json`.

- **Predictor**: the daily BAA10Y level change in basis points (not
  the log return the planner draft names — a spread quoted in
  percentage points has no meaningful log return; the same correction
  studies 008/009 made). **Lagged 2 trading days by availability**
  (see the publication-lag section below).
- **Target**: the VIX daily **log change**. VIX is an index level,
  so the log change is the correct target; the draft's "VIX return"
  is loose wording for the same thing.
- **Control**: the SPX log return (SPX[t], unlagged — Yahoo posts
  the close the same evening, so the day-t SPX change is knowable at
  the decision close; study 003's factor-alignment precedent). The
  lagged VIX control used in studies 008/009 cannot serve here
  because VIX is the target, and TYVIX would truncate the sample at
  2020; SPX returns are the natural equity common factor.
- **Expected direction: positive.** Credit-spread widening reflects
  credit stress, and credit stress usually accompanies rising equity
  volatility. The draft's "positive, out-of-sample component" refers
  to positive incremental explanatory power (incremental R² > 0), not
  to a positive coefficient — the two are stated separately in the
  preregistration.
- **Model**: the base model predicts the next-day VIX log change
  from VIX's own lagged log change and the SPX log return; the
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
  window — the same split study 008 used): 2003–2007, 2008–2012,
  2013–2017, 2018–2022, 2023–2026.

### Full window: VIX is still published

Unlike study 009, whose sample was truncated by TYVIX's
discontinuation in 2020, VIX is still published, so the sample runs
2003-01-02 → 2026-11-17 (the FRED legs bind one trading day behind
the fetch date). At n = 5,957 this is tied with study 008 for the
lab's largest lead-lag sample. The sample covers the 2008 crisis,
the 2020 COVID crash, and the 2022–2023 rate-shock period.

### Publication lag (the core PIT issue)

BAA10Y posts about a day later than other FRED series (6b evidence
probe 2026-11-18T21:45Z: BAA10Y latest 2026-11-16, VIXCLS already
2026-11-17). FRED daily values generally post on the next business day
(study 007, N=1), so BAA10Y's effective availability lag is
**2 trading days**: at the close of day t, the latest available
BAA10Y value is dated t-2, and the latest available change is the
change ending t-2. The predictor for the VIX log change over t+1 is
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

One convention to note: the own-history baseline uses the VIX log
change over day t as a predictor for the change over t+1. Under the
study's source-based PIT convention (FRED posts day-t values the next
business day), the day-t VIX value is published the next morning, so
the baseline uses information the FRED source had not yet published
at the decision close. The same convention was used in studies 003
and 009. It strengthens the baseline against the source, so the
incremental test is conservative: the source must beat a baseline
that already knows the target's most recent change.

### Cost gate: informational only

VIX is a volatility index and is not tradable; VIX exposure requires
VIX futures (CFE), and futures roll costs cannot be measured from
free data: Yahoo VX=F returns no data (verified by study 003 on
2026-11-18, re-verified here on 2026-11-19 — HTTP 404) and no other
reliable free VIX futures series was found. Following study 003's
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
- `index:vix` (FRED VIXCLS)
- `index:sp500` (Yahoo ^GSPC, control leg)

Sources: `fred`, `yahoo-finance`. Calendar: `us-equity`. Fetched
2026-11-19T02:53:32Z from the public fredgraph CSV endpoints (no API
key, no custom User-Agent — study 003's lesson: requests with a
custom User-Agent hang) and the Yahoo query2 chart endpoint
(`User-Agent: Mozilla/5.0`, with the longName and positivity
fail-fast checks from studies 003/008).

| Series | Values | Missing | First | Last |
| --- | --- | --- | --- | --- |
| BAA10Y | 5,968 | 261 | 2003-01-02 | 2026-11-17 |
| VIX (VIXCLS) | 6,042 | 187 | 2003-01-02 | 2026-11-17 |
| SPX (^GSPC) | 6,009 | 0 | 2003-01-02 | 2026-11-18 |

The per-instrument counts match study 008's manifest exactly for the
FRED legs (same series, same window); the SPX leg has one more bar
(2026-11-18), which drops out of the synchronized panel because the
FRED legs lag by a day. The planner template estimated 5,967 joint
rows; the panel came in at 5,960 return rows.

Panel (diff-then-join: changes computed per series on its own dates
first, then joined — the study-003 method): **5,961 close rows,
5,960 return rows, 2003-01-03 → 2026-11-17, 88 dropped close rows,
89 dropped return rows**. The regression frame drops the first two
rows (no lag-2 BAA10Y change exists there): 5,958 rows,
2003-01-07 → 2026-11-17. The primary test uses 5,957 rows (one row
is lost to the target's one-day-ahead shift).

Quality issues: none. Raw payloads live only in the local cache at
`data/cache/credit-spread-vix-010/` (gitignored) and are never
committed.

### Publication-lag verification

The fetch re-checked the posting lag behaviorally (same procedure as
studies 008/009). At fetch time (2026-11-19T02:53:32Z, i.e. 2026-11-18
21:53 US Eastern), BAA10Y and VIXCLS both ended 2026-11-17, with
2026-11-18 the most recent trading day. Combined with the 6b probe
(2026-11-18T21:45Z, 45 minutes after the US close: BAA10Y one trading
day behind the reference series), the picture is the same as studies
008/009's: BAA10Y posts in the post-close evening window (US Eastern
16:45–19:25), so at any close the latest available value is two
trading days old, and the effective 2-trading-day lag stands. The
full-series BAA10Y payload SHA-256 matches study 008's
(`d803ed7c…`) and the VIXCLS payload matches study 009's
(`eed5fb6b…`), so the three studies' shared data are the same FRED
vintage. The lag-check details are in the manifest and the panel
summary.

## Results

All results are from trial T0018 (ledger record
`f9798275…`, recorded 2026-11-19T02:55:55Z). The test family has one
test — the primary — so the Holm adjustment is the identity on it.

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily BAA10Y→VIX, SPX control (primary) | 5,957 | −0.000063 | 0.000451 | −0.14 | 0.8896 | 0.8896 | 6.55e-06 | 6.48e-06 |
| no-factor control | 5,957 | −0.000160 | 0.000434 | −0.37 | 0.7124 | — | 4.30e-05 | 4.26e-05 |
| naive (unlagged) alignment | 5,957 | +0.000090 | 0.000414 | +0.22 | 0.8276 | — | 1.30e-05 | 1.29e-05 |
| reverse placebo (VIX→BAA10Y) | 5,957 | −0.9936 | 1.0590 | −0.94 | 0.3481 | — | 0.000279 | 0.000272 |

### Primary test: lagged BAA10Y change → next-day VIX log change

| Statistic | Value |
| --- | --- |
| Observations | 5,957 |
| Coefficient (per bp) | −0.000063 |
| HAC standard error (lag 5) | 0.000451 |
| t-statistic | −0.139 |
| p-value | 0.8896 |
| Holm-adjusted p-value | 0.8896 |
| Partial R² | 6.55e-06 |
| Incremental R² | 6.48e-06 |
| Base R² → augmented R² | 0.010740 → 0.010747 |

The coefficient has the **wrong sign** against the preregistered
positive expectation, is a seventh of its own standard error, and the
partial R² is 763x below the preregistered minimum effect size of
0.005. In economic terms: a one-standard-deviation BAA10Y move
(3.01bp) predicts a −0.019% ± 0.136% next-day VIX log change —
nothing, on a target whose daily log-change standard deviation is
7.38%.

The no-factor upper bound (no SPX control, same predictor) is the
same null: coefficient −0.000160/bp, p = 0.7124, partial R² =
4.30e-05. The control is not masking an effect.

### Power: what this null rules out

The minimum detectable effect at 80% power (λ = 2.8016, n = 5,957,
one added regressor) is partial R² ≈ 0.001316 — the same MDE as
study 008, which had the same sample size. The observed 6.55e-06 is
~200x below the MDE, and the 0.005 threshold is 3.80x above it — the
study was powered to detect effects far smaller than the
preregistered minimum, and found nothing. The null rules out any
effect at or above partial R² ≈ 0.0013. It does not rule out a tiny
effect below that bound; but an effect that small is not a
transmission mechanism worth chasing.

### Naive lead-lag scan (descriptive)

Pearson correlations between the BAA10Y change and the VIX log
change at lags 0–5 (unlagged changes, descriptive only):

| Lag | n | r |
| --- | --- | --- |
| 0 (same day) | 5,958 | +0.1738 |
| 1 | 5,957 | −0.0188 |
| 2 | 5,956 | −0.0052 |
| 3 (tradeable, PIT-correct) | 5,955 | −0.0056 |
| 4 | 5,954 | −0.0169 |
| 5 | 5,953 | +0.0161 |

The same-day correlation is +0.1738 — credit spreads and equity
volatility move together **within** the day, as the mechanism would
suggest — but every lagged correlation is near zero. The pattern is
the lab's recurring one: information moves same-day and does not
carry over to the next day. (The tradeable alignment is lag 3 in scan
terms — lag 1 in regression terms plus the 2-trading-day publication
lag — and it is −0.0056, nothing.)

### Naive alignment (lookahead, descriptive)

Running the primary regression with unlagged (same-day) BAA10Y
changes — the version that peeks at data not yet available at the
close — also gives nothing: coefficient +0.000090/bp (the expected
sign, for once), p = 0.8276, partial R² = 1.30e-05, n = 5,957. It is
not significant and its partial R² is 100x below the MDE (0.001316).
**The publication lag is not what killed the effect**: even with
lookahead, the lagged transmission is absent.

### Reverse placebo (descriptive, not in the test family)

VIX → BAA10Y (lagged VIX log change predicting the next-day BAA10Y
change): coefficient −0.9936 bp per unit log change, p = 0.3481,
partial R² = 0.000279, n = 5,957. Not significant. A +10% VIX day
predicts a −0.10bp narrowing the next day — small, and the interval
covers zero. Unlike study 008, where the reverse placebo was
nominally significant (p = 0.0004, partial R² = 0.0087), here even
the reverse direction is a null. Descriptive only; it enters no
verdict.

### Sub-period stability (descriptive)

| Sub-period | n | Coefficient (per bp) | SE | Partial R² |
| --- | --- | --- | --- | --- |
| 2003–2007 | 1,245 | +0.000814 | 0.000804 | 0.000979 |
| 2008–2012 | 1,248 | −0.000236 | 0.000673 | 0.000180 |
| 2013–2017 | 1,248 | −0.000123 | 0.001228 | 1.15e-05 |
| 2018–2022 | 1,247 | +0.000329 | 0.001177 | 0.000181 |
| 2023–2026 | 965 | −0.001249 | 0.000757 | 0.001958 |

No stable effect. The coefficient flips sign across sub-periods
(positive in 2003–2007 and 2018–2022, negative in the other three),
and no sub-period's partial R² comes within 2.5x of the 0.005
threshold. The 2023–2026 partial R² (0.001958) is the largest of the
five — the only sub-period value above the full-sample MDE (0.001316)
— but it is still below the 0.005 threshold and wrong-signed. There is
no regime in which the preregistered effect appears.

### Walk-forward out-of-sample

40 folds, 0 skipped, 4,957 test rows. All-folds OOS incremental R²
= −0.000885 (baseline MSE 0.0059771, augmented MSE 0.0059824);
**holdout (7 folds, 716 rows): OOS incremental R² = −0.000019**
(baseline MSE 0.0071038, augmented MSE 0.0071040 — a 1.3e-07 MSE
difference, noise). Per-fold incremental R² values hover within
±0.003 of zero with no pattern, except fold 5 (2009-01-13 →
2009-07-14, the crisis fold) at −0.03694 — the same fold that was
the outlier in study 008 (−0.03895). Adding the BAA10Y predictor
makes out-of-sample forecasts slightly worse, in full and on the
holdout.

### Informational cost assessment (not a verdict criterion)

The gross sign-rule edge on the 716 holdout OOS augmented forecasts
is **+0.452% per day**, block-bootstrap 95% CI [−0.108%, +1.035%],
bootstrap p = 0.1284, sign accuracy 52.7%. Unlike study 009, where
the same assessment was nominally significant (p = 0.0375), here the
interval includes zero and the bootstrap p is 0.13 — the one number
that looked positive in study 009 does not even do that here. And the
same caveats apply regardless:

1. It is **gross with zero costs applied**, on an index that is not
   tradable. There is no instrument that pays the VIX log change, so
   the "edge" has no P&L meaning; it is an upper bound on a tradable
   edge that does not exist.
2. It contradicts the negative holdout OOS R². The sign rule is
   direction accuracy without magnitude accuracy: the augmented
   model's forecasts get the sign right slightly more often than
   chance (52.7%) while its squared-error forecasts are worse than
   the baseline. A model that is directionally lucky and
   magnitude-wrong is not a transmission mechanism.
3. It is **not in the verdict** — the preregistration fixed the
   three-criterion verdict before any result was seen, and the
   informational assessment carries no verdict weight. The same
   tension (positive gross edge, negative OOS R²) appeared in
   studies 003 and 009 and was treated the same way.

The informational assessment is reported because the preregistration
said it would be reported — not because it changes anything.

## Verdict

| Criterion | Threshold | Observed | Pass |
| --- | --- | --- | --- |
| Holm-adjusted primary p | < 0.05 | 0.8896 | No |
| Primary partial R² | ≥ 0.005 | 6.55e-06 | No |
| Holdout OOS incremental R² | > 0 | −0.000019 | No |

**H0015 v1 REJECTED** — 0 of 3 criteria pass. The state transition
was recorded with the trial numbers as the reason; the ledger is
anchored (`trials.jsonl.anchor`, 1 record, latest hash
`f9798275…`).

The rejection is not a borderline call: the primary p is 0.89, the
effect size is 763x below the minimum, the out-of-sample evaluation
is negative, the lookahead version is also null, and no sub-period
shows the effect. The mechanism — credit stress today lifting equity
volatility tomorrow — does not survive contact with 23 years of daily
data. Same-day co-movement (+0.1738) is real, but it is not
transmission: the information is in the price the same day and does
not carry over.

## Limitations

- **Daily frequency.** The transmission, if it exists at intraday
  horizons, is invisible here. The same-day correlation (+0.1738)
  hints that whatever co-movement exists is fast; daily data cannot
  say which side moves first within the day.
- **One control.** Only the SPX log return was controlled for.
  Other common factors (rates level changes, credit conditions,
  rates volatility) were not in the model. The no-factor upper bound
  is also null, which limits how much a missing control could be
  hiding, but it does not eliminate the possibility.
- **The 2023–2026 sub-period partial R² (0.001958) is the largest in
  the trial** — the only sub-period value above the full-sample MDE
  (0.001316). It is below the 0.005 threshold, not significant (no
  p-value is reported for sub-periods), and wrong-signed. It is not
  a finding; it is a reminder that the most recent regime is the
  closest thing to signal in the study, and it is still noise in the
  wrong direction.
- **The informational gross edge (+0.452%/day, p = 0.1284) is a
  descriptive statistic on an untradable index.** See the
  cost-assessment section for why it carries no weight.
- **The 2-trading-day BAA10Y lag is assumed constant across
  2003–2026** (verified only at fetch time). If the historical
  posting lag differed, the predictor alignment is wrong for those
  periods — but the naive unlagged alignment is also null, so a
  different lag assumption would not rescue the effect.

## Reproducibility

```bash
.venv/bin/python research/credit-spread-vix-010/preregister.py   # idempotent after registration
.venv/bin/python research/credit-spread-vix-010/fetch_data.py    # re-fetches; manifest SHA changes with fetch time
.venv/bin/python research/credit-spread-vix-010/run_trial.py     # trial T0018 (already recorded; re-running creates T0019)
```

The trial binds the preregistered spec fingerprint
(`eb8b2195…`), the manifest SHA-256 (`8802891b…`), and the code
revision (`7ae59d7f…`). Re-running the trial script records a new
trial against the current HEAD; it does not overwrite T0018.

## Scaffold feedback (third real use)

Study 008 recorded seven gaps from the 6c scaffold's first real use,
and study 009 found no new gaps. This study hit **no new gaps
either**. Every hand-adaptation the study needed was a repeat of a
known item:

- The generated `run_trial.py` wired only the primary test and a
  two-criterion verdict, with walk-forward and the cost gate as
  `NotImplementedError` stubs — 008's item 1. Same replacement, same
  full pipeline.
- `preregister.py` was not idempotent — 008's item 4. Same fix
  (re-running after registration leaves the registration untouched).
- The scaffold generated a 2-instrument universe; the SPX control leg
  was added by hand — 008's item 6.
- The draft's predictor transform (log return of a spread) and target
  wording ("VIX return") needed the researcher's correction in the
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
files contain no real-ID placeholder specs — only the real H0015
appears (the H9002/H9003/H9004 placeholders live only in the 6c
validation, not in generation).

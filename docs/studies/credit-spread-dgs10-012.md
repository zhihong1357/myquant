# Credit-spread changes lead the 10-year Treasury yield (study 012)

Twelfth empirical study in myquant Stage 3, and the fifth real use
of the Stage 6c scaffold. Research question: does the latest
available BAA10Y credit-spread change predict the next-day DGS10
(10-year Treasury yield) change, beyond DGS10's own history and the
SPX common-factor control? This is the planner's rank-1 candidate
pair after study 011 consumed BAA10Y→VXN (6a, total score 1.00,
adjacent supported edge E0026).

**Verdict: H0017 v2 REJECTED** (trial T0020). The latest available
BAA10Y change does not predict the next-day DGS10 change: the
primary coefficient is negative (the preregistered direction), but
p = 0.1819, partial R² = 0.000576 — 8.7x below the preregistered
minimum effect size and 2.3x below the minimum detectable effect.
The holdout out-of-sample incremental R² is negative (−0.004563).
Zero of three preregistered acceptance criteria pass.

All numbers in this report are quoted from the trial ledger record
`6b87286c14dd70b572665cda0e1dac85b2888f6d3fb9b70d3bd2c290c2b7ad13`
(recorded 2026-11-19T15:41:10Z, code revision
`dc877d10475f95f810ab9cf96880d477adf5dad6`), the fetch manifest
(SHA-256
`c28850b71fd5e6f916c93bdd410eec4a34d77ad744e63a44ec97c2f22875c44d`),
and the panel summary. Nothing here is hand-transcribed from a
screen; the ledger is the source.

## The mechanical confound (read this first)

BAA10Y is defined as the BAA corporate yield minus the 10-year
Treasury yield: BAA10Y = BAA − DGS10. The predictor is therefore

    ΔBAA10Y(t−2) = ΔBAA(t−2) − ΔDGS10(t−2),

so the predictor **contains the target's own lag-2 change, with a
minus sign**. If DGS10 changes are autocorrelated, the predictor
could "predict" the target purely mechanically — through the
target's own past, not through credit conditions. Worse, the
mechanical sign coincides with the economic sign: with positive
DGS10 autocorrelation, the −ΔDGS10 component pushes the coefficient
negative, exactly as the flight-to-safety hypothesis predicts
(see Design). An unguarded test could not distinguish a mechanical
artefact from real transmission. This is the same class of caveat
as the SUPPORTED cross-section edge E0026 (BAA10Y on DGS10, study
005), whose slope is partly mechanical by the same construction.

The design blocks the channel with a **lag-2 guard**: the baseline
model controls for the target's own lag-2 change ΔDGS10(t−2) in
addition to its lag-1 change and the SPX control. The guard is
PIT-clean — DGS10 posts the next business day (study 007, N=1), so
the change ending at t−2 is available at the decision close. With
the guard in the model, the augmented predictor's incremental
information comes (up to the guard's own coefficient) only from the
ΔBAA(t−2) component. The guard is a mechanical guard, not a factor
control: it is retained in the no-factor upper bound ("no-factor"
means no SPX, not no guard).

The guard is not free: it costs one degree of freedom and, on the
10 frame rows (0.17%) where the predictor's and the guard's value
dates differ (each series is shifted on its own dates, so the two
can disagree after a date where exactly one leg is missing), the
guard does not perfectly cancel the mechanical component. The
residual contamination is negligible — 10 rows out of 5,958, and
the mechanical channel itself is small (see Decomposition) — but
it is recorded rather than assumed away.

Whatever the verdict, the result must not be read as clean
transmission evidence without this caveat. It is not: the verdict
is a rejection, and the rejection is of the guarded test — the
version that already removes the mechanical channel.

## Design

H0017 v1 was preregistered before any result was examined
(registration hash
`158b5216af221fd939d4aef601d7cbbf06f9708c489d83c8f8b3e33adf6b50db`,
spec fingerprint
`6422913462650bd997d4a221b9cd1c9f529a1c0993ee18bdaf224f8cfdc2cfca`),
and amended to v2 before any trial ran (registration hash
`99940ae3a80bf01cf30cd5e586f73cd54ef07d6c3d62aff583be35fafff86e9e`,
spec fingerprint
`dd5e04a370da48c0185eedb78990dea2164d44f1097db646d5e9764a1e9eed2a`).
The trial binds v2. The full design is in
`research/credit-spread-dgs10-012/design.json`; the registered
specs are in
`research/credit-spread-dgs10-012/hypotheses/registrations/H0017/v1.json`
and `v2.json`.

- **Predictor**: the daily BAA10Y level change in basis points (not
  the log return the planner draft names — a spread quoted in
  percentage points has no meaningful log return; the same correction
  studies 008/009/010/011 made). **Lagged 2 trading days by
  availability** (see the publication-lag section below).
- **Target**: the DGS10 daily **level change in basis points**, not
  the log change. DGS10 is a yield quoted in percentage points; a
  log change of a yield has no economic meaning as a return, and the
  draft's "DGS10 return" is loose wording. This is a new correction
  relative to study 011, where the target (VXN) was an index level
  and the log change was correct.
- **Control**: the SPX log return (SPX[t], unlagged — Yahoo posts
  the close the same evening, so the day-t SPX change is knowable at
  the decision close; study 003's factor-alignment precedent), plus
  the target's own lag-2 change as the mechanical guard (see above).
  Lagged VIX is deliberately not the control: this study is about
  the rates leg, and the SPX control keeps the design comparable
  with studies 010/011. TYVIX would truncate the sample at 2020.
- **Expected direction: negative.** Credit-spread widening reflects
  credit stress; under stress, money flees to safety, buying
  Treasuries, pushing Treasury prices up and yields down — so a
  lagged ΔBAA10Y rise should accompany a next-day DGS10 fall. The
  mechanical sign is also negative (see the confound section), which
  is why the lag-2 guard is indispensable. The draft's "positive,
  out-of-sample component" refers to positive incremental
  explanatory power (incremental R² > 0), not to a positive
  coefficient — the two are stated separately in the preregistration.
- **Model**: the base model predicts the next-day DGS10 change from
  DGS10's own lag-1 change, its lag-2 change (the guard), and the
  SPX log return; the augmented model adds the lag-2 BAA10Y change.
  HAC standard errors (Newey-West, max lag 5). The test family has
  one test (the primary), Holm-adjusted.
- **Verdict criteria (study 003's three)**: Holm-adjusted primary p
  below 0.05; primary partial R² at least 0.005; holdout
  out-of-sample incremental R² above 0. There is no cost gate
  criterion in the verdict — see the cost-gate section.
- **Windows** (21:00 UTC daily closes, one-day purge gaps):
  train [2003-01-02, 2020-01-01), validation [2020-01-02, 2024-01-01),
  holdout [2024-01-02, 2026-11-19). Minimum observations:
  1000 / 500 / 300. Walk-forward: initial train 1000 rows, test
  window 126, embargo 1 day. Bootstrap: block length 10, 2000
  resamples, seed 42.
- **Sub-periods** (study 003's 5-year blocks, extended to the full
  window — the same split studies 008/010/011 used): 2003–2007,
  2008–2012, 2013–2017, 2018–2022, 2023–2026.

### The v1 → v2 amendment (pre-trial)

V1 assumed a daily FRED BAA series for the decomposition leg (a
supplementary regression on ΔBAA(t−2), the non-mechanical component
of the predictor). The fetch showed FRED publishes BAA **monthly
only** (286 rows, 2003-01 to 2026-10, verified from the raw CSV
payload) — no daily BAA series exists to fetch. The first fetch's
panel collapsed to 183 return rows before the error was caught; the
cache was wiped and the fetch re-run clean. V2 drops the BAA fetch
leg from the universe and derives the daily BAA change from the
identity ΔBAA = ΔBAA10Y + ΔDGS10. Given the guard, the lagged-ΔBAA
supplementary regression is a restatement of the primary test, not
independent evidence (see Decomposition). Nothing else changed:
predictor, target, guard, control, verdict criteria, windows and
test family are identical between v1 and v2. The amendment was
registered before any trial ran, and the amendment reason is
recorded in the registry, the design note, and the README. Study
003's H0004 v1+v2 is the lab precedent for a pre-trial amendment.

### Publication lag (the core PIT issue)

BAA10Y posts about a day later than other FRED series (6b evidence
probe 2026-11-18T21:45Z: BAA10Y latest 2026-11-16, the reference
series already 2026-11-17). FRED daily values generally post on the
next business day (study 007, N=1), so BAA10Y's effective
availability lag is **2 trading days**: at the close of day t, the
latest available BAA10Y value is dated t-2, and the latest
available change is the change ending t-2. The predictor for the
DGS10 change over t+1 is therefore the BAA10Y change ending at
t-2 — a lag-2 predictor by value date, deliberately. The SPX
control carries no lag: Yahoo posts the close the same evening, so
SPX[t] is knowable at the decision close. Both lags are applied in
the trial's panel construction via the study-007 lagged-changes
module (`myquant.studies.publication_lag.lagged_changes_on_index`);
the PIT store itself records `available_at` equal to the event time
(adapter limitation — see the design's known confounders). The
fetch script re-verifies the posting pattern behaviorally and
records the observed last dates in the manifest.

The trial's descriptive naive alignment (unlagged changes, the
lookahead version) quantifies what ignoring the publication lag
would buy; it is not part of the test family.

One convention to note: the own-history baseline uses the DGS10
change over day t as a predictor for the change over t+1. Under the
study's source-based PIT convention (FRED posts day-t values the
next business day), the day-t DGS10 value is published the next
morning, so the baseline uses information the FRED source had not
yet published at the decision close. The same convention was used
in studies 003, 009, 010 and 011. It strengthens the baseline
against the source, so the incremental test is conservative: the
source must beat a baseline that already knows the target's most
recent change. The lag-2 guard, by contrast, is PIT-clean — the
change ending at t-2 is available at the decision close under the
same convention. The two must not be confused: the lag-1 baseline
term is a conservative concession, the lag-2 guard is clean.

### Cost gate: informational only

DGS10 is a yield and is not directly tradable. A tradable proxy
would be a Treasury future (e.g. ZN) or a Treasury ETF — and the
free price series do exist: Yahoo ZN=F returned 24 closes in the
last month (last close 105.671875) and IEF returns data as well
(both verified 2026-11-19 via the query2 chart endpoint). The
informational treatment therefore does **not** rest on "no free
series exists". It rests on the modelling gap: converting a
yield-change signal into a futures or ETF position requires a
DV01/duration conversion and futures roll handling that this study
does not model, so no clean cost measurement is available.
Following study 003's precedent for a non-tradable target, the
cost gate is **informational, not a verdict criterion**: the trial
reports the gross sign-rule edge in basis points per day on holdout
out-of-sample augmented forecasts (1x, always invested while
positioned, no costs applied) with a block-bootstrap CI, under the
metrics key `cost_gate_informational`. The verdict takes only the
three criteria above. This was fixed in the preregistration, before
any result was seen.

## Data

Universe:

- `credit:baa-10y-spread` (FRED BAA10Y)
- `rates:us-10y-yield` (FRED DGS10)
- `index:sp500` (Yahoo ^GSPC, control leg)

Sources: `fred`, `yahoo-finance`. Calendar: `us-equity`. Fetched
2026-11-19T15:39:41Z from the public fredgraph CSV endpoints (no API
key, no custom User-Agent — study 003's lesson: requests with a
custom User-Agent hang) and the Yahoo query2 chart endpoint
(`User-Agent: Mozilla/5.0`, with the longName and positivity
fail-fast checks from studies 003/008).

| Series | Values | Missing | First | Last |
| --- | --- | --- | --- | --- |
| BAA10Y | 5,968 | 261 | 2003-01-02 | 2026-11-17 |
| DGS10 | 5,973 | 256 | 2003-01-02 | 2026-11-17 |
| SPX (^GSPC) | 6,009 | 0 | 2003-01-02 | 2026-11-18 |

The per-instrument counts match study 010's manifest exactly for
the BAA10Y and SPX legs (same series, same window). The full-series
BAA10Y payload SHA-256 matches studies 008/010/011 (`d803ed7c…`),
so the shared data are the same FRED vintage. The planner template
estimated 5,967 joint rows; the panel came in at 5,960 return rows.

One fetch detail: the fetch ran while the US market was open
(~15:35 UTC / 10:35 EST, Thursday 2026-11-19), and Yahoo returned a
partial ^GSPC bar for the current day. Its 21:00 UTC close is after
the fetch time, so the Observation contract refused it
(`ingested_at` cannot precede `available_at`). The fetch drops bars
whose 21:00 UTC close is after `fetched_at` before building
observations — a daily bar is only an observation once its close has
happened — and counts them in the manifest as
`dropped_partial_bars` (= 1 for SPX). The raw payload is still
stored whole.

Panel (diff-then-join: changes computed per series on its own dates
first, then joined — the study-003 method): **5,961 close rows,
5,960 return rows, 2003-01-03 → 2026-11-17, 58 dropped close rows,
59 dropped return rows**. The regression frame drops the first two
rows (no lag-2 BAA10Y change exists there): 5,958 rows,
2003-01-07 → 2026-11-17. The primary test uses 5,957 rows (one row
is lost to the target's one-day-ahead shift) — tied with studies
008 and 010 for the lab's largest lead-lag sample.

Quality issues: none. Raw payloads live only in the local cache at
`data/cache/credit-spread-dgs10-012/` (gitignored) and are never
committed.

### Publication-lag verification

The fetch re-checked the posting lag behaviorally (same procedure
as studies 008/009/010/011). At fetch time (2026-11-19T15:39:41Z,
i.e. 2026-11-19 10:39 US Eastern), BAA10Y and DGS10 both ended
2026-11-17, with 2026-11-18 the most recent trading day. Combined
with the 6b probe (2026-11-18T21:45Z, 45 minutes after the US close:
BAA10Y one trading day behind the reference series), the picture is
the same as studies 008/009/010/011's: BAA10Y posts in the post-close
evening window (US Eastern 16:45–19:25), so at any close the latest
available value is two trading days old, and the effective
2-trading-day lag stands. The lag-check details are in the manifest
and the panel summary.

## Results

All results are from trial T0020 (ledger record
`6b87286c…`, recorded 2026-11-19T15:41:10Z). The test family has one
test — the primary — so the Holm adjustment is the identity on it.

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily BAA10Y→DGS10, SPX + guard (primary) | 5,957 | −0.049085 | 0.036773 | −1.33 | 0.1819 | 0.1819 | 0.000576 | 0.000574 |
| no-factor control (guard retained) | 5,957 | −0.044306 | 0.037240 | −1.19 | 0.2342 | — | 0.000469 | 0.000469 |
| naive (unlagged) alignment | 5,957 | −0.059099 | 0.039886 | −1.48 | 0.1384 | — | 0.000823 | 0.000821 |
| reverse placebo (DGS10→BAA10Y) | 5,957 | +0.034949 | 0.014951 | +2.34 | 0.01941 | — | 0.003631 | 0.003539 |
| ΔBAA decomposition (identity-derived) | 5,957 | −0.049085 | 0.036773 | −1.33 | 0.1819 | — | 0.000576 | 0.000574 |

### Primary test: lagged BAA10Y change → next-day DGS10 change

| Statistic | Value |
| --- | --- |
| Observations | 5,957 |
| Coefficient (per bp) | −0.049085 |
| HAC standard error (lag 5) | 0.036773 |
| t-statistic | −1.335 |
| p-value | 0.1819 |
| Holm-adjusted p-value | 0.1819 |
| Partial R² | 0.000576 |
| Incremental R² | 0.000574 |
| Base R² → augmented R² | 0.002356 → 0.002930 |

The coefficient has the **preregistered sign** (negative) — the
first of the five BAA10Y lead-lag studies whose primary coefficient
points the expected way — but it is 1.33 standard errors from zero
and the partial R² is 8.7x below the preregistered minimum effect
size of 0.005. In economic terms: a one-standard-deviation BAA10Y
move (3.01bp) predicts a −0.148bp ± 0.111bp next-day DGS10 change —
nothing, on a target whose daily change standard deviation is
5.68bp.

The no-factor upper bound (guard retained, no SPX control) is the
same null: coefficient −0.044306/bp, p = 0.2342, partial R² =
0.000469. The SPX control is not masking an effect.

### Power: what this null rules out

The minimum detectable effect at 80% power (λ = 2.8016, n = 5,957,
one added regressor) is partial R² ≈ 0.001316 — the same MDE as
studies 008/010, which had the same sample size. The observed
0.000576 is ~2.3x below the MDE, and the 0.005 threshold is 3.80x
above it. This is the largest primary partial R² of the five
BAA10Y lead-lag studies (008: 2.19e-05; 009: 6.10e-05; 010:
6.55e-06; 011: 2.29e-05) — and it is still below the MDE and 8.7x
below the threshold. The null rules out any effect at or above
partial R² ≈ 0.0013. It does not rule out a tiny effect below that
bound; but an effect that small is not a transmission mechanism
worth chasing.

### Decomposition (descriptive)

Three quantities, all descriptive and outside the test family:

- **Predictor–guard correlation: −0.3869** (n = 5,958). The
  mechanical component is substantial, as constructed: the predictor
  contains minus the guard. This is the number that justifies the
  guard — without it, more than a third of the predictor's variation
  would be the target's own past.
- **DGS10 change autocorrelations: lag-1 −0.0118, lag-2 −0.0503.**
  The mechanical channel runs through the target's autocorrelation,
  and the autocorrelation is near zero. So the mechanical channel
  was small to begin with — and the guard blocks it anyway. The
  guard is cheap insurance that turned out to be mostly redundant,
  which is the right way round: a guard that is needed and absent
  is a false positive; a guard that is present and unneeded costs
  one degree of freedom.
- **The lagged-ΔBAA supplementary regression is numerically
  identical to the primary test** (coefficient −0.049085/bp,
  p = 0.1819, partial R² = 0.000576, all 9 numbers identical). This
  is the identity at work, not a coincidence: the derived predictor
  ΔBAA = ΔBAA10Y + ΔDGS10(t−2) differs from the primary predictor
  only by the guard, which is already a regressor, so replacing the
  predictor leaves the fitted values and the predictor's coefficient
  unchanged (the guard's coefficient absorbs the difference). The
  regression confirms the identity holds in the data, but — exactly
  as the v2 design states — it provides **no independent evidence**.
  It is a consistency check, reported as one.

### Naive lead-lag scan (descriptive)

Pearson correlations between the BAA10Y change and the DGS10 change
at lags 0–5 (unlagged changes, descriptive only):

| Lag | n | r |
| --- | --- | --- |
| 0 (same day) | 5,958 | −0.3863 |
| 1 | 5,957 | −0.0165 |
| 2 | 5,956 | −0.0055 |
| 3 (tradeable, PIT-correct) | 5,955 | −0.0243 |
| 4 | 5,954 | +0.0219 |
| 5 | 5,953 | −0.0401 |

The same-day correlation is −0.3863 — but unlike studies 008–011,
where the same-day correlation was the (non-mechanical) co-movement
of two distinct series, here it is **dominated by construction**:
ΔDGS10 is literally a component of ΔBAA10Y with a minus sign, so
the two changes are mechanically negatively correlated same-day.
(It matches the predictor–guard correlation of −0.3869, as it must
— they are the same quantity up to the row set.) The informative
numbers are the lagged correlations, and every one of them is near
zero. (The tradeable alignment is lag 3 in scan terms — lag 1 in
regression terms plus the 2-trading-day publication lag — and it is
−0.0243, nothing.)

### Naive alignment (lookahead, descriptive)

Running the primary regression with unlagged (same-day) BAA10Y
changes — the version that peeks at data not yet available at the
close — also gives nothing: coefficient −0.059099/bp (expected
sign), p = 0.1384, partial R² = 0.000823, n = 5,957. It is not
significant and its partial R² is below the MDE (0.001316).
**The publication lag is not what killed the effect**: even with
lookahead, the lagged transmission is absent.

### Reverse placebo (descriptive, not in the test family)

DGS10 → BAA10Y (lagged DGS10 change predicting the next-day BAA10Y
change): coefficient +0.034949 bp per bp, p = 0.01941, partial R² =
0.003631, n = 5,957. **Nominally significant at the 0.05 level —
but it must not be read as reverse transmission**, for three
reasons. First, it is descriptive only: it enters no test family
and carries no Holm adjustment, so a single p = 0.019 among the
study's many descriptive statistics is weak evidence. Second, its
partial R² (0.003631) is below the 0.005 threshold the lab uses for
a meaningful effect. Third, and decisively, **the reverse test is
itself mechanically confounded**: its target ΔBAA10Y(t+1) contains
−ΔDGS10(t+1) by construction, so the regression of the target on
ΔDGS10(t) picks up the lag-1 autocorrelation of DGS10 changes
through the minus sign — and that autocorrelation is −0.0118
(slightly negative), which gives the mechanical channel the same
positive sign as the observed coefficient. The nominal significance
is consistent with the mechanical channel, not with transmission.
Descriptive only; it enters no verdict.

### Sub-period stability (descriptive)

| Sub-period | n | Coefficient (per bp) | SE | Partial R² |
| --- | --- | --- | --- | --- |
| 2003–2007 | 1,245 | −0.113651 | 0.083474 | 0.001622 |
| 2008–2012 | 1,248 | −0.119482 | 0.060633 | 0.003898 |
| 2013–2017 | 1,248 | −0.045652 | 0.068546 | 0.000405 |
| 2018–2022 | 1,247 | −0.026571 | 0.072462 | 0.000264 |
| 2023–2026 | 965 | +0.141415 | 0.079781 | 0.003493 |

No stable effect. The coefficient is negative in the first four
sub-periods and positive in 2023–2026, and no sub-period's partial
R² comes within 1.3x of the 0.005 threshold. The 2008–2012 partial
R² (0.003898) is the largest of the five — still below the
threshold, and below the sub-period MDE at n ≈ 1,248 (≈ 0.00625).
The 2023–2026 sub-period has the second-largest partial R²
(0.003493) with the opposite sign. There is no regime in which the
preregistered effect appears at a meaningful size.

### Walk-forward out-of-sample

40 folds, 0 skipped, 4,957 test rows. All-folds OOS incremental R²
= −0.000617 (baseline MSE 33.2472, augmented MSE 33.2677);
**holdout (7 folds, 716 rows): OOS incremental R² = −0.004563**
(baseline MSE 26.4018, augmented MSE 26.5222). Adding the BAA10Y
predictor makes out-of-sample forecasts worse in full and worse on
the holdout. Per-fold incremental R² values hover within ±0.01 of
zero with no pattern; fold 5 (2009-01-13 → 2009-07-14, the crisis
fold) is −0.006655 — **not** the outlier it was in studies 008
(−0.03895), 010 (−0.03694) and 011 (−0.03786). The crisis fold's
extreme negative values in those studies were a property of their
volatility-index targets, not of the walk-forward scheme; with a
rates target the fold is unremarkable.

### Informational cost assessment (not a verdict criterion)

The gross sign-rule edge on the 716 holdout OOS augmented forecasts
is **−0.165bp per day**, block-bootstrap 95% CI [−0.559bp,
+0.229bp], bootstrap p = 0.4188, sign accuracy 47.3%. The sign rule
loses money on a gross basis — the augmented model's holdout
forecasts get the direction right less often than chance — which is
consistent with the negative holdout OOS R². Unlike studies 009,
010 and 011, where the gross edge was positive and the tension
between the edge and the OOS R² had to be explained, here there is
no tension to explain: both the squared-error and the sign-rule
assessments point the same way. The same caveats apply regardless:

1. It is **gross with zero costs applied**, on a yield that is not
   directly tradable. A ZN or IEF position would need a DV01/duration
   conversion and roll handling that this study does not model, so
   the "edge" has no P&L meaning; it is an upper bound on a tradable
   edge that is not measured here.
2. It is **not in the verdict** — the preregistration fixed the
   three-criterion verdict before any result was seen, and the
   informational assessment carries no verdict weight.

The informational assessment is reported because the preregistration
said it would be reported — not because it changes anything.

## Verdict

| Criterion | Threshold | Observed | Pass |
| --- | --- | --- | --- |
| Holm-adjusted primary p | < 0.05 | 0.1819 | No |
| Primary partial R² | ≥ 0.005 | 0.000576 | No |
| Holdout OOS incremental R² | > 0 | −0.004563 | No |

**H0017 v2 REJECTED** — 0 of 3 criteria pass. The state transition
was recorded with the trial numbers as the reason; the ledger is
anchored (`trials.jsonl.anchor`, 1 record, latest hash
`6b87286c…`).

The rejection is not a borderline call: the primary p is 0.18, the
effect size is 8.7x below the minimum, the lookahead version is also
null, the holdout out-of-sample assessment is negative, and no
sub-period shows the effect at a meaningful size. The mechanism —
credit stress today pushing Treasury yields down tomorrow — does not
survive contact with 23 years of daily data. The one number that
points the expected way (the primary coefficient's sign) is 1.33
standard errors from zero and carries no weight against the three
failed criteria. Same-day co-movement here is mechanical (−0.3863
by construction), not evidence of anything; the lagged
correlations, which would be evidence, are all near zero.

## Limitations

- **Daily frequency.** The transmission, if it exists at intraday
  horizons, is invisible here. Daily data cannot say which side
  moves first within the day.
- **One control.** Only the SPX log return was controlled for (plus
  the target's own history and the guard). Other common factors
  (rates volatility, the rates level itself, credit conditions) were
  not in the model. The no-factor upper bound is also null, which
  limits how much a missing control could be hiding, but it does not
  eliminate the possibility.
- **The reverse placebo is nominally significant (p = 0.0194) and
  mechanically confounded.** See the reverse-placebo section for why
  it carries no weight — but the fact that the mechanical channel
  can produce a nominally significant descriptive statistic is itself
  a reminder that this pair's construction needs the guard.
- **The informational gross edge (−0.165bp/day, p = 0.4188) is a
  descriptive statistic on a non-tradable yield.** See the
  cost-assessment section for why it carries no weight.
- **The 2-trading-day BAA10Y lag is assumed constant across
  2003–2026** (verified only at fetch time). If the historical
  posting lag differed, the predictor alignment is wrong for those
  periods — but the naive unlagged alignment is also null, so a
  different lag assumption would not rescue the effect.
- **The guard misaligns on 10 of 5,958 frame rows (0.17%)**, where
  the predictor's and the guard's value dates differ. The residual
  mechanical contamination is negligible, but it is a real
  imperfection of the own-date-shift construction.
- **The v2 decomposition is a restatement, not independent
  evidence.** The ΔBAA supplementary regression confirms the
  identity holds in the data; it cannot corroborate the primary
  test, because the two regressions are the same regression. The
  study's independent evidence is the guard itself, not the
  decomposition.
- **FRED BAA is monthly only.** The v1 design's plan to test the
  non-mechanical component directly against fetched daily BAA data
  was impossible; the derived series is exact by identity, but it is
  derived, not observed.

## Reproducibility

```bash
.venv/bin/python research/credit-spread-dgs10-012/preregister.py   # idempotent after registration
.venv/bin/python research/credit-spread-dgs10-012/fetch_data.py    # re-fetches; manifest SHA changes with fetch time
.venv/bin/python research/credit-spread-dgs10-012/run_trial.py     # trial T0020 (already recorded; re-running creates T0021)
```

The trial binds the preregistered v2 spec fingerprint
(`dd5e04a3…`), the manifest SHA-256 (`c28850b7…`), and the code
revision (`dc877d10…`). Re-running the trial script records a new
trial against the current HEAD; it does not overwrite T0020.

## Scaffold feedback (fifth real use)

Study 008 recorded seven gaps from the 6c scaffold's first real use,
and studies 009, 010 and 011 found no new gaps. This study hit **no
new gaps either**. Every hand-adaptation the study needed was a
repeat of a known item:

- The generated `run_trial.py` wired only the primary test and a
  two-criterion verdict, with walk-forward and the cost gate as
  `NotImplementedError` stubs — 008's item 1. Same replacement, same
  full pipeline.
- `preregister.py` was not idempotent — 008's item 4. Same fix
  (re-running after registration leaves the registration untouched).
- The scaffold generated a 2-instrument universe; the SPX control leg
  was added by hand — 008's item 6.
- The draft's predictor transform (log return of a spread) and target
  wording ("DGS10 return") needed the researcher's correction in the
  design — 008's items 5/7. This study's target correction (level
  change in bp, not log change) is a new instance of item 7's class:
  the scaffold passes draft text verbatim and cannot know that a
  yield has no meaningful log return.
- The generated `fetch_data.py` had no Yahoo fail-fast checks and a
  hard-coded content type — 008's item 3 — and no publication-lag
  check (the lag check is study-specific work the scaffold never
  claimed to do).

One fix from study 008 verified: the generated `run_trial.py` now
passes `BAR_SECONDS = None` (the 008 bug, `bar_seconds=86400`, would
have voided every Monday return). Confirmed in the generated file
before adaptation.

One placeholder-hygiene check from study 009 verified: the generated
files contain no real-ID placeholder specs — only the real H0017
appears (the H9002/H9003/H9004 placeholders live only in the 6c
validation, not in generation).

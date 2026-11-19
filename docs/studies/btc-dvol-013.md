# Lagged BTC returns lead BTC_DVOL changes (study 013)

Thirteenth empirical study in myquant Stage 3, and the sixth real
use of the Stage 6c scaffold. Research question: does the lagged
BTC daily log return predict the next-day BTC_DVOL log change,
beyond BTC_DVOL's own history and the ETH common-factor control?
This is the planner's rank-1 candidate pair after study 012
consumed BAA10Y→DGS10 (6a, total score 1.00, adjacent supported
edge E0030). It is the lab's first DVOL study — a new data source
(Deribit's BTC implied-volatility index) and the first study whose
panel is entirely crypto-native (24/7 calendar, no US trading days).

**Verdict: H0018 REJECTED** (trial T0021). The lagged BTC return
does not predict the next-day BTC_DVOL change: the primary
coefficient is positive (the **opposite** of the preregistered
leverage-effect direction), p = 0.2269, partial R² = 0.001195 —
4.2x below the preregistered minimum effect size and 3.2x below
the minimum detectable effect. One of three preregistered
acceptance criteria passes (the holdout out-of-sample incremental
R² is positive, +0.002538); the two decisive ones fail clearly.

All numbers in this report are quoted from the trial ledger record
`302631f465211abdf1804f48eb12cc17168755ad02fceb9cf1052f0e47954cf4`
(recorded 2026-11-19T17:20:11Z, code revision
`7ed075287f8b4df401e6fb63fd6db09e73c81d44`), the fetch manifest
(SHA-256
`92f1e247f3edd337af1ff8d6499b509805b72f9c37ae94dc3da0014635892689`),
and the panel summary. Nothing here is hand-transcribed from a
screen; the ledger is the source.

## The snapshot problem (read this first)

BTC_DVOL is a continuous index, and the OKX 1D bars open at 16:00
UTC. The Deribit DVOL endpoint's daily resolution timestamps its
points at 00:00 UTC — a daily DVOL value measured at midnight would
leave an 8-hour overlap between the predictor window (16:00–16:00
UTC) and the target window (00:00–00:00 UTC), so part of the
"next-day" DVOL change would already be known inside the predictor
bar. The study therefore fixes the daily DVOL value as the **16:00
UTC snapshot**: the close of the Deribit hourly DVOL row
timestamped 15:00 UTC. The DVOL observation at bar-open time 16:00
UTC on day D carries the snapshot value at 16:00 UTC on day D+1
(the bar-close value, matching the OKX candle convention:
event_time is the bar open, the close value is the price at the bar
close, available_at is the bar close). The predictor (BTC return
over the bar opening at t) and the target (DVOL change over the
bar opening at t+1) then share exactly the same window boundaries,
with no overlap and no gap.

The snapshot convention is a design choice, not a discovery: a
different snapshot time (e.g. 00:00 UTC) would give a different
panel and possibly different numbers. It was fixed in the
preregistration before any result was examined, and it is the only
convention this study's numbers speak to. The hourly DVOL series
is retained in the gitignored cache (`data/cache/btc-dvol-013/`),
so a different snapshot convention could be tested — but only
under a fresh preregistration, not as a post-hoc variation on this
one.

## Design

H0018 v1 was preregistered before any result was examined
(registration hash
`1754723c1cc84861ce85b3afa83c7d01f98cb957d9f8149b2d15e850cc293f3f`,
spec fingerprint
`463f8e79462335dbc872cb86b2e33b9972ad3b2407beeae0ef1479bd84c674c1`).
The full design is in `research/btc-dvol-013/design.json`; the
registered spec is in
`research/btc-dvol-013/hypotheses/registrations/H0018/v1.json`.

- **Predictor**: the BTC daily log return (OKX BTC-USDT-SWAP 1D
  candles, bars open 16:00 UTC), **lag-1** — the return over the
  bar opening at t, knowable at the 16:00 UTC decision close. There
  is no FRED-style publication lag: BTC prices and the DVOL index
  are both real-time, so the lag is one bar, not two trading days.
- **Target**: the BTC_DVOL daily **log change**. BTC_DVOL is an
  index level like VIX (studies 003/010/011), so the log change is
  the target — unlike study 012's DGS10 yield target, which took
  the level change in basis points. The planner draft's "BTC_DVOL
  return" wording is unambiguous here (a log change of an index
  level), and the preregistration states the definition explicitly.
- **Control**: the ETH log return (OKX ETH-USDT-SWAP, lag-0 — the
  return over the same bar as the predictor). ETH, not SPX: the
  panel is a 24/7 crypto calendar, and SPX has no weekend values,
  so an SPX control would force dropping ~28% of rows or violating
  the no-forward-fill rule. ETH is crypto-native, 24/7, same venue,
  and captures the crypto common factor (the BTC→ETH link is study
  001). SPX comparability with studies 010/011/012 is traded for
  sample completeness; the no-factor bound shows what the control
  absorbs.
- **Expected direction: negative.** The classical leverage effect:
  negative returns accompany rising volatility, so a lagged BTC
  fall should accompany a next-day DVOL rise. The mechanism text
  covers risk repricing and deleveraging, and notes the regression
  cannot identify which channel operates — it tests the numerical
  relationship, not the mechanism. The leverage effect also has an
  amplitude dimension (|return| → volatility), but the primary test
  is the signed return per the template; the amplitude dimension is
  a descriptive supplement (see below), not in the test family, and
  was not promoted after the fact. The draft's "positive,
  out-of-sample component" refers to positive incremental
  explanatory power (incremental R² > 0), not to a positive
  coefficient — the two are stated separately in the preregistration.
- **Model**: the base model predicts the next-day DVOL change from
  DVOL's own lag-1 change (the change over the bar opening at t —
  a real-time index value, knowable at the decision close, so no
  source-lag concession is needed) and the ETH log return; the
  augmented model adds the lagged BTC return. HAC standard errors
  (Newey-West, max lag 5). The test family has one test (the
  primary), Holm-adjusted.
- **Verdict criteria (study 003's three)**: Holm-adjusted primary p
  below 0.05; primary partial R² at least 0.005; holdout
  out-of-sample incremental R² above 0. There is no cost gate
  criterion in the verdict — see the cost-gate section.
- **Windows** (16:00 UTC daily closes, one-day purge gaps):
  train [2021-03-24, 2024-01-01), validation [2024-01-02, 2025-01-01),
  holdout [2025-01-02, 2026-11-20). Minimum observations:
  500 / 300 / 300. Walk-forward: initial train 1000 rows, test
  window 126, embargo 1 day. Bootstrap: block length 10, 2000
  resamples, seed 42.
- **Sub-periods** (yearly blocks, preregistered — the sample is too
  short for the 5-year blocks studies 008/010/011/012 used):
  2021, 2022, 2023, 2024, 2025–2026.

### The Deribit DVOL endpoint (verified before fetching)

The endpoint is `public/get_volatility_index_data`
(`currency=BTC`, `index_name=btc_vol`, `start_timestamp` /
`end_timestamp` in ms, `resolution` in seconds). It returns OHLC
rows `[timestamp_ms, open, high, low, close]` on the resolution
grid, with `data` and `continuation` keys. Behaviour verified
2026-11-19, before the preregistration:

- **Hourly resolution works** (resolution 3600): a 2-day window
  returned 49 rows (48 hours + 1 — endpoints inclusive, timestamps
  snapped to the hour grid).
- **1,000-point cap per call, truncating from the start**: a 60-day
  hourly window returned exactly 1,000 rows (the last 1,000 points
  of the requested window). The fetch therefore chunks in 40-day
  windows (at most 961 points) and refuses any chunk returning
  exactly 1,000 points (the truncation signal). No chunk hit the
  cap. Note the adapter's `fetch_volatility_index` chunks in
  two-year windows — fine for daily resolution, wrong for hourly
  (it would silently truncate) — so the fetch script does its own
  40-day chunking and the adapter's internal chunking is a no-op
  for these windows.
- **Daily resolution** (86400) timestamps points at 00:00 UTC —
  the reason for the 16:00 UTC snapshot convention (see above).
- **No publication lag**: DVOL is a real-time computed index; the
  hourly rows are available as each hour closes. No study-007-style
  lag concession is needed or applied.

### Cost gate: informational only

BTC_DVOL is an index and is not directly tradable. The tradable
proxy would be a Deribit BTC options straddle, but no clean free
cost series exists for it — verified 2026-11-19, before the
preregistration:

- Deribit's `public/get_tradingview_chart_data` returns status
  `no_data`, 0 ticks, for BTC option instruments — verified on
  three instruments (near-term ATM call BTC-20NOV26-62500-C, weekly
  near-money call BTC-4DEC26-62000-C over 30-day and 6-month
  windows, monthly near-money call BTC-25DEC26-62000-C over 7-day
  daily and hourly windows). The instruments do trade (verified
  via `public/get_last_trades_by_instrument` — 5 recent trades for
  BTC-25DEC26-62000-C), and the same endpoint returns data for
  BTC-PERPETUAL (31 ticks over 30 days), so the no_data result is
  specific to option chart history, not a broken endpoint.
- `get_instruments` with `expired=true` returns only the most
  recent batch (48 contracts, all expiring 2026-11-19) —
  confirming study 004's finding. No historical option universe
  can be reconstructed from the public API.

So the cost gate is informational (study 003's precedent for a
non-tradable target), and the informational treatment rests on
**missing data** — the opposite of study 012, where Yahoo ZN=F had
data and the informational treatment rested on a modelling gap
(DV01/duration conversion and roll handling). The trial reports the
gross sign-rule edge on holdout OOS augmented forecasts in
log-change units per day, with a block-bootstrap CI. It carries no
verdict weight.

## Data

- **BTC** (OKX BTC-USDT-SWAP 1D, `history-candles`, `after`
  pagination): 2,089 confirmed bars, 2021-03-01T16:00Z to
  2026-11-18T16:00Z, **0 missing**, 21 pages.
- **ETH** (OKX ETH-USDT-SWAP 1D, same): 2,089 confirmed bars, same
  window, **0 missing**, 21 pages.
- **BTC_DVOL** (Deribit hourly, resolution 3600, 40-day chunks):
  49,601 hourly points, 2021-03-24T00:00Z to 2026-11-19T16:00Z,
  52 chunks, no chunk at the 1,000-point cap. **2,067 daily 16:00
  UTC snapshots** (close of the hourly row timestamped 15:00 UTC),
  2021-03-24T16:00Z to 2026-11-19T16:00Z, **0 missing snapshots**.
  (The raw pages contain one further hourly row — timestamped
  17:00 UTC on the fetch date, a forming row whose close was not
  knowable at the 17:16 UTC fetch time. The adapter's `[start,
  end)` filter correctly excludes it; the count of 49,601 is the
  post-filter count.)
- **Panel**: synchronized close panel 2,067 rows (2021-03-23 to
  2026-11-18; 22 dropped close rows — the pre-DVOL dates
  2021-03-01 to 2021-03-22, where the OKX legs have closes but
  DVOL has none); return panel **2,066 rows** (2021-03-24 to
  2026-11-18; 23 dropped return rows — the 22 plus the first row,
  dropped by differencing). Diff-then-join: log changes computed
  per series on its own dates first, then joined. Regression frame
  2,066 rows; n = 2,065 after the one-step alignment. The planner
  template had estimated 2,064 joint rows.
- **Quality**: the PIT store holds 22,957 rows (2×2,089×5 OKX
  observations + 2,067 DVOL close observations); the quality
  inspection reports no issues.
- **Descriptives**: BTC daily log-return SD 2.80%; DVOL daily
  log-change SD 4.46%.

Raw payloads are in the gitignored cache
`data/cache/btc-dvol-013/` (raw + pit-1d); the manifest records the
fetch details and the endpoint verification.

## Results

All results are from trial T0021 (ledger record `302631f4…`,
recorded 2026-11-19T17:20:11Z). The test family has one test — the
primary — so the Holm adjustment is the identity on it.

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily BTC→BTC_DVOL, ETH factor (primary) | 2,065 | +0.100154 | 0.082882 | +1.21 | 0.2269 | 0.2269 | 0.001195 | 0.001194 |
| no-factor control | 2,065 | +0.035484 | 0.046598 | +0.76 | 0.4464 | — | 0.000461 | 0.000461 |
| naive (same-bar) alignment | 2,064 | +0.089885 | 0.106504 | +0.84 | 0.3987 | — | 0.001080 | 0.000955 |
| reverse placebo (BTC_DVOL→BTC) | 2,065 | +0.038485 | 0.017912 | +2.15 | 0.03167 | — | 0.003340 | 0.003338 |
| amplitude check (abs BTC→BTC_DVOL) | 2,065 | −0.229945 | 0.051044 | −4.50 | 6.64e-06 | — | 0.009932 | 0.009927 |

### Primary test: lagged BTC return → next-day BTC_DVOL change

| Statistic | Value |
| --- | --- |
| Observations | 2,065 |
| Coefficient (per unit log return) | +0.100154 |
| HAC standard error (lag 5) | 0.082882 |
| t-statistic | +1.208 |
| p-value | 0.2269 |
| Holm-adjusted p-value | 0.2269 |
| Partial R² | 0.001195 |
| Incremental R² | 0.001194 |
| Base R² → augmented R² | 0.000558 → 0.001752 |

The coefficient has the **opposite sign to the preregistered
leverage-effect expectation** (negative): it is positive, 1.21
standard errors from zero, and the partial R² is 4.2x below the
preregistered minimum effect size of 0.005. In economic terms: a
one-standard-deviation BTC move (2.80%) predicts a +0.28% ± 0.23%
next-day DVOL log change — nothing, on a target whose daily change
standard deviation is 4.46%, and in the wrong direction besides.

The no-factor upper bound is the same null: coefficient +0.035484,
p = 0.4464, partial R² = 0.000461. The ETH control is not masking
an effect — removing it makes the coefficient smaller, not larger.

### Power: what this null rules out

The minimum detectable effect at 80% power (λ = 2.8016, n = 2,065,
one added regressor) is partial R² ≈ 0.003787 — nearly 3x the
BAA10Y studies' MDE (0.001316 at n = 5,957), because the DVOL
sample is a third the size. The observed 0.001195 is ~3.2x below
the MDE, and the 0.005 threshold is 1.32x above it. The null rules
out any effect at or above partial R² ≈ 0.0038. It does not rule
out a smaller effect — and the power boundary here is genuinely
weaker than in the BAA10Y studies: an effect between 0.0013 and
0.0038 would have been detectable there and is not detectable
here. That is the price of a 5.7-year sample against a 23-year
one, and it is stated plainly rather than hidden behind the
rejection.

### Naive lead-lag scan (descriptive)

Pearson correlations between the BTC log return and the DVOL log
change at lags 0–5 (unlagged changes, descriptive only):

| Lag | n | r |
| --- | --- | --- |
| 0 (same bar) | 2,066 | −0.2691 |
| 1 (tradeable, PIT-correct) | 2,065 | +0.0270 |
| 2 | 2,064 | −0.0550 |
| 3 | 2,063 | +0.0373 |
| 4 | 2,062 | −0.0141 |
| 5 | 2,061 | +0.0164 |

The same-bar correlation is −0.2691 — the leverage effect is
plainly present **contemporaneously**: BTC falls and DVOL rises
within the same 16:00–16:00 bar. But it does not carry over: the
lag-1 correlation (the tradeable alignment) is +0.0270, and every
lagged correlation is near zero. This is the lab's recurring
pattern in its cleanest form — same-day co-movement with no
next-day carryover — now observed on a crypto-native pair with no
publication lag anywhere in the chain. The lag cannot be blamed:
both legs are real-time, and the same-bar effect is large enough
that a lagged echo of any meaningful size would show up in the
scan.

### Naive alignment (same-bar, descriptive)

Running the primary regression with the same-bar BTC return (the
lookahead version — pairing the DVOL change over t+1 with the BTC
return over t+1) also gives nothing: coefficient +0.089885,
p = 0.3987, partial R² = 0.001080, n = 2,064. Note the base R² of
this regression is 0.115634 (against 0.000558 for the primary):
the same-bar ETH factor explains a large share of the same-bar
DVOL change, which is expected — the contemporaneous crypto common
factor moves DVOL within the bar. The BTC return adds nothing on
top of it. **The lag is not what killed the effect**: even with
lookahead, the signed BTC return carries no incremental
information about the DVOL change.

### Reverse placebo (descriptive, not in the test family)

BTC_DVOL → BTC (lagged DVOL change predicting the next-day BTC
return): coefficient +0.038485 per unit log change, p = 0.03167,
partial R² = 0.003340, n = 2,065. **Nominally significant at the
0.05 level — but it must not be read as reverse transmission.**
First, it is descriptive only: it enters no test family and
carries no Holm adjustment, so a single p = 0.032 among the
study's many descriptive statistics is weak evidence. Second, its
partial R² (0.003340) is below the 0.005 threshold the lab uses
for a meaningful effect, and below the MDE (0.003787). Third, the
sign is positive — a DVOL rise predicting a BTC rise — which has
no leverage-effect reading and no preregistered interpretation.
Descriptive only; it enters no verdict. (The lab has seen this
before: study 008's reverse was nominally significant at
p = 0.0004 and study 012's at p = 0.0194, both descriptive only.)

### Amplitude check (descriptive, not in the test family)

|BTC return| → next-day DVOL change: coefficient −0.229945,
SE 0.051044, t = −4.50, p = 6.64e-06, partial R² = 0.009932,
n = 2,065. This is the study's most eye-catching descriptive
number — nominally significant at a high level, and the only
partial R² in the study above the 0.005 threshold — and it is
reported here in full precisely because it must **not** be
promoted. Three reasons:

1. **It was preregistered as descriptive only.** The amplitude
   dimension was named in the preregistration as a supplement
   outside the test family, with the explicit instruction not to
   promote it after the fact. Promoting it now would be exactly
   the post-hoc selection the preregistration exists to prevent.
2. **The sign is the opposite of the naive amplitude story.** A
   positive coefficient would say "big moves today → higher
   volatility tomorrow". The observed coefficient is negative:
   big moves today predict a DVOL *fall* tomorrow.
3. **The natural reading is DVOL level mean-reversion, not a
   leverage channel.** Big BTC moves coincide with a high DVOL
   level today (the contemporaneous leverage effect — scan lag 0
   is −0.2691), and a high DVOL level mean-reverts, so the DVOL
   change over the next bar is negative. The baseline controls the
   DVOL *change* over the bar, not the DVOL *level*, so the
   amplitude predictor picks up the level mean-reversion channel
   the baseline leaves open. This reading is an interpretation,
   not a tested claim — the regression does not include the DVOL
   level, so it cannot distinguish the mean-reversion channel
   from a genuine amplitude channel. A follow-up that wants to
   test the amplitude dimension properly would need to control
   the DVOL level (and a fresh preregistration).

The amplitude check is a hypothesis-generating observation about
DVOL mean-reversion, not evidence of BTC→DVOL transmission. It
enters no verdict and no graph edge.

### Sub-period stability (descriptive)

| Sub-period | n | Coefficient | SE | Partial R² |
| --- | --- | --- | --- | --- |
| 2021 | 282 | +0.004231 | 0.173722 | 0.000005 |
| 2022 | 364 | −0.207610 | 0.190688 | 0.002604 |
| 2023 | 364 | +0.219940 | 0.250761 | 0.002451 |
| 2024 | 365 | +0.167200 | 0.148723 | 0.005153 |
| 2025–2026 | 686 | +0.151214 | 0.126543 | 0.002111 |

No stable effect. The coefficient flips sign across years
(negative only in 2022), and the standard errors are large in
every block. The 2024 partial R² (0.005153) is just above the
0.005 threshold — but it is descriptive, its coefficient is
positive (the wrong sign), and it is far below the sub-period MDE
at n = 365 (≈ 0.0211). There is no regime in which the
preregistered (negative) effect appears at a meaningful size.

### Walk-forward out-of-sample

9 folds, 0 skipped, 1,065 test rows. All-folds OOS incremental R²
= +0.002230 (baseline MSE 0.00140567, augmented MSE 0.00140254);
**holdout (6 folds, 685 rows): OOS incremental R² = +0.002538**
(baseline MSE 0.00139934, augmented MSE 0.00139579). Per-fold
incremental R²: +0.003215, +0.006046, −0.010749, +0.001707,
+0.008647, +0.006388, +0.006973, −0.005323, −0.002435 — six of nine
positive, none large. Adding the BTC predictor improves
out-of-sample forecasts slightly in full and on the holdout, which
is the one preregistered criterion that passes. But the improvement
is small in absolute terms (an MSE reduction of 3.6e-06 on the
holdout, against a baseline MSE of 1.4e-03), and it does not
rescue the rejection: the in-sample effect is insignificant,
wrong-signed, and 4.2x below the minimum effect size. A positive
OOS R² on a wrong-signed, insignificant coefficient is a
small-sample curiosity, not transmission evidence.

### Informational cost assessment (not a verdict criterion)

The gross sign-rule edge on the 685 holdout OOS augmented
forecasts is **+0.000968 log-change units per day**,
block-bootstrap 95% CI [−0.001486, +0.003565], bootstrap
p = 0.4443, sign accuracy 53.7%. The interval includes zero and
the p-value is nowhere near significant — the sign rule's gross
edge is indistinguishable from noise, which is consistent with
the insignificant primary test. Unlike studies 009 (gross edge
p = 0.0375) and 010/011, where the gross edge was positive and
the tension between the edge and the OOS R² had to be explained,
here there is no tension to explain: the edge, the CI, and the
primary test all point the same way. The same caveats apply
regardless:

1. It is **gross with zero costs applied**, on an index that is
   not directly tradable. A straddle position would need option
   prices that the public API does not provide (see the cost-gate
   section), so the "edge" has no P&L meaning; it is an upper
   bound on a tradable edge that is not measured here.
2. It is **not in the verdict** — the preregistration fixed the
   three-criterion verdict before any result was seen, and the
   informational assessment carries no verdict weight.

The informational assessment is reported because the preregistration
said it would be reported — not because it changes anything.

## Verdict

| Criterion | Threshold | Observed | Pass |
| --- | --- | --- | --- |
| Holm-adjusted primary p | < 0.05 | 0.2269 | No |
| Primary partial R² | ≥ 0.005 | 0.001195 | No |
| Holdout OOS incremental R² | > 0 | +0.002538 | Yes |

**H0018 REJECTED** — 1 of 3 criteria pass. The state transition
was recorded with the trial numbers as the reason; the ledger is
anchored (`trials.jsonl.anchor`, 1 record, latest hash
`302631f4…`).

The rejection is not a borderline call on the two decisive
criteria: the primary p is 0.23, the coefficient points the wrong
way, and the effect size is 4.2x below the minimum. The one
passing criterion (a positive holdout OOS R²) is a small
improvement on a wrong-signed, insignificant coefficient. The
leverage effect is real in this data — the same-bar correlation is
−0.2691 — but it is contemporaneous, not predictive: by the next
bar it is gone. That is the same conclusion the lab has reached
for every lead-lag pair it has tested, now on a crypto-native pair
with no publication lag to hide behind.

## Limitations

- **Daily frequency.** The transmission, if it exists at intraday
  horizons, is invisible here. The same-bar correlation (−0.2691)
  shows the leverage effect operates within the bar; daily data
  cannot say how it unfolds inside the bar, or whether a
  shorter-horizon lag (hours) carries information.
- **The 16:00 UTC snapshot is a choice.** A different daily
  snapshot time would give a different panel. The convention was
  fixed in the preregistration and is the only one this study's
  numbers speak to; testing another convention needs a fresh
  preregistration.
- **One control.** Only the ETH log return was controlled for
  (plus the target's own history). Other common factors (rates
  volatility, the BTC options skew, funding rates) were not in the
  model. The no-factor upper bound is also null, which limits how
  much a missing control could be hiding, but it does not
  eliminate the possibility.
- **The reverse placebo is nominally significant (p = 0.0317).**
  See the reverse-placebo section for why it carries no weight —
  but a nominally significant descriptive statistic among many is
  expected by chance, and this one is below the threshold and the
  MDE.
- **The amplitude check is nominally significant (p = 6.6e-06)
  and above the 0.005 threshold.** See the amplitude section for
  why it is not promoted: it was preregistered as descriptive
  only, its sign is opposite to the naive amplitude story, and
  the natural reading is DVOL level mean-reversion. The
  mean-reversion reading is an interpretation, not a tested claim.
- **The informational gross edge (+0.000968/day, p = 0.4443) is a
  descriptive statistic on a non-tradable index.** See the
  cost-assessment section for why it carries no weight.
- **Sample size.** n = 2,065 gives an MDE of 0.003787, nearly 3x
  the BAA10Y studies' MDE. The null rules out effects at or above
  partial R² ≈ 0.0038; a smaller effect is not ruled out. The DVOL
  history starts in 2021, so the sample cannot be extended
  backwards; it grows by one row per day.
- **The DVOL endpoint's 1,000-point cap** means the hourly fetch
  depends on the 40-day chunking and the truncation guard. A
  future re-fetch that changes the chunking without the guard
  could silently truncate the series; the guard is in the fetch
  script, not in the adapter.
- **OKX-vs-Deribit venue basis.** The predictor leg is an OKX
  perpetual price and the target leg is a Deribit index. The two
  venues' BTC prices can differ by small amounts at any instant;
  the study treats the OKX close as the market price and does not
  model the basis.

## Reproducibility

```bash
.venv/bin/python research/btc-dvol-013/preregister.py   # idempotent after registration
.venv/bin/python research/btc-dvol-013/fetch_data.py    # re-fetches; manifest SHA changes with fetch time
.venv/bin/python research/btc-dvol-013/run_trial.py     # trial T0021 (already recorded; re-running creates a new trial)
```

The trial binds the preregistered v1 spec fingerprint
(`463f8e79…`), the manifest SHA-256 (`92f1e247…`), and the code
revision (`7ed07528…`). Re-running the trial script records a new
trial against the current HEAD; it does not overwrite T0021.

## Scaffold feedback (sixth real use)

Study 008 recorded seven gaps from the 6c scaffold's first real
use, and studies 009, 010, 011 and 012 found no new gaps. This
study hit **no new gaps either**. Every hand-adaptation the study
needed was a repeat of a known item:

- The generated `run_trial.py` wired only the primary test and a
  two-criterion verdict, with walk-forward and the cost gate as
  `NotImplementedError` stubs — 008's item 1. Same replacement, same
  full pipeline.
- `preregister.py` was not idempotent — 008's item 4. Same fix
  (re-running after registration leaves the registration untouched).
- The scaffold generated a 2-instrument universe; the ETH control leg
  was added by hand — 008's item 6.
- The draft's predictor/target wording needed the researcher's
  correction in the design — 008's items 5/7. Here the draft's
  "BTC_DVOL return" was unambiguous (a log change of an index
  level), so no correction of the target's transform was needed —
  but the snapshot convention (16:00 UTC) and the control choice
  (ETH, not SPX) are study-specific design work the scaffold
  passes through as TODOs, as in studies 008–012.
- The generated `fetch_data.py` had no fail-fast checks and a
  hard-coded content type — 008's item 3 — and no endpoint
  verification (the DVOL 1,000-point cap, the hourly chunking, and
  the snapshot extraction are study-specific work the scaffold
  never claimed to do).

One fix from study 008 verified: the generated `run_trial.py` now
passes `BAR_SECONDS = None` (the 008 bug, `bar_seconds=86400`, would
have voided every Monday return). Confirmed in the generated file
before adaptation.

One placeholder-hygiene check from study 009 verified: the generated
files contain no real-ID placeholder specs — only the real H0018
appears (the H9002/H9003/H9004 placeholders live only in the 6c
validation, not in generation).

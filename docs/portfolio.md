# Portfolio (Stage 5)

Paper-portfolio infrastructure for future strategy research: a
unified prediction contract, a historical funding-rate series, a
descriptive risk model, a paper portfolio with three-way
reconciliation, and forward shadow evaluation with drift and
alpha-decay monitoring. This is infrastructure, not a strategy:
nothing in this document is a trading signal, an alpha claim, or a
performance result, and the lab's supported findings (H0010/H0011,
level and event effects) are not used to derive any signal here.

Stage 5a covers roadmap items 1–3 (prediction contract, risk
model, paper portfolio) plus the historical funding-rate series
that closes the Stage 4b data gap. Stage 5b covers items 4–5
(forward shadow evaluation, drift and alpha-decay monitoring):
the frameworks for scoring a prediction stream as it runs forward
and for watching it decay. The lab still has no real strategy, so
5b is validated on synthetic streams with known ground truth and
on the 5a lag-return fixture — never on a signal derived from the
lab's findings.

Code: `src/myquant/portfolio/` (`predictions.py`, `risk.py`,
`portfolio.py`, `shadow.py`, `drift.py`),
`src/myquant/execution/funding.py`,
`src/myquant/adapters/okx_funding.py`. Validation:
`research/portfolio-5a/` (daily fixtures + tape end-to-end check),
`research/portfolio-5b/` (shadow evaluation on synthetic streams
+ real panel) and `research/funding-history/` (series report).

## Prediction contract

`src/myquant/portfolio/predictions.py` — one typed contract for
predictions across horizons, so that any future model output
carries the same fields and the same point-in-time semantics.

Fields (`Prediction`):

- `prediction_id`, `instrument_id`, `model_id`, `model_version`,
  `feature_version` — identity and versioning.
- `target` — what is predicted, with a fixed definition:
  `log_return` (log close-to-close return over the horizon),
  `abs_log_return` (|log return| over the horizon),
  `direction` (−1 / 0 / +1), `realized_volatility` (realized
  volatility over the horizon). The target's definition is part of
  the contract, not a free-text label.
- `horizon` — a `timedelta` (explicit unit); `target_time` is
  `event_time + horizon`.
- `event_time` — when the predicted interval starts; `available_at`
  — when the prediction becomes usable. PIT semantics:
  `available_at >= event_time` is enforced, and
  `require_available(prediction, decision_time)` raises for a
  prediction not yet available at the decision time — a query for
  the future is refused, not answered with a stale value.
  `available_predictions` filters a collection to the available
  subset at a decision time.
- `value` — the prediction; finite, and consistent with the target
  (direction ∈ {−1, 0, +1}; absolute return and volatility ≥ 0).
- `uncertainty` — optional, at most one of `uncertainty_std` (a
  standard deviation, ≥ 0) or `uncertainty_interval` (a
  [lower, upper] interval, lower ≤ upper, finite). The two forms
  are mutually exclusive so no consumer has to guess which one a
  value is.

The contract itself produces no predictions. `make_lag_return_fixture`
generates mechanical fixture predictions ("next return = last
return", log-return and absolute-return targets only) for tests and
validation; it is labelled a fixture in its name and docstring and
is not a strategy.

## Historical funding-rate series

Closes the Stage 4b data gap: funding is no longer only an input
parameter. `src/myquant/adapters/okx_funding.py` fetches OKX
`/public/funding-rate-history` (public, no key); `research/
funding-history/fetch_data.py` pulled the full reachable history
for BTC/ETH/SOL-USDT-SWAP, stored raw pages in the RawStore with a
manifest, and `research/funding-history/funding_report.md`
records the findings.

Observed facts (2026-11-19):

- Depth: about **93 days** — 280 rows per instrument,
  2026-08-17T16:00:00Z to 2026-11-18T16:00:00Z, complete grid,
  zero missing. The retention floor moves (a 281st row seen minutes
  before the fetch was gone by fetch time), so the floor is
  approximate and must be re-established on every pull. Anything
  needing rates before 2026-08-17 has no data here.
- Pagination: `after=<ms>` pages backwards (rows strictly older
  than the cursor, newest first, ≤ 100/page). `before` does NOT page
  backwards on this endpoint — it acts as a lower bound — and is
  never sent. The adapter pages with `after` only.
- The settled rate at the previous settlement (from the live
  `/public/funding-rate` endpoint) matches the history row at that
  settlement exactly, for all three instruments.
- Settlement grid: 00:00 / 08:00 / 16:00 UTC. Sign convention (same
  as the 4b cost model): a positive rate means longs pay shorts.
  The funding amount for a signed position held across a settlement
  is `position x price x contract_value x rate` — positive means
  the holder pays. The rate is the settled rate for the interval
  *ending* at the settlement time.
- 4b cross-reference: 4b's recorded live rate 0.0000215 (read
  ~08:10 UTC 2026-11-18) is a mid-interval *estimate* for the
  interval ending 16:00 UTC, not the settled rate (0.00006348);
  the two differ as they should. No settlement was crossed in
  either 4b window, so 4b's zero funding total is unaffected.

`src/myquant/execution/funding.py`:

- `FundingRateSeries` — validated, settlement-indexed rows
  (strictly increasing, every row on the funding grid; exact-match
  `rate_at` lookups; `coverage()` reports missing grid slots).
- `compute_funding_from_series` — funding due on the position built
  by a set of fills, at historical rates. Settlements with no rate
  in the series, or no price, are skipped and listed in the result:
  a skipped settlement is missing data, not zero funding. **No
  interpolation or extrapolation, ever.**
- The original single-rate `costs.compute_funding` (rate as an
  input parameter) is unchanged as the fallback path when no series
  exists.

## Risk model

`src/myquant/portfolio/risk.py`. Everything here is descriptive,
not predictive: a covariance estimated from past returns describes
past co-movement; a VaR computed from past returns describes past
tail losses. None of it forecasts anything.

### Exposure aggregation

`aggregate_exposure` takes per-instrument `(quantity, mark_price,
contract_value)` and returns long/short notional separately, net
and gross notional, concentration (largest single instrument's
share of gross notional), and leverage (gross notional / equity).
Leverage is `None` when equity is not positive — undefined, not
zero or infinity. Flat instruments contribute nothing; an empty
book has zero exposure and zero leverage.

### Covariance

`sample_covariance` — sample covariance of synchronized return
series (columns), default ddof = 1. Callers do panel construction
(per-series diff-then-join on a shared grid, as in the lab's
studies); the function validates only shape and finiteness.

`ledoit_wolf_covariance` — Ledoit–Wolf (2004) shrinkage toward a
scaled identity, following "A well-conditioned estimator for
large-dimensional covariance matrices" (*Journal of Empirical
Finance* 11(5)). The sample covariance uses the paper's 1/T
normalization; the target is μI with μ = tr(S)/N; the intensity is

    δ* = max(0, min((π − ρ)/(T·γ), 1))

where γ = ||S − μI||²_F, π is the sum of the asymptotic variances
of the entries of √T·S, and ρ is the asymptotic covariance term
correcting for the estimated target scale μ̂. (π and ρ are per-√T
quantities, so the factor T appears explicitly; δ* is O(1/T), as
the paper requires. An earlier draft of this module omitted the T
and produced δ* = 1.0 on every dataset — caught by a behavioural
check, fixed, and now covered by a test that re-derives δ* from
the paper's formulas with explicit loops.) When γ = 0 (S is already
proportional to the identity), δ* = 0. The shrunk matrix is
(1 − δ*)·S + δ*·μI. The implementation was verified against a
slow explicit-loop derivation of the paper's formulas (agreement to
machine precision) and behaves correctly: δ* falls with T and the
shrunk matrix beats the sample matrix on Frobenius distance to a
known truth in a fixed-seed check.

`portfolio_volatility` — √(w′Σw) for one weight vector (signed
weights allowed).

### VaR / ES

`historical_var_es` — historical-simulation VaR and expected
shortfall on a return series, at a stated confidence (default
0.95). VaR is the (1 − confidence) quantile of returns, negated
(a loss is positive); ES is the mean loss beyond VaR. Quantiles
use linear interpolation. Both are floored at zero: a positive tail
quantile means no loss at that confidence. Both are measured on
the supplied window only — the window is the caller's choice and
must be stated wherever the numbers are reported.

## Paper portfolio

`src/myquant/portfolio/portfolio.py` — `PaperPortfolio`, a
perpetuals paper portfolio with an auditable ledger.

Cash model (USDT-margined perpetuals):

    equity = cash + unrealized PnL
    cash   = initial_cash + realized PnL − fees − funding paid

Buying does not deduct notional from cash; only fees, funding, and
realized PnL move cash. Positions are per instrument in contracts
with an average-cost basis: adding to a position re-weights the
average cost; reducing realizes PnL on the closed part
(`closed x (fill price − average cost) x direction x contract
value`); a flip closes the old position and opens the remainder at
the fill price. Fees split maker/taker by the fill's `is_maker`
flag; funding is applied as settlements (positive amount = paid)
and tracked separately from fees.

Events — fills (`apply_fill`, or `apply_order_result` for a whole
simulated order), funding settlements (`apply_funding`), marks
(`mark`) — must arrive in non-decreasing time order; the portfolio
raises on an out-of-order event rather than silently re-ordering a
ledger. Every event appends an equity-curve snapshot carrying the
mark time, so mark staleness is visible. A mark is the latest known
price per instrument; an instrument's mark initializes to its first
fill price (unrealized is then zero at that instant, which is
exactly right) and moves only on `mark` calls. `mark` requires a
price for every open position — an unmarked open position is an
error, not a zero.

Contract values are per instrument, passed at construction (from
the live `/public/instruments` spec: BTC-USDT-SWAP 0.01,
ETH-USDT-SWAP 0.1, SOL-USDT-SWAP 1.0, verified 2026-11-19 and
recorded in the panel manifest).

## Reconciliation

`reconcile()` is three-way and reports exact residuals:

1. **Equity identity.** Equity from cash + unrealized vs equity
   from the ledger (initial + realized − fees − funding +
   unrealized). Cash is updated incrementally per event while the
   accumulators are kept separately, so a missed update in either
   shows up here.
2. **Independent PnL cross-check.** Book PnL (realized +
   unrealized, average-cost basis) vs an independent PnL from raw
   fill cash flows plus current position values at mark: buys pay
   cash (negative flow), sells receive it, and the open position is
   worth quantity × mark × contract value. No average cost anywhere
   in this leg — it validates the average-cost bookkeeping against
   raw fill economics.
3. The equity-change identity is (1) rearranged and reported with
   it.

`passed` requires every |residual| ≤ 1e-9 USDT
(`RECONCILIATION_TOLERANCE`), a floating-point tolerance, not a
rounding: the reported residuals are the exact floats. A residual
above the tolerance is a bug to fix, never a parameter to tune.

## Validation

`research/portfolio-5a/validate_portfolio.py` (offline; report in
`research/portfolio-5a/validation_report.md`). Panel: 49 confirmed
OKX 1D bars per instrument, first bar opens 2026-09-30T16:00Z, last
closes 2026-11-18T16:00Z (2026-10-01 to 2026-11-18 in UTC+8),
fetched by `research/portfolio-5a/fetch_panel.py` into the RawStore
with a manifest. Funding: the historical series above, covering the
whole window; the reference price at each settlement is the close
of the last daily bar completed at or before the settlement
(PIT-clean; 0 h stale for 16:00 settlements, 8 h for 00:00, 16 h
for 08:00 — a documented daily-granularity approximation).

Fill convention (daily fixtures): fills execute at the bar-close
price ± 1 bp adverse slippage, taker fee 0.05% (OKX Regular) on
executed notional, quantities rounded to 0.01 contracts. This is a
stated close-fill convention, **not** tick-level simulation — no
tick tape exists for this window, and fabricating one from daily
bars would be dishonest. Slippage is a fixed 1 bp assumption, not
a measurement.

Fixtures (mechanical, claim-free; framework validation only):

- **A — buy-and-hold fixed contracts.** At the first bar close,
  buy BTC 50 / ETH 30 / SOL 50 contracts; hold to the window end.
- **B — weekly rebalance to fixed notional.** Every 7th bar close,
  rebalance each instrument to 20,000 USDT notional.

Results (2026-11-19 run; initial cash 100,000 USDT each):

| Fixture | Final equity | Realized | Unrealized | Taker fees | Funding paid |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 84,160.92 | 0.00 | −15,457.55 | 27.99 | 353.5383 |
| B | 77,274.97 | −11.16 | −22,360.46 | 38.18 | 315.2229 |

Funding: 144 settlements per instrument per fixture, none skipped.
Fixture A: BTC 300.8174, ETH 28.2274, SOL 24.4936. Fixture B: BTC
149.0289, ETH 75.3727, SOL 90.8213. (The window's rates are mostly
positive, so long fixtures pay funding; the totals differ between
fixtures because B holds smaller BTC notional and larger ETH/SOL
notional than A.)

Reconciliation residuals (exact floats):

| Check | Residual (equity) | Residual (PnL) | Passed |
| --- | ---: | ---: | ---: |
| A | 0.00e+00 | −5.46e-12 | yes |
| B | 2.91e-11 | 3.64e-12 | yes |
| 2h tape end-to-end | 4.37e-11 | 1.05e-13 | yes |

Hand-checks (each recomputed from raw inputs, outside the
portfolio's code path): first BTC fee matches to 0.0; first BTC
funding settlement matches to 0.0; independent final-equity
recomputation matches to 0.0 (A) and 4.37e-11 (B, summation order).

Independent recomputation (review): the headline numbers were
re-derived a second time in plain stdlib Python, reading the OKX
raw payloads straight from the RawStore blobs with no repo imports:
both fixtures' fees, per-instrument funding totals (144
settlements each), unrealized PnL and final equities; the daily
equity curves and both fixtures' VaR/ES; the Ledoit–Wolf δ*
(0.0225, from an explicit-loop implementation of the paper's
formulas); both portfolio volatilities; and gross notional,
leverage and max single share. All matched. The funding cache was
also checked live: a fresh pull of the newest 100 funding rows per
instrument matches the cache exactly (0 mismatches), and no new
settlement has occurred since the fetch.

Simulator end-to-end check: 16 market orders (buy/sell 1.0 BTC
contract every 15 minutes) replayed through the Stage 4b
simulator on the 4a two-hour tape (2026-11-18 05:00–07:00 UTC),
fills applied to a portfolio, marked at the last print (64,579.1
USDT). All 16 fills are book-unknown (the tape has no in-window
snapshots, as in 4b); final equity 99,993.80 USDT, fees 5.1690
USDT, no funding settlement crossed. Reconciliation passes (see
table above).

Descriptive risk metrics on the window (48 daily log returns;
descriptive only): Ledoit–Wolf δ* = 0.0225; daily portfolio
volatility 0.0209 (sample) / 0.0207 (LW) for A, 0.0244 / 0.0240
for B; historical-simulation VaR 95% (daily) 0.0235 (A) / 0.0385
(B), ES 0.0291 (A) / 0.0412 (B). With 48 observations these
estimates are noisy; they describe the window, they predict
nothing.

## Stage 5b — forward shadow evaluation and drift monitoring

`src/myquant/portfolio/shadow.py` scores a prediction stream as
its target windows close; `src/myquant/portfolio/drift.py` watches
the scored stream for decay and distribution drift. Both are
venue-agnostic: outcomes come from a caller-provided provider
(a function from a `Prediction` to a realized value or `None`).

### Scoring discipline

`score_predictions(predictions, outcome_provider, scored_at,
fit_window, baselines)` enforces three hard rules:

1. **Forward only.** A prediction is scored only when `scored_at`
   is strictly after its `target_time`. A prediction whose window
   has not closed is recorded as unscored (`not_yet_due`) — never
   estimated from partial information. Scoring exactly at
   `target_time` is refused.
2. **Missing outcomes stay missing.** If the provider returns
   `None` for a due prediction, it is recorded as unscored
   (`outcome_missing`): missing data, not a zero error.
3. **No in-sample scores.** An optional half-open fit window
   `[start, end)` declares the in-sample period; predictions with
   `event_time` inside it are refused scoring (`in_fit_window`),
   so in-sample scores cannot masquerade as out-of-sample ones.

The provider is only queried for predictions that are due and
outside the fit window. Every run produces a deterministic
scored-predictions ledger (`shadow_ledger_json`): one record per
prediction with its outcome, error, and scoring status, in
(event_time, prediction_id) order. `scored_at` is an input, never
read from the clock, so identical inputs reproduce the ledger
byte-identically.

### Metrics and baselines

Metrics are computed per target type, over the scored predictions
only, with `e = predicted − outcome`:

- All targets: MSE = mean(e²), MAE = mean(|e|), bias = mean(e).
- `log_return`: Pearson correlation (undefined when either series
  has zero variance) and hit rate = fraction of sign agreement
  (sign(0) = 0).
- `direction`: accuracy = fraction with predicted == outcome, and
  confusion counts over non-zero pairs (TP/FP/TN/FN on +1/−1);
  predictions or outcomes of exactly 0 are counted separately and
  do not enter the confusion counts.

Every score is reported against baselines. The **zero baseline**
(constant 0; for `direction` the constant 0) is always computed on
the same scored set. Named baselines — e.g. the lag-return fixture,
generated by the caller with `make_lag_return_fixture` — are scored
with the same provider and discipline and matched to the stream by
(instrument, event_time, target); skill is computed only over the
matched pairs, so the comparison is like-for-like. Skill is
`1 − MSE / MSE_baseline`; negative means worse than the baseline.
Skill is `None` when undefined (no matched baseline scores, or a
zero baseline MSE). A baseline with no matches at all is reported
with zero pairs, not silently dropped.

### Drift monitoring

`drift.py` works on scored streams (rolling series) and on outcome
windows:

- **Rolling performance.** Expanding and fixed rolling windows
  over per-prediction errors: rolling MSE, rolling skill against a
  baseline's errors on the same windows, rolling hit rate. A
  window that is not yet full returns `None` — an incomplete
  window is missing data, not a shorter window.
- **PSI (population stability index).** Reference window vs recent
  window, on equal-frequency bins from the reference sample's
  quantiles (bin count configurable; duplicate edges from tied
  values are merged). PSI = Σ (actual − expected) ×
  ln(actual / expected), with shares floored at ε = 1e-4 so empty
  bins contribute a finite amount; out-of-range values fall into
  the outermost bins. The 0.1 / 0.25 cutoffs are conventional
  detection thresholds, **not** significance levels.
- **Window shift.** Recent-vs-reference mean difference with a
  HAC standard error (an indicator regression through the kernel's
  Newey-West estimator) and a volatility ratio with a
  circular-block bootstrap interval on the log ratio (same
  resampling scheme as the kernel's block bootstrap; fixed seed).
- **Decay estimation.** A linear trend on the rolling skill series
  (OLS + HAC standard error; `max_lag` should cover the overlap
  the rolling window induces, window − 1 being the natural
  choice). Only if the slope is significantly negative is an
  exponential decay fitted (skill_t = a·exp(−λt) + c, grid search
  over the half-life); only if that fit is good enough
  (R² ≥ 0.25 by default) is a half-life reported — with a residual
  block-bootstrap interval, the fit R², and a stability flag. A
  non-significant trend or a poor fit reports "not detected"
  instead of a number. The half-life is a fragile estimate and is
  never reported as a bare point estimate.
- **Alerts.** Configurable rules emit flags (prompts, not
  conclusions): N consecutive rolling windows with skill below a
  threshold (default N = 3, threshold 0), and PSI above a
  threshold (default 0.25). Each flag carries its type, trigger
  time, value, and threshold. A `None` (incomplete) window breaks
  a skill run without flagging.

There is no KS test: PSI plus the window shift cover distribution
drift, and a second overlapping detector was not added.

### Stage 5b validation

`research/portfolio-5b/validate_shadow.py` (offline, fixed seeds;
report in `research/portfolio-5b/validation_report.md`, ledger in
`shadow_ledger.jsonl`, 3,180 records). Four synthetic streams with
known ground truth, all on a daily grid with a 1D horizon:

| Stream | Design | Result |
| --- | --- | --- |
| Oracle | predictions = outcomes, n = 200 | MSE exactly 0, skill exactly 1, hit rate 1, correlation 1; direction accuracy 1 (TP 95, TN 105) |
| Noise | small-amplitude independent noise, n = 500 | skill vs zero −0.0071, hit rate 0.526, direction accuracy 0.504 (TP 119, FP 118, TN 133, FN 130) |
| Decaying signal | β_t = 0.4·0.5^(t/100), noise N(0, 0.2σ), n = 1000 | Trend slope −0.000400/prediction, HAC p = 4.0e-08; half-life **129.5** (truth 100), 95% interval [88.3, 189.9], R² = 0.846, stable; 15 skill flags, first at rolling-window index 278 |
| Regime break | N(0, 0.02) → N(0.03, 0.04) at index 250, n = 500 | First PSI flag on the first window containing post-break data (PSI 1.062; pre-break windows 0.000 and 0.207); window shift mean diff 0.0301 (HAC p = 6.0e-09), vol ratio 2.096, 95% interval [1.677, 2.580] |

Design notes (recorded in the script): β_0 is deliberately
moderate so the skill curve is approximately a single exponential
— a large β_0 makes the skill curve a sum of two exponentials
(2β − β²) and biases a single-exponential fit (an early draft
with β_0 = 0.8 estimated 218.7 against a truth of 100). The decay
analysis uses the zero baseline with a 40-prediction window: a
20-prediction window leaves the rolling skill too noisy for the
half-life to be identified, and the series is long (10
half-lives) so the decay is fully observed. The noise stream is
deliberately small-amplitude: a same-scale independent predictor
would score skill near −1 against the zero baseline (pure added
variance). The last fully pre-break PSI window reads 0.207, close
to the 0.25 alarm — sampling noise at that window size, and part
of why a flag is a prompt, not a conclusion.

Real panel: the 5a lag-return fixture scored forward on the 49-bar
daily panel (47 predictions per instrument per target, scored at
2026-11-19T16:00Z). Log-return skill vs zero is about −1.05
(BTC −1.05, ETH −1.02, SOL −1.10): the lag adds variance without
signal, as expected for near-unpredictable daily returns.
Abs-log-return skill vs zero is 0.12–0.30 (BTC 0.21, ETH 0.30,
SOL 0.12), reflecting volatility clustering in |returns| — not
any trading edge. With 47 predictions over seven weeks, nothing is
claimed from either; the run validates the framework end to end.

22 mechanical checks in the script, all passing; the script raises
if any fails. Re-running reproduces the ledger byte-identically
and the report except its timestamp line.

Independent recomputation (review): the headline numbers were
re-derived a second time in plain Python with no repo imports —
all stream metrics (MSE/MAE/bias/correlation/hit rate/accuracy/
confusion/skill) straight from the committed ledger; the three
lag-baseline skills from matched ledger outcomes; all five PSI
values, the window-shift mean difference with its HAC standard
error and p-value, and the volatility ratio with its bootstrap
interval, from streams regenerated with the documented seeds; the
decay stream's rolling-skill endpoints, trend slope and HAC
p-value (own Newey–West implementation), the exponential grid
fit (half-life 129.5, R² 0.846), and the residual block-bootstrap
interval [88.3, 189.9]; the 15 skill flags and the first flag's
index (278); and all six real-panel fixture scores from the 5a
panel closes. All matched.

## Limitations

- The funding series reaches back only ~93 days (from
  2026-08-17); anything needing earlier rates has no data, and the
  series must not be extended by interpolation or extrapolation.
- Daily fixtures use a close-fill convention, not tick-level
  simulation: no intraday price path, no queue, no book.
- Funding reference prices are daily closes, stale by up to 16 h.
  Settlement-time prices would need the trade tape, which exists
  only for 2026-11-18.
- The 2h tape check is one instrument on one morning; its fills
  are book-unknown by design.
- The fixtures hold fixed contracts / fixed notionals; they are
  not strategies, and their equity paths say nothing about any
  trading idea. No Sharpe, no alpha, no performance claim is made
  anywhere in this stage.
- Risk metrics describe 48 daily observations; the covariance,
  VaR, and ES estimates are noisy, and the Ledoit–Wolf intensity
  reflects that.
- Shadow evaluation needs outcomes: a prediction whose window has
  not closed, or whose outcome is missing, is unscored — the
  framework never fills the gap.
- The decay half-life is a fragile estimate. It needs a long
  series (the validation uses 10 half-lives) and a wide enough
  rolling window; with a 20-prediction window the rolling skill is
  too noisy for the half-life to be identified. A half-life is
  always reported with its interval, fit R², and stability flag —
  or not at all.
- PSI thresholds (0.1 / 0.25) are conventional detection cutoffs,
  not significance levels. A flag is a prompt to look, not a
  conclusion that the distribution changed; at small window sizes
  the threshold's noise floor is substantial (a fully pre-break
  window read PSI 0.207 in validation).
- The lab still has no real strategy: 5b is validated on synthetic
  streams and a naive fixture. The first real use of the shadow
  framework will need its own outcome provider and its own
  fit-window declaration.

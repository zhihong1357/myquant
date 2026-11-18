# Statistical Research Kernel — Stage 2B

This document describes descriptive and inference primitives. They are research utilities, not proof of causality, alpha or a profitable strategy.

## 1. Return and volatility estimators

- `simple_returns`: `P_t / P_(t-1) - 1`
- `log_returns`: `ln(P_t) - ln(P_(t-1))`
- `realized_variance`: `sum(r_t ** 2)`, with no demeaning and no annualization
- `realized_volatility`: square root of the preceding realized-variance measure
- `annualized_volatility`: sample standard deviation with `ddof=1`, multiplied by `sqrt(periods_per_year)`

The two volatility measures answer different questions. The sum-of-squares realized measure accumulates variation over the supplied window; annualized volatility estimates a per-period standard deviation and annualizes it. Do not compare them as though they had identical definitions.

Return inputs use a timezone-aware, unique, ascending `DatetimeIndex`. Missing price observations are not forward-filled. A return is missing if either price in its pair is missing. The realized-variance and annualized-volatility functions reject missing returns; callers must make exclusions explicit before estimation. Corporate actions, contract rolls, stale prices and market-calendar alignment remain upstream data-contract responsibilities.

## 2. Descriptive lead-lag scan

`lead_lag_scan(source, target, lag_steps=...)` reports Pearson correlations between:

`source[t]` and `target[t + k]`

A positive lag therefore means the source series is earlier than the target series by k observations. Inputs must already be synchronized, equally spaced, finite observations on the same calendar. The function does not resample, interpolate, forward-fill, infer the calendar, or search an unbounded lag range. Predeclare lag candidates for confirmatory research.

This is a descriptive cross-correlation diagnostic only. It does not control common factors, test statistical significance, correct for searching many lags, or identify causality. A common driver, non-synchronous trading, stale marks or publication delays can all create apparent lead-lag structure.

## 3. OLS regression

`ols_fit(target, predictors)` fits a deterministic ordinary least-squares model with an intercept by default. Predictors are supplied as a name-to-series mapping, and every series must already be aligned to the target. The design must be full rank and contain more observations than fitted coefficients.

The result includes named coefficients, fitted values, residuals, residual sum of squares, R-squared, adjusted R-squared, rank and residual degrees of freedom. Missing or infinite observations, unequal lengths and collinear predictors are rejected. The function does not perform timestamp joins, lag construction, resampling, imputation, feature scaling, or point-in-time checks.

The result also reports the design matrix's 2-norm condition number. A large condition number means the predictors are nearly collinear and the coefficient estimates are unstable, even though the design is technically full rank.

## 4. Newey-West HAC inference

`newey_west_hac(target, predictors, max_lag=...)` fits the same OLS model and estimates its covariance matrix using a Bartlett-kernel Newey-West heteroskedasticity- and autocorrelation-consistent estimator.

For lag j, the Bartlett weight is `1 - j / (max_lag + 1)`. The covariance includes contemporaneous score covariance plus weighted lagged score cross-products. An optional finite-sample multiplier `n / residual_degrees_of_freedom` is available and defaults to off. A bandwidth of zero gives the HC0 heteroskedasticity-consistent covariance.

Reported p-values use a two-sided asymptotic standard-normal reference distribution. They are not exact small-sample Student-t p-values. Choose the HAC bandwidth before looking at results and report sensitivity across reasonable predeclared bandwidths. HAC adjusts the estimated coefficient covariance for heteroskedasticity and serial dependence under its assumptions; it does not repair look-ahead bias, a misspecified model, non-stationarity, regime changes, stale data, endogenous regressors, or multiple testing.

## 5. Common-factor controlled partial lead-lag

`partial_lead_lag(source, target, lag_steps=k, common_factors=...)` compares two nested models on identical observations.

Base model:

`target[t + k] ~ intercept + target[t] + common_factors[t]`

Augmented model:

`target[t + k] ~ intercept + target[t] + common_factors[t] + source[t]`

The reported source coefficient and HAC inference quantify whether source[t] adds a conditional linear association after the supplied target-history and factor controls. All predictors are aligned at t. Every common factor must have been observable by the decision time t; using a factor measured only at t+k would introduce future information.

The result also reports:

- Incremental in-sample R-squared: augmented R-squared minus base R-squared.
- Partial R-squared: the share of base-model residual sum of squares removed by adding the source.

These are in-sample effect descriptions, not out-of-sample predictive performance. The method controls only for the factors actually supplied and correctly measured. An omitted common driver, a poor proxy, non-synchronous timestamps, publication delays, or measurement error can leave spurious association. A statistically significant source coefficient does not prove a causal arrow or a tradable edge.

The common-factor synthetic test uses the simulator's latent factor as a known-truth oracle solely to test whether the method can remove a deliberately shared driver. That latent value is not an observable market feature and must not be used as a real strategy input.

## 6. Circular block bootstrap

The bootstrap utilities use circular moving blocks:

1. Sample block start positions with replacement.
2. Keep observations within each sampled block in their original order.
3. Concatenate blocks and trim to the original sample length.
4. Repeat using a fixed random seed.

`block_bootstrap_mean_ci` returns a percentile interval for the sample mean. `block_bootstrap_mean_test` creates a null-centered series and calculates a two-sided finite-resample p-value using the +1 correction.

Block bootstrap is intended to preserve short-range serial dependence better than independently shuffling observations. It remains an approximation. The result can be sensitive to block length, non-stationarity, structural breaks and heavy tails. Always report block-length sensitivity and use a sample period that matches the research question. The current implementation does not provide studentized or bias-corrected intervals and should not be represented as a universal solution to time-series inference.

`block_length` must not exceed half the sample size. With fewer than two full blocks the resampling distribution collapses: at `block_length == n` every resample is a cyclic shift of the whole sample, so every bootstrap mean equals the sample mean, the interval degenerates to a point and the mean test always returns the minimum p-value. Block lengths above `n // 2` are rejected rather than silently producing that degenerate result.

## 7. Multiple-testing corrections

`adjust_pvalues` preserves the original input order and provides adjusted p-values plus the decision at a predeclared threshold.

- **Bonferroni** and **Holm** target family-wise error rate (FWER).
- **Benjamini–Hochberg** targets false discovery rate (FDR) under its dependence assumptions.
- **NONE** is allowed only for a single planned test.

The function treats the supplied p-values as the complete family. It cannot know whether the caller omitted unsuccessful experiments. The experiment/hypothesis registry and study protocol must define the family before results are inspected. A search over many lags, factors, assets, model variants or bandwidths is a multiple-testing family, not one isolated test.

## 8. Purged walk-forward validation and out-of-sample scoring

`purged_walk_forward_splits` builds chronological, disjoint held-out test windows. Each fold trains only on observations whose decision times precede the test window. For a test window beginning at T, a training sample is purged when its label end time is greater than or equal to T; equality is treated conservatively as overlap.

An optional pre-test embargo removes additional training observations whose decision times fall within the configured duration immediately before T. In this forward-only design, future rows are never training candidates, so embargo is implemented as an extra historical gap before the test window. The optional maximum training size limits the candidate window before purging and embargo are applied. A final shorter test window is retained.

A test window whose training set falls below `minimum_train_size` after purging and embargo is skipped rather than failing the whole split: the remaining folds are still returned, the skipped window is recorded in the `WalkForwardSplitReport` with its reason, and a warning is logged. Only when every test window is skipped does the splitter raise. Fold numbers are never renumbered, so a fold's number always identifies its test window.

The splitter returns the training, test, purged and embargoed indices for each fold so the exclusions can be audited. Decision timestamps must be timezone-aware, unique and strictly increasing. Label end timestamps must be timezone-aware, aligned one-to-one, and later than their corresponding decision timestamps.

`evaluate_walk_forward_forecasts` compares baseline and augmented predictions on exactly the held-out rows. Its incremental OOS R-squared is:

`1 - SSE_augmented / SSE_baseline`

A positive value means the augmented forecasts reduced squared error relative to the declared baseline. A negative value means they performed worse. When baseline error is zero, the ratio is undefined and returned as null. Fold metrics are also reported, while aggregate error is weighted by the number of held-out observations.

These helpers do not train or tune a model. Callers must fit every model using only that fold's training indices, choose hyperparameters without consulting test outcomes, and supply forecasts generated before observing the held-out target. The splitter also cannot establish whether feature values were actually available at each historical decision time; that remains a point-in-time data-pipeline requirement. Non-overlapping test windows, a predeclared fold schedule, full multiple-testing accounting, and realistic costs remain necessary.

## 9. Event studies and clustered event windows

`event_study(returns, events, pre_event_steps, post_event_steps, expected_returns=...)` calculates cumulative abnormal returns (CARs) over an inclusive event window. Event times must exactly match a timezone-aware, unique, ascending return index, and each complete window must fit inside the sample. Window offsets are observation counts, not inferred calendar durations.

When `expected_returns` is supplied, abnormal returns are actual minus expected returns on an exactly matching index. If omitted, the zero-return benchmark is used, so the result is cumulative raw return rather than a market-model abnormal return. The function does not estimate expected returns or a market model; benchmark construction and PIT validity belong to the caller.

Events whose inclusive windows overlap are joined into connected overlap clusters. The function first calculates each event CAR, then averages event CARs within each cluster. Its overall mean and standard error use cluster means as the inference units, avoiding the false assumption that overlapping event windows are independent. The two-sided p-value uses an asymptotic normal reference and is omitted when fewer than two clusters exist. This is a conservative descriptive adjustment, not a full event-level cluster-robust regression or randomization test; results can be sensitive to cluster composition and event dependence beyond the chosen window.

The caller must define the event universe, event timestamps, event window, expected-return model, confounder exclusions, and complete multiple-testing family before inspecting results. Scheduled macro releases must use their actual publication/availability timestamps, not merely the economic period they describe. Unscheduled events and overlapping macro announcements require explicit classification rather than automatic causal attribution.

## 10. Backtest-overfitting diagnostics: PBO and Deflated Sharpe Ratio

`src/myquant/stats/overfitting.py` implements two diagnostics from
Bailey, Borwein, López de Prado and Zhu for the question "how much of
this backtest's Sharpe ratio is selection bias?".

**Deflated Sharpe Ratio (DSR)** — Bailey & López de Prado (2014), "The
Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
Overfitting and Non-Normality", *Journal of Portfolio Management*
40(5). Given an observed Sharpe ratio SR̂ estimated from T
observations, with return skewness γ₃ and excess kurtosis κ, after
selecting the best of N independent trials:

`Var[SR̂] = (1 + ½·SR̂² − γ₃·SR̂ + (κ/4)·SR̂²) / (T − 1)`

`E[max SR̂ | H₀] = √(1/(T−1)) · ((1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)))`

with γ = 0.5772 (Euler–Mascheroni), and

`DSR = Φ((SR̂ − E[max SR̂ | H₀]) / √Var[SR̂])`.

`deflated_sharpe_ratio` takes the Sharpe ratio and moments directly;
`deflated_sharpe_ratio_from_returns` estimates them from a return
series. DSR is a probability in [0, 1]: the probability that the true
Sharpe ratio is positive after deflating for selection over N trials
and for non-normality. Bailey & López de Prado suggest DSR ≥ 0.95 as
the threshold for claiming skill. The Sharpe ratio and T must use
consistent units (a per-period Sharpe with T in periods, or an
annualized Sharpe with T in years). With N = 1 there is no selection,
so E[max SR̂ | H₀] = 0.

**Probability of Backtest Overfitting (PBO)** — Bailey, Borwein, López
de Prado & Zhu (2014/2017), "The Probability of Backtest Overfitting",
*Journal of Computational Finance* 20(5).
`probability_of_backtest_overfitting` runs combinatorially symmetric
cross-validation (CSCV): split the sample into S contiguous groups (S
even); for each of the C(S, S/2) ways to choose half the groups as
in-sample, select the strategy with the best in-sample Sharpe ratio
and record its out-of-sample rank ω = rank/(N+1). PBO is the fraction
of splits with ω < 0.5. PBO near 0 means the in-sample-optimal
strategy reliably stays good out-of-sample (a persistent edge); near
0.5 is what pure noise produces; near 1 means the in-sample edge
systematically reverses out-of-sample — the signature of overfitting.
Strategy performance is the per-period Sharpe ratio computed from
group sufficient statistics, so all splits are cheap even for S = 16
(12,870 splits); above `max_combinations` a fixed-seed random subset
of distinct splits is used instead.

Neither diagnostic proves the absence of overfitting. A low PBO or a
high DSR says the observed edge survives *these* corrections; a
misspecified trial count, non-stationary returns, or a strategy set
chosen after seeing the data can still mislead. DSR assumes the N
trials are independent (or that N is the *effective* number of
independent trials) and that the normal approximation to the
distribution of SR̂ holds. PBO measures the *procedure*
(select-the-best on this data), not any single strategy.

**Applicability to this lab.** The seven completed studies are
hypothesis tests, not strategy backtests, and the cost gates keep
aggregate statistics only, so the lab has no stored strategy-return
series to feed PBO/DSR. Both methods are validated on synthetic data
with known ground truth (see `tests/test_stats_overfitting.py` and
`research/statistical-audit-2b/report.md` §4) and are ready to use
when the lab does have strategy-return series; no lab-real-data
PBO/DSR is computed or claimed.

The normal quantile function both methods need is implemented in
`src/myquant/stats/_normal.py` (Acklam's rational approximation plus
one Halley refinement step, near machine precision) because the kernel
depends only on NumPy, pandas, pydantic and pyarrow — there is no
SciPy dependency.

## 11. Calibration

`src/myquant/stats/calibration.py` checks the lab's testing procedures
against known nulls, using the synthetic factory
(`make_transmission_panel`) where it fits and direct AR(1) generation
where it does not (the factory has no autocorrelated null scenario).
Every rate is reported with its Monte Carlo standard error,
√(p(1−p)/R), so a deviation from the nominal level is judged against
simulation noise rather than eyeballed.

- `calibrate_hac_size`: empirical size of the lead-lag HAC t-test
  (`partial_lead_lag`, lag 1) on NULL panels — iid Gaussian, and AR(1)
  with φ = 0.3 — at the lab's daily sample size. The HAC p-value is
  asymptotic, so the question is whether the nominal 5% level holds
  at n ~ 1,400.
- `calibrate_bootstrap_coverage`: empirical coverage of
  `block_bootstrap_mean_ci` on series with known mean zero, iid and
  AR(1) with φ = 0.3. Block-bootstrap coverage is approximate and
  block-length sensitive; a shortfall is reported honestly.
- `calibrate_holm_fwer`: empirical family-wise error rate of Holm
  correction on families of null p-values, independent (uniform) and
  equicorrelated (Gaussian copula, ρ = 0.3). Holm controls FWER under
  arbitrary dependence, so both variants should stay at or below the
  nominal level; the correlated variant is the informative one for the
  lab, whose tests reuse the same data.

A calibration result describes the *procedure*, not any single study:
a well-calibrated procedure can still produce a false positive on one
real dataset, and a miscalibrated one does not retroactively
invalidate a study's preregistered verdict. Measured values at
audit-scale replication counts are in
`research/statistical-audit-2b/report.md` §2.

## 12. Power analysis: minimum detectable effects

`src/myquant/stats/power.py` computes the minimum detectable effect
(MDE): the smallest true effect a design can detect with a given power
(default 80%) at a given significance level (default α = 0.05). The
MDE is a property of the *design* — sample size, noise level, test
direction — not an observed conclusion. An observed effect below the
MDE means the design was underpowered for an effect of that size, not
that the effect does not exist.

All formulas use the normal approximation to the noncentral t
distribution: for a two-sided test, the required noncentrality is
λ = z_{1−α/2} + z_{power} (2.80 at α = 0.05, power 0.80); for a
one-sided test, λ = z_{1−α} + z_{power} (2.49). The approximation is
accurate at the lab's sample sizes (n ≥ 100).

- **Lead-lag OLS** (`mde_partial_r_squared`, `mde_coefficient`): for a
  single-coefficient F-test, partial R² = t²/(t² + df), so with
  t = λ and df ≈ n, MDE(R²_partial) = λ²/(λ² + n); the coefficient
  MDE is λ × SE(β̂). At n = 1,414 the partial-R² MDE is 0.0055 —
  essentially the lab's preregistered 0.005 effect-size threshold, so
  the threshold is the detection limit of the design.
- **Event-study CAR** (`mde_standardized_mean`): for a one-sample mean
  of n events, MDE = λ/√n. One-sided by default because the lab's
  primary CAR tests are one-sided (direction "less"). At n = 135 the
  one-sided MDE is 0.214.
- **Mean comparison** (`mde_cohens_d`, `mde_mean_ratio`): Cohen's d
  MDE is λ·√(1/n₁ + 1/n₂); the effect-ratio form used by the lab
  follows as 1 + λ·SE(diff)/mean_base.

`simulate_lead_lag_power` checks the analytic MDE by simulation:
panels from the factory's SOURCE_LEADS_TARGET scenario at a true
coefficient equal to the MDE should reject at about the claimed power.
At n = 1,414 the measured power at the MDE coefficient is 0.79 ± 0.03
(200 replications), confirming the normal approximation at this sample
size. The full MDE tables, juxtaposed with the observed effects of
each study, are in `research/statistical-audit-2b/report.md` §3.

## 13. Explicit non-goals in this slice

Not implemented yet:

- market-model estimation and multi-factor expected-return estimation inside the event-study function;
- event-level clustered regression, randomization inference and calendar-aware window construction.

Implemented in Stage 2B (previously listed here): PBO and Deflated Sharpe Ratio (§10), calibration (§11) and power analysis (§12); effect-size evidence records live in `research/decision-records/` (15 records, generated from the trial ledgers and the registry, drift- and ledger-verified), and the lab-wide statistical audit in `research/statistical-audit-2b/`.

No function in this kernel changes a hypothesis to SUPPORTED or REJECTED. These estimators are research diagnostics. A candidate relationship must still survive pre-registered tests, a complete multiple-testing correction, walk-forward evaluation, data-availability checks and realistic trading costs before it can be considered a potential strategy.

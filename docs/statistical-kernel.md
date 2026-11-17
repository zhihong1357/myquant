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

## 7. Multiple-testing corrections

`adjust_pvalues` preserves the original input order and provides adjusted p-values plus the decision at a predeclared threshold.

- **Bonferroni** and **Holm** target family-wise error rate (FWER).
- **Benjamini–Hochberg** targets false discovery rate (FDR) under its dependence assumptions.
- **NONE** is allowed only for a single planned test.

The function treats the supplied p-values as the complete family. It cannot know whether the caller omitted unsuccessful experiments. The experiment/hypothesis registry and study protocol must define the family before results are inspected. A search over many lags, factors, assets, model variants or bandwidths is a multiple-testing family, not one isolated test.

## 8. Explicit non-goals in this slice

Not implemented yet:

- event-study estimators and clustered event windows;
- walk-forward validation and out-of-sample incremental R-squared;
- purging and embargo for overlapping labels;
- PBO, Deflated Sharpe Ratio and power analysis;
- calibration, effect-size evidence records and statistical lifecycle decisions.

No function in this kernel changes a hypothesis to SUPPORTED or REJECTED. These estimators are research diagnostics. A candidate relationship must still survive pre-registered tests, a complete multiple-testing correction, walk-forward evaluation, data-availability checks and realistic trading costs before it can be considered a potential strategy.

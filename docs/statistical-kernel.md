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

## 10. Explicit non-goals in this slice

Not implemented yet:

- PBO, Deflated Sharpe Ratio and power analysis;
- calibration, effect-size evidence records and statistical lifecycle decisions;
- market-model estimation and multi-factor expected-return estimation inside the event-study function;
- event-level clustered regression, randomization inference and calendar-aware window construction.

No function in this kernel changes a hypothesis to SUPPORTED or REJECTED. These estimators are research diagnostics. A candidate relationship must still survive pre-registered tests, a complete multiple-testing correction, walk-forward evaluation, data-availability checks and realistic trading costs before it can be considered a potential strategy.

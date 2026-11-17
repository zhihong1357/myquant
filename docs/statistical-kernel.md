# Statistical Research Kernel — Stage 2B (initial slice)

This document describes the initial descriptive and inference primitives. They are research utilities, not proof of alpha and not trading signals.

## 1. Return and volatility estimators

- `simple_returns`: (P_t/P_{t-1}-1)
- `log_returns`: (log(P_t)-log(P_{t-1}))
- `realized_variance`: (sum_t r_t^2), with no demeaning and no annualization
- `realized_volatility`: square root of the preceding realized variance
- `annualized_volatility`: sample standard deviation with (ddof=1), multiplied by (sqrt{periods_per_year})

The two volatility measures answer different questions. The sum-of-squares realized measure accumulates variation over the supplied window; annualized volatility estimates a per-period standard deviation and annualizes it. Do not compare them as though they had identical definitions.

Return inputs use a timezone-aware, unique, ascending `DatetimeIndex`. Missing price observations are not forward-filled. A return is missing if either price in its pair is missing. The realized-variance and annualized-volatility functions reject missing returns; callers must make exclusions explicit before estimation. Corporate actions, contract rolls, stale prices and market-calendar alignment remain upstream data-contract responsibilities.

## 2. Lead-lag scan

`lead_lag_scan(source, target, lag_steps=...)` reports Pearson correlations between:

[
source_t quad 	ext{and} quad target_{t+k}
]

for each requested non-negative lag (k). Thus a positive lag means the source series is earlier than the target series by (k) observations.

Inputs must already be synchronized, equally spaced, finite observations on the same calendar. The function does not resample, interpolate, forward-fill, infer the calendar, or search an unbounded lag range. Predeclare lag candidates for confirmatory research.

This is a descriptive cross-correlation diagnostic only. It does not control common factors, test statistical significance, correct for searching many lags, or identify causality. A common driver, non-synchronous trading, stale marks or publication delays can all create apparent lead-lag structure. The synthetic common-factor scenario is included to remind us of this identification problem.

## 3. Circular block bootstrap

The initial bootstrap utilities use circular moving blocks:

1. Sample block start positions with replacement.
2. Keep observations within each sampled block in their original order.
3. Concatenate blocks and trim to the original sample length.
4. Repeat using a fixed random seed.

`block_bootstrap_mean_ci` returns a percentile interval for the sample mean. `block_bootstrap_mean_test` creates a null-centered series and calculates a two-sided finite-resample p-value using the +1 correction.

Block bootstrap is intended to preserve short-range serial dependence better than independently shuffling observations. It remains an approximation. The result can be sensitive to block length, non-stationarity, structural breaks and heavy tails. Always report block-length sensitivity and use a sample period that matches the research question. The current implementation does not provide studentized or bias-corrected intervals and should not be represented as a universal solution to time-series inference.

## 4. Multiple-testing corrections

`adjust_pvalues` preserves the original input order and provides adjusted p-values plus the decision at a predeclared threshold.

- **Bonferroni** and **Holm** target family-wise error rate (FWER).
- **Benjamini–Hochberg** targets false discovery rate (FDR) under its dependence assumptions.
- **NONE** is allowed only for a single planned test.

The function treats the supplied p-values as the complete family. It cannot know whether the caller omitted unsuccessful experiments. The experiment/hypothesis registry and study protocol must define the family before results are inspected. The correction method and target error rate must match the preregistered hypothesis.

## 5. Explicit non-goals in this slice

Not implemented yet:

- event-study estimators and clustered event windows;
- common-factor regression / partial lead-lag diagnostics;
- Newey–West HAC inference;
- walk-forward and purged/embargoed validation;
- PBO, Deflated Sharpe Ratio and power analysis;
- calibration, effect-size evidence records and statistical lifecycle decisions.

Those should be implemented as separate increments with synthetic ground-truth and null tests. No function in this slice changes a hypothesis to SUPPORTED or REJECTED.

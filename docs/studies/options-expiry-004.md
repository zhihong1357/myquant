# Options-expiry window: volatility and transmission (study 004)

- **Study:** `research/options-expiry-004/` — hypotheses **H0005 v1**
  (transmission, trial **T0005**) and **H0006 v1** (volatility level,
  trial **T0007**)
- **Verdict: H0005 REJECTED and H0006 REJECTED.** There is no evidence
  that BTC→ETH transmission strengthens inside options-expiry windows,
  and no evidence that realized volatility is higher on expiry-window
  days. All four H0005 acceptance criteria failed; both H0006 criteria
  failed. The descriptive splits agree with the nulls throughout.
- **Status:** H0005 v1 and H0006 v1 transitioned to REJECTED after
  trials T0005 and T0007. Trial **T0006** was the first H0006 attempt
  and failed inside the experiment (a bootstrap-weights bug, recorded
  as a failed trial in the ledger); the corrected rerun is T0007 (see
  "The failed T0006 attempt" below).

## Question

Options expire on Deribit on the last Friday of each month (08:00 UTC),
and the standard dealer-hedging story says market makers' hedging flows
concentrate in the days before expiry, which should show up as stronger
cross-asset transmission and higher realized volatility inside the
expiry window. Studies 001–003 found no lag-1 transmission anywhere
they looked; this study asks whether the effect is concentrated in a
specific, ex-ante known calendar window instead of being unconditional
or regime-conditional.

- **H0005 (transmission):** lag-1 BTC returns predict next-bar ETH
  returns more strongly on expiry-window days than on other days: the
  BTC[t] × window[t] interaction coefficient is positive, beyond the
  target's own history and the common-factor control, after costs and
  dependence controls.
- **H0006 (volatility level):** mean daily |log return| is higher on
  expiry-window days than on non-window days (BTC primary, ETH
  secondary), by a ratio of at least 1.15.

The expiry window is only a **proxy** for dealer-hedging intensity.
Deribit public data gives whole-market per-contract open interest and
Greeks, not dealer positions, so this study tests the expiry-window
effect itself — whether volatility and transmission differ inside the
window — and says nothing directly about dealer positions, gamma
exposure, or hedging flow. See "Mechanism: what this study does and
does not say" below.

## What is fresh here, and what is not

- **Fresh:** the conditioning variable (the options-expiry calendar,
  never used in studies 001–003), the sample (daily panel extended back
  to 2021-01-21, roughly 1.5× study 001's length), and the H0006
  volatility-level question (the first mean-comparison test in the
  lab; the graph now carries mean-comparison edges E0017/E0018
  alongside the lead-lag edges).
- **Not fresh:** the pair (BTC→ETH daily and 1H were both tested
  unconditionally in study 001 and regime-conditionally in study 002),
  the test machinery (interaction + subsample + 1H robustness, the same
  structure as study 002), and the cost gate (same sign rule, same fee
  assumption).
- **Not independent evidence:** the DVOL descriptive. Deribit's
  volatility indices are computed from the same options market whose
  expiry calendar defines the window; the DVOL profile can describe
  implied volatility around expiry but cannot corroborate the realized
  volatility test.

## Data and provenance

- **Sources:** OKX public REST (`okx-public` v1) and Deribit public
  REST (`deribit` v1), no API keys. OKX endpoints `/market/candles`
  and `/market/history-candles` for `BTC-USDT-SWAP`,
  `ETH-USDT-SWAP`, `SOL-USDT-SWAP`; Deribit `get_instruments` (listed
  and expired option contracts, for calendar verification) and
  `get_volatility_index_data` (DVOL, descriptive only).
- **Sample (OKX):** daily bars 2021-01-21 → 2026-11-16 (2,126
  confirmed bars per instrument); 1H bars 2025-01-02 → 2026-11-17
  (16,440 confirmed bars per instrument). Zero missing bars on either
  grid. The daily panel starts at SOL's first bar (2021-01-21T16:00Z);
  BTC and ETH history extends further back (confirmed bars to at least
  2020-09-23), but the synchronized three-instrument panel is bounded
  by SOL, the factor control. The last daily bar (open 2026-11-17)
  had not closed when the data was pulled (2026-11-18T04:21Z), so the
  effective sample ends 2026-11-16, two days short of the preregistered
  holdout end.
- **Sample (Deribit):** listed option instruments 958 BTC / 798 ETH
  (11 distinct expiries each, identical sets); expired listing returns
  only the most recent expired batch (70 contracts each, expiry
  2026-11-17 only) — see the calendar section. DVOL daily points
  2,065 each (2021-03-24 → 2026-11-17), no gaps; DVOL history does not
  extend to 2020.
- **Panels:** OKX daily log-return panel 2,125 rows (2021-01-22 →
  2026-11-16); OKX hourly panel 16,439 rows (2025-01-02T01:00Z →
  2026-11-17T23:00Z); DVOL log-change panel 2,064 rows (2021-03-25 →
  2026-11-17). Regression rows: 2,124 daily (the last return row has
  no next-bar target), 16,438 hourly.
- **Raw payloads and PIT parquet** live only in the local gitignored
  caches (`data/cache/options-expiry-004/`); they are not committed.
  The committed `manifest.json` records every fetch (endpoint,
  parameters, date ranges, payload SHA-256) so anyone can re-pull and
  verify the confirmed candles. As in studies 001–003, the manifest's
  own SHA-256 is not reproducible across pulls (it embeds the fetch
  timestamp); what is reproducible is the confirmed data and every
  number in this report.
  Manifest SHA-256:
  `8669abbdefa3dd37e1191a8539182cf7471f51465aec81b699320bd319c7bf9a`.
- **Quality:** 31,890 pit-1d rows, 246,600 pit-1h rows, 4,130 pit-dvol
  rows; zero quality issues in all three stores, no missing expected
  series. (The fetch ran twice — the first run failed after the OKX
  pulls on a Deribit parsing bug, fixed before the re-run — so the
  stores hold duplicate batches; the PIT store's revision resolution
  returns one value per series, and the panels are unaffected.)

## The expiry calendar

The calendar is **rule-constructed, not pulled from historical
contracts**, because Deribit's public API does not expose the full
history of expired contracts: `get_instruments` with `expired=true`
returns only the most recent expired batch (verified 2026-11-18: 70
contracts, expiry 2026-11-17 only, for both BTC and ETH). The rule is
the public Deribit rule — monthly options expire on the last Friday of
each calendar month at 08:00 UTC; quarterly options on the last Friday
of each calendar quarter at 08:00 UTC — implemented as pure functions
in `src/myquant/studies/expiry.py` (month/year boundaries covered by
tests). The sample holds **70 monthly expiries** (2021-01-29 →
2026-10-30) and **23 quarterly expiries**. The November 2026 monthly
expiry (2026-11-27) falls outside the sample.

The rule was verified against two independent sources before
preregistration, with no exceptions found:

1. **Listed contracts.** Deribit's currently listed BTC and ETH option
   expiries (fetched 2026-11-18, 11 each, identical sets) include the
   monthlies 2026-11-27, 2026-12-25, 2027-01-29 and the quarterlies
   2026-12-25, 2027-03-26, 2027-06-25, 2027-09-24 — every one falls on
   the last Friday of its month/quarter. The automated check
   (`verify_calendar_against_listed`) confirmed no monthly expiry is
   missing within the 92-day listing lead and that all four listed
   quarterlies match the constructed ones. The listing also contains
   weekly Friday expiries (e.g. 2026-11-20) and daily expiries, which
   the rule correctly excludes from the monthly calendar.
2. **Official documentation.** Deribit's Contract Introduction Policy
   (support.deribit.com, "Contract Introduction Policy", fetched
   2026-11-18) states verbatim: "Monthly options expire on the last
   Friday of each calendar month at 08:00 UTC. Quarterly options
   expire on the last Friday of each calendar quarter at 08:00 UTC."
   BTC and ETH share the same expiry dates (verified in the listed
   contracts: identical expiry sets).

Both checks are recorded in the manifest's `calendar_verification`
section (`all_checks_passed: true`). The residual risk is a historical
rule change: the rule is verified against current listings and current
documentation, not against contracts that expired years ago. Deribit
has listed monthly options on this schedule since launch, and no
exception was found in any source consulted, but a pre-2021 schedule
change cannot be ruled out from public data.

## Timestamp conventions

- OKX daily bars open at **16:00 UTC**; 1H bars open on the UTC hour.
  Deribit options settle at **08:00 UTC** on expiry day.
  `event_time` = bar open; `available_at` = bar close (open + bar
  duration); `ingested_at` = pull time. Only confirmed (OKX
  `confirm=1`) bars enter the panel; forming bars are excluded.
- **Settlement-crossing note.** Under the close-to-close convention,
  the return indexed at bar open t measures the price change over
  [t, t+24h). The T−1 bar (opens Thursday 16:00 UTC, closes Friday
  16:00 UTC) is the settlement-crossing bar: its return interval
  contains the Friday 08:00 UTC settlement. The T bar (opens Friday
  16:00 UTC) is the first full post-settlement bar. The window T−3..T
  therefore covers two full pre-settlement days (T−3, T−2), the
  settlement-crossing day (T−1), and the first post-settlement day
  (T); the T+1 bar (opens Saturday 16:00 UTC) is outside the window.
  This convention was fixed in preregistration.
- Daily windows are half-open, aligned to 16:00 UTC bar opens, each
  separated by a one-day purge gap: train [2021-01-21, 2024-01-01),
  validation [2024-01-02, 2025-01-01), holdout [2025-01-02,
  2026-11-18). The 1H window is [2025-01-02T00:00Z,
  2026-11-18T00:00Z), aligned with the daily holdout start.
- DVOL points are daily, timestamped 00:00 UTC; DVOL log-changes are
  aligned to their own index, never positionally against levels.

## Definitions and transformations

- **Returns:** close-to-close log returns, computed per instrument on
  its own series before synchronization; a return is admitted only when
  its two closes are exactly one bar apart.
- **Missing-data policy:** no forward filling; incomplete synchronized
  rows are dropped and the dropped count is reported (0 close rows
  dropped on every panel; 1 structural return row dropped per panel —
  the first, which has no prior close).
- **Expiry window (PIT-correct):** a bar is a window bar when its open
  date falls in [T−3, T] for a monthly expiry T. The calendar is public
  in advance, so the window indicator at t is known at t; no future
  information enters the feature. Window rows: 280 of 2,124 daily
  regression rows (13.2%), 188 monthly-only + 92 quarterly; 88 window
  rows among the 683 holdout test rows.
- **Wide window (descriptive only):** [T−5, T+1], 490 daily rows.
- **H0005 primary test (A):** interaction OLS of ETH[t+1] on ETH[t],
  SOL[t] (common-factor control), BTC[t] and BTC[t]×window[t],
  Newey-West HAC standard errors (max lag 5 daily, 12 hourly),
  testing the interaction coefficient. Partial R² is the nested
  comparison against the model without the interaction. (The
  specification follows the preregistration exactly: no separate
  window main effect is included, so the interaction coefficient is
  the slope difference between window and non-window days under the
  assumption of equal intercepts; daily log-return means are near zero
  in both groups, so the practical impact is small, but the
  specification choice is recorded here.)
- **H0005 subsample test (B):** partial lead-lag on expiry-window rows
  only (ETH[t+1] on ETH[t], SOL[t], BTC[t]), HAC max lag 5.
- **H0005 test family (Holm, target FWER 0.05):** (a) daily BTC→ETH
  interaction (primary), (b) daily BTC→ETH window subsample, (c) 1H
  BTC→ETH interaction. No-factor versions of each test are reported as
  upper-bound controls (not in the family).
- **H0006 tests:** OLS of daily |log return| on [1, window], Newey-West
  HAC (max lag 10 — absolute returns are more persistent than
  returns), testing the window coefficient. Effect size is the
  window/non-window mean |r| ratio, threshold 1.15 (preregistered: a
  15% volatility uplift is the smallest effect that would matter for
  the dealer-hedging story, given that expiry-week hedging is supposed
  to be a first-order flow event, not a marginal one). The
  block-bootstrap 95% CI for the mean difference (block 10, 2,000
  resamples, seed 42) is computed on the weighted series whose mean is
  the difference of means. Test family (Holm): (a) BTC (primary),
  (b) ETH. No walk-forward, no cost gate — a level comparison is not a
  forecast and has no trading rule to cost. The mean comparison uses
  all 2,125 daily rows; the train/validation/holdout splits do not
  apply to H0006.
- **Walk-forward (H0005):** purged chronological splits over the daily
  regression rows, initial train 365 rows, test windows 90 rows,
  1-day embargo, label_end = decision_time + 2 days. Base model
  excludes the interaction; augmented model includes it. The
  acceptance criterion is the incremental OOS R² on expiry-window
  holdout rows only.
- **Cost gate (H0005):** sign rule on holdout OOS augmented forecasts,
  1x, positioned on expiry-window holdout rows only and flat on
  non-window rows. Entry from flat and final exit cost one taker side
  each (0.05%); a direction flip costs a full round trip (0.10%). The
  0.05% OKX VIP0 taker fee is a labelled assumption from the public
  fee schedule, not verified for any account. Funding, slippage and
  market impact are ignored (stated limitations). The net daily edge
  is averaged over all holdout test rows, including flat non-window
  rows.
- **Descriptive splits (no p-values, not in the test family):**
  monthly-only vs quarterly windows; subperiods 2021–2022 vs
  2023–2026; wide window; DVOL levels and log-changes around expiry
  (BTC day-offset profile T−5..T+1).

## Results

### H0005 three-test family

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A daily BTC→ETH interaction, SOL control | 2,124 | −0.0358 | 0.0910 | −0.39 | 0.694 | 0.694 | 0.00008 | 0.00008 |
| A no-factor control | 2,124 | −0.0352 | 0.0912 | −0.39 | 0.700 | — | 0.00008 | 0.00008 |
| B daily BTC→ETH window subsample, SOL control | 280 | −0.1907 | 0.1200 | −1.59 | 0.112 | 0.336 | 0.00910 | 0.00905 |
| B no-factor control | 280 | −0.1618 | 0.1044 | −1.55 | 0.121 | — | 0.00671 | 0.00671 |
| C 1H BTC→ETH interaction, SOL control | 16,438 | −0.0560 | 0.0470 | −1.19 | 0.233 | 0.466 | 0.00016 | 0.00016 |
| C no-factor control | 16,438 | −0.0570 | 0.0470 | −1.21 | 0.225 | — | 0.00016 | 0.00016 |

No test in the family rejects, and every coefficient is negative — the
opposite sign from the hypothesis. The primary interaction is −0.036 ±
0.091 (Holm p = 0.694) with a partial R² of 0.00008, about 1/60th of
the 0.005 threshold. The window subsample (B) is the closest test (raw
p = 0.112), but its coefficient is negative (−0.19): within expiry
windows, lag-1 BTC is if anything *negatively* associated with next-day
ETH. Its partial R² (0.0091) clears the 0.005 threshold, but B is not
the primary test, its Holm-adjusted p (0.336) does not reject, and the
sign is wrong — it is not a finding in the hypothesis's favour. The 1H
robustness test is cleanly null. The no-factor controls agree with the
factor-controlled results throughout, so the nulls are not artefacts of
the factor control absorbing the effect.

### H0005 descriptive splits

| split | coef | partial R² | rows |
| --- | --- | --- | --- |
| Wide window (T−5..T+1) interaction | −0.0024 | 0.00000 | 490 window rows |
| Quarterly windows only | −0.1139 | 0.00020 | 92 window rows |
| Monthly-only windows | −0.0107 | 0.00001 | 188 window rows |
| Subperiod 2021–2022 | +0.0892 | 0.00058 | n = 709 |
| Subperiod 2023–2026 | −0.2174 | 0.00262 | n = 1,415 |

Coefficients and partial R² only; no p-values. The splits agree with
the null: the wide window is exactly zero, the quarterly windows (where
OI is largest and hedging flows should be strongest) point the wrong
way, and the subperiods disagree in sign (+0.09 then −0.22) with tiny
effect sizes. There is no window definition or subperiod in which the
interaction is positive and material.

### Purged walk-forward OOS (H0005)

20 folds, 0 skipped, 1,759 test rows. All-folds incremental OOS R² is
**−0.00213**; holdout-only (9 folds, 683 rows) is **−0.00067**; the
preregistered criterion — expiry-window holdout rows only (8 folds, 88
rows) — is **−0.00772** (baseline MSE 0.000870 vs augmented MSE
0.000876). Per-fold incremental OOS R²: 10 of 20 folds positive, 10
negative (best +0.0038, worst −0.0201). The interaction model forecasts
worse than the no-interaction baseline out of sample on every scoring
subset; the negative window-holdout value is the largest in magnitude,
so the window rows are where the interaction hurts most.

### Cost gate (H0005)

Sign rule on the 683 holdout OOS days (88 expiry-window days): 31
flips, gross daily edge −0.0359%, total trading cost 5.3% over the
holdout, net daily edge **−0.0437%**, block-bootstrap 95% CI [−0.120%,
+0.035%], bootstrap p = 0.275 (block length 10, 2,000 resamples, seed
42). The edge is negative before costs and more negative after them.

### H0006 two-test family

| test | n (window / non-window) | mean \|r\| window | mean \|r\| non-window | mean diff | SE | t | raw p | Holm-adj p | ratio | 95% boot CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) BTC | 2,125 (280 / 1,845) | 0.019879 | 0.019877 | +0.000001 | 0.00144 | 0.00 | 0.999 | 1.0 | 1.0001 | [−0.00474, +0.00505] |
| (b) ETH | 2,125 (280 / 1,845) | 0.025430 | 0.026518 | −0.001087 | 0.00165 | −0.66 | 0.510 | 1.0 | 0.9590 | [−0.00686, +0.00517] |

The BTC result is as null as a test can be: the window and non-window
means agree to the sixth decimal (0.019879 vs 0.019877), the mean
difference is +0.000001 with p = 0.999, the ratio is 1.0001 against a
1.15 threshold, and the window indicator's OLS R² is 4.0e-10 — it
explains nothing. The 95% block-bootstrap CI ([−0.00474, +0.00505]) is
wide, however: it includes the +0.0030 difference a 1.15 ratio would
require, so the test establishes that the point estimate is zero, not
that a moderate uplift is impossible. In ratio terms the CI spans
roughly 0.76–1.25. ETH points the other way: window volatility is
*lower* (ratio 0.959), though not significantly (p = 0.510).

### H0006 descriptive splits

| split | BTC ratio | ETH ratio |
| --- | --- | --- |
| Wide window (T−5..T+1) | 0.992 | 0.997 |
| Monthly-only windows | 1.098 | 1.065 |
| Quarterly windows | 0.813 | 0.763 |
| Subperiod 2021–2022 | 1.048 | 0.969 |
| Subperiod 2023–2026 | 0.949 | 0.941 |

Means and ratios only; no p-values. No split reaches the 1.15
threshold. The quarterly windows — the largest expiries, where the
hedging story predicts the strongest effect — show the *lowest*
volatility ratios (0.81 / 0.76), the opposite direction. The
monthly-only ratios (1.10 / 1.06) are the largest in the table but
still below threshold, and they are the complement of the quarterly
split: the overall null is not hiding a monthly effect large enough to
matter. The subperiods disagree in sign for BTC and agree in the wrong
direction for ETH.

### DVOL around expiry (descriptive only)

DVOL levels are nearly identical on window and non-window days (BTC
59.45 vs 59.29; ETH 73.41 vs 73.34, over 2,065 points each). Mean
DVOL log-changes are negative on window days (BTC −1.36%, ETH −1.10%)
and slightly positive off-window (+0.16% / +0.13%). The BTC day-offset
profile (n = 67–68 expiries per offset) shows the decline concentrated
on the expiry day itself:

| offset | t−5 | t−4 | t−3 | t−2 | t−1 | t+0 | t+1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mean BTC DVOL log-change | +1.58% | −0.24% | −0.33% | −0.64% | −1.26% | −3.17% | +0.09% |

This is a descriptive pattern with no preregistered inference: implied
volatility falls into expiry, with the largest drop on the expiry day.
That is the opposite pattern from a "volatility rises into expiry"
story and is consistent with options rolling off / vol crush after the
event, but no p-value was computed and none should be read into it.
The DVOL sample covers 68 expiries (the first two monthly expiries,
2021-01-29 and 2021-02-26, predate DVOL history, which starts
2021-03-24).

## Verdicts against the preregistered criteria

H0005 (trial T0005):

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted A p < 0.05 | 0.694 | no |
| A interaction partial R² ≥ 0.005 | 0.00008 | no |
| Window-holdout OOS incremental R² > 0 | −0.00772 | no |
| Net daily edge after costs > 0 | −0.0437%/day | no |

Zero of four criteria passed. **H0005 v1 is REJECTED.** There is no
evidence that BTC→ETH transmission strengthens inside expiry windows:
the primary interaction is null with the wrong sign, the subsample and
1H tests are null, the interaction hurts out-of-sample forecasts, and
the trading rule loses money.

H0006 (trial T0007):

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted BTC p < 0.05 | 1.0 | no |
| BTC window/non-window mean \|r\| ratio ≥ 1.15 | 1.0001 | no |

Zero of two criteria passed. **H0006 v1 is REJECTED.** Realized
volatility on expiry-window days is indistinguishable from other days
for BTC (ratio 1.0001) and lower for ETH (ratio 0.959).

## The failed T0006 attempt

The first H0006 attempt ran as trial T0006 and failed inside the
experiment, before any verdict was computed. The bug was in the
block-bootstrap interval's weights: the weighted series used weights
1/n_window and −1/n_nonwindow, so its mean was the mean difference
divided by N instead of the difference itself. The trial script's own
guard — an assertion that the bootstrap point estimate matches the OLS
coefficient — caught it (5.93e-10 vs 1.26e-06, a factor of exactly
2,125 = N) and raised. The failure is recorded in the hash-chained
ledger (T0006, status failed, record `0525941f072a…`) per the
record-every-trial rule; the trial id is therefore taken and the
corrected rerun uses T0007. The fix (weights N/n_window and
−N/n_nonwindow) was verified before the rerun by computing the weighted
mean and the direct difference of group means on the real panel and
confirming they agree to 1e-12. The bug affected only the bootstrap
interval's weights; the HAC inference and the effect ratio were
unaffected, and the guard that caught it is retained in the script.

## Mechanism: what this study does and does not say

This study tests the expiry-window *effect*, not the dealer-hedging
*mechanism*. Deribit public data gives whole-market per-contract open
interest and Greeks; it does not identify who holds what, so "dealers
are net short gamma" and "dealers hedged X contracts into expiry" are
not observable here and are not claimed anywhere in this report. The
null results are consistent with (at least) three stories that this
study cannot distinguish: dealer hedging flows are too small relative
to perpetual-market flows to move daily transmission or volatility;
hedging is spread smoothly across the month rather than concentrated in
the last four days; or the window definition misses the hedging
concentration (e.g. it happens intraday on expiry day, or in the final
hours before 08:00 UTC settlement — a daily bar cannot resolve it).
What the study does rule out is the coarse claim that expiry weeks are
systematically more volatile or more strongly transmitting at the daily
frequency. In crypto, forced buying and selling is dominated by
perpetual liquidations, open interest and funding rates; options gamma
is only an environment variable, and these results give no reason to
promote it.

## Limitations

- **The window is a calendar proxy, not a flow measure.** The study
  never observes hedging flow; a null window effect does not prove
  dealers do not hedge, only that no daily-frequency volatility or
  transmission effect coincides with the calendar window.
- **Daily resolution.** Hedging concentrated in the hours around the
  08:00 UTC settlement would be diluted inside a daily bar. The 1H
  panel tests transmission, not the volatility level, and only over
  2025–2026.
- **The calendar is rule-constructed.** It is verified against current
  listings and current documentation, not against historical expired
  contracts (which the public API does not expose). A historical rule
  change cannot be ruled out from public data.
- **No window main effect.** The preregistered interaction
  specification omits the window dummy's main effect, so the
  interaction coefficient is the slope difference between window and
  non-window days under the assumption of equal intercepts. Daily
  log-return means are near zero in both groups, so the practical
  impact is small, but the specification choice is recorded here.
- **Expiry events are scarce.** 70 monthly expiries over 5.8 years
  give 280 window rows; the window subsample test (B) has n = 280 and
  the window-holdout OOS criterion has 88 rows. The H0006 CI spans
  roughly 0.76–1.25 in ratio terms, so the design can establish that
  the point estimate is zero but cannot rule out a moderate uplift or
  decline; the verdict is "no evidence found", not "effect proven
  absent".
- **Cost model is stylized.** Funding rates (which can exceed taker
  fees), slippage and market impact are ignored; log returns proxy 1x
  P&L. All of these would make the net edge worse, not better.
- **HAC p-values are asymptotic.** With n = 2,124 (daily) and
  n = 16,438 (1H) the asymptotics are comfortable, but the p-values
  are not exact. The H0006 bootstrap CI is a percentile interval from
  2,000 resamples; block-length sensitivity was not run (the preregistered
  block length is 10).
- **The DVOL profile is descriptive.** No inference was preregistered
  for DVOL; the expiry-day decline is a pattern to note, not a finding.

## Reproducibility

- Preregistration: `research/options-expiry-004/preregister.py` →
  H0005 v1, spec fingerprint
  `5c9d73af2bd7efae02f7113c1b6f868dc5492efdb24da2d1ccd150f172f7f133`,
  registration hash
  `9727a20954de82e79fd612d96cff7c14433e959bfb595f2c6a6b8af8a85391a5`;
  H0006 v1, spec fingerprint
  `0c48d2ac4fc37be0d5ba46b530823be332040cf387a2027bb57f45f5e619845f`,
  registration hash
  `a7c631af7389cf005abdf71bd6aa6496251877842f54a20f636d375e9af27347`.
  Both registered 2026-11-18T04:09Z, before any result was computed.
- Fetch: `research/options-expiry-004/fetch_data.py` →
  `manifest.json` (SHA-256 `8669abbd…c7bf9a`, full value in the Data
  section above).
- Trials: `research/options-expiry-004/run_trial.py` → trial T0005,
  ledger record
  `644b4221b24643bdf95470bde06b26911727b9281c1de8aafcd5845008bff935`,
  code revision `ceb87a2683b216bcf6c172993bfd52d3ac9741e4`,
  config fingerprint
  `da4bac1b42530dcb8d66e611683d0dc3f5b33603c162f4b65c60929d2e74ccb6`;
  `research/options-expiry-004/run_trial_h0006.py` → trial T0007,
  ledger record
  `69d75c944b750c9b90a9b08f2f5aa7cb635e2f4bc58ad5c44b966add4f9d480d`,
  code revision `8405064d46cc7966fc3d23d4fc0902f8efed720c`,
  config fingerprint
  `afd0c64037145c220117fdcdedbb488b2f9cfb612112866a4916c811d2219f86`.
  Failed attempt T0006, ledger record `0525941f072a…` (full hash in
  the ledger).
- Re-run from the repo root (after the fetch script restores the local
  caches): `.venv/bin/python research/options-expiry-004/run_trial.py`
  and `.venv/bin/python
  research/options-expiry-004/run_trial_h0006.py`. The trials refuse
  to run twice under the same trial id; the ledger is the permanent
  record.
- Independent recomputation: every headline number in this report was
  recomputed with plain numpy (from-scratch OLS, Bartlett Newey-West,
  Holm, walk-forward fold schedule and OOS scoring, cost-gate sign
  rule) from the cached panels and matched the trial ledger to four
  decimals or better — all six H0005 test variants, all Holm
  adjustments, all three OOS scores, the full cost gate, and both
  H0006 mean comparisons. The bootstrap confidence intervals and
  bootstrap p-values were not independently recomputed (they come from
  the shared, tested block-bootstrap primitives); the H0006 CI's point
  estimate was verified algebraically against the OLS coefficient.
- Graph: study 004 edges E0014–E0018 in
  `research/graph/registry.json`, built by
  `research/graph/build_graph.py` (trial-keyed; T0006 is absent by
  design — see the builder's TRIALS comment).

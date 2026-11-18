# Macro release and auction windows: volatility and transmission (study 006)

- **Study:** `research/macro-windows-006/` — hypotheses **H0009 v1**
  (transmission, trial **T0011**) and **H0010 v1** (volatility level,
  trial **T0012**)
- **Verdict: H0009 REJECTED and H0010 SUPPORTED.** There is no evidence
  that BTC→ETH transmission strengthens inside macro release windows
  (the primary interaction is as close to zero as a test can be), but
  realized volatility is higher on macro-window days: BTC mean |log
  return| is 25% higher on window days (ratio 1.2504, Holm-adjusted
  p = 0.0098) and ETH 30% higher (ratio 1.2976, Holm-adjusted
  p = 0.0058). All four H0009 acceptance criteria failed; both H0010
  criteria passed. H0010 is the lab's first supported hypothesis.
- **Status:** H0009 v1 transitioned to REJECTED after trial T0011;
  H0010 v1 transitioned to SUPPORTED after trial T0012.

## Question

FOMC statements and CPI releases are the two macro events most
associated with volatility spikes in traditional markets, and their
schedules are public months in advance. Studies 001–004 found no
lag-1 BTC→ETH transmission anywhere they looked — unconditional,
regime-conditional, or inside options-expiry windows. This study asks
whether the effect is concentrated on macro release days instead, and
whether crypto realized volatility is higher on those days:

- **H0009 (transmission):** lag-1 BTC returns predict next-bar ETH
  returns more strongly on macro-window days than on other days: the
  BTC[t] × window[t] interaction coefficient is positive, beyond the
  target's own history and the common-factor control, after costs and
  dependence controls.
- **H0010 (volatility level):** mean daily |log return| is higher on
  macro-window days than on non-window days (BTC primary, ETH
  secondary), by a ratio of at least 1.15.

This study tests the **release-day effect**, not the **surprise
effect**: the window indicator marks days on which a release occurs,
and the release schedule is known in advance, but the release
*content* — whether the print surprised consensus — is not known at
the bar's open and is not measured anywhere here. Surprise measurement
needs consensus/actuals data, which is out of scope. Nothing in this
report claims that macro surprises transmit across crypto assets, or
that any particular release moved prices. See "Mechanism: what this
study does and does not say" below.

## What is fresh here, and what is not

- **Fresh:** the conditioning variable (the FOMC/CPI macro calendar,
  never used in studies 001–004), the Treasury auction calendar (a
  new descriptive split, built from the Fiscal Data API and
  cross-checked against TreasuryDirect), and the H0010 volatility-level
  result — the first supported hypothesis in the lab, and the first
  supported mean-comparison edges (E0030/E0031) in the market graph.
- **Not fresh:** the pair (BTC→ETH daily and 1H were tested
  unconditionally in study 001, regime-conditionally in study 002, and
  expiry-conditionally in study 004), the sample (the same OKX panels
  as study 004, identical bar counts), the test machinery (interaction
  + subsample + 1H robustness, the same structure as studies 002 and
  004), and the cost gate (same sign rule, same fee assumption).
- **Not independent evidence:** the FOMC-only and CPI-only splits are
  subsets of the same macro window, so they decompose the main result
  rather than corroborating it; the auction split uses the same price
  panel. The H0010 descriptive splits agree with the family tests
  throughout, but they are the same data viewed by subgroup.

## Data and provenance

- **Sources:** OKX public REST (`okx-public` v1), no API key;
  federalreserve.gov (`federalreserve` v1, via study 005's committed
  calendar file); BLS schedule pages (`bls` v1, text-fetch
  transcription — see the calendar section); U.S. Treasury Fiscal Data
  API (`fiscaldata` v1). OKX endpoints `/market/candles` and
  `/market/history-candles` for `BTC-USDT-SWAP`, `ETH-USDT-SWAP`,
  `SOL-USDT-SWAP`.
- **Sample (OKX):** daily bars 2021-01-21 → 2026-11-16 (2,126
  confirmed bars per instrument); 1H bars 2025-01-02 → 2026-11-17
  (16,440 confirmed bars per instrument). Zero missing bars on either
  grid — the same panels as study 004, re-pulled. The daily panel
  starts at SOL's first bar (2021-01-21T16:00Z); BTC and ETH history
  extends further back, but the synchronized three-instrument panel is
  bounded by SOL, the factor control. The last daily bar (open
  2026-11-17) had not closed when the data was pulled
  (2026-11-18T05:54Z), so the effective sample ends 2026-11-16, two
  days short of the preregistered holdout end.
- **Panels:** OKX daily log-return panel 2,125 rows (2021-01-22 →
  2026-11-16); OKX hourly panel 16,439 rows (2025-01-02T01:00Z →
  2026-11-17T23:00Z). Regression rows: 2,124 daily (the last return
  row has no next-bar target), 16,438 hourly.
- **Calendars:** 71 CPI releases (2021-01-13 → 2026-12-10), 48 FOMC
  statements in 2021–2026 (2021-01-27 → 2026-12-09), 551 distinct
  Treasury note/bond auction dates (2021-01-11 → 2026-11-12). See
  "The macro calendars" below.
- **Raw payloads and PIT parquet** live only in the local gitignored
  caches (`data/cache/macro-windows-006/`); they are not committed.
  The committed `manifest.json` records every fetch (endpoint,
  parameters, date ranges, payload SHA-256) so anyone can re-pull and
  verify the confirmed candles. As in studies 001–005, the manifest's
  own SHA-256 is not reproducible across pulls (it embeds the fetch
  timestamp); what is reproducible is the confirmed data and every
  number in this report.
  Manifest SHA-256:
  `55ea214aef7d4bf64fb9632c4fccb3d5e5f2563c5a3b65c95478ddc4bb797606`.
- **Quality:** 31,890 pit-1d rows, 246,600 pit-1h rows; zero quality
  issues in both stores, no missing expected series.

## The macro calendars

### CPI (committed: `research/macro-windows-006/cpi_calendar.json`)

The 71 CPI release dates were transcribed from the BLS Schedule of
Selected Releases annual pages (2021–2026) by text fetch. BLS returns
HTTP 403 to direct programmatic requests (including with a browser
user-agent), so the calendar is **not** structured BLS API output:
each annual page was read as text, the CPI release dates extracted,
and the result cross-checked before preregistration:

1. **Archive cross-check.** The BLS archived CPI news releases page
   lists a published release for every reference month in the calendar
   (2020-12 through 2026-11) except 2025-10, which it explicitly marks
   "Not published because of 2025 lapse in federal government
   appropriations". Annual published counts: 12 / 12 / 12 / 12 / 11 /
   10 (2026 through October; November and December 2026 release in
   December 2026 and January 2027).
2. **Second-source spot checks.** The full 2024 year (12 dates)
   matches two independent public release lists exactly; the 2025 and
   2026 early-year dates match a third; 2026-11-10 is confirmed by the
   BLS current schedule page and two further sources.
3. **Internal validation.** Dates are sorted, unique, all weekdays;
   every reference month is exactly the month before its release
   month; reference months are consecutive 2020-12 → 2026-11 except
   2025-10.

Two entries are nonstandard because of the 2025 federal shutdown
(verified against the BLS shutdown FAQ): the September 2025 CPI was
delayed from October 15 to **October 24, 2025**, and the October 2025
CPI was **never published** — no event exists for that reference
month. The December 2026 CPI releases 2027-01-13, out of sample.

### FOMC (reused: `research/fomc-event-study-005/fomc_calendar.json`)

The FOMC calendar is study 005's committed file, extracted from
federalreserve.gov pages and cross-checked there (per-year counts,
the 2003 schedule press release, the 2020 minutes page). This study
does not re-derive it; the fetch script validates that it contains
the 48 scheduled statements in 2021–2026 (8 per year) and known
dates 2021-01-27 and 2026-10-28.

### Treasury auctions (committed: `research/macro-windows-006/treasury_auction_calendar.json`)

The auction calendar is **descriptive only** and was built under the
preregistered conditional: fetch from TreasuryDirect/the Fiscal Data
API, use it only if verifiable. It verified. The Fiscal Data API
`auctions_query` dataset (v1) returned 2,487 auction records for
auction_date 2021-01-01 → 2026-11-18 (1,859 bills, 475 notes, 153
bonds); the 628 coupon (Note/Bond) records give **551 distinct
auction dates** (2021-01-11 → 2026-11-12; 94 / 94 / 93 / 93 / 94 / 83
per year). Bills are excluded: weekly cash-management auctions are
not event days.

Verification: the TreasuryDirect `auctioned` endpoint (250 most
recent auctioned securities, window 2025-05-27 → 2026-11-12) was
cross-checked against the Fiscal Data API on their overlap window
(2025-05-27 → 2026-10-22): **134 coupon dates on each side,
symmetric difference empty**. The Fiscal Data API lags the live
schedule by about four weeks (its coverage ends 2026-10-22), so the
7 most recent coupon dates (2026-10-26 → 2026-11-12) come from the
TreasuryDirect listing and are flagged as the tail supplement in the
calendar file; the exact overlap agreement is what justifies trusting
TreasuryDirect for the tail. Closing times in the API data: 536
coupon records close at 01:00 PM ET, 92 at 11:30 AM ET — the 11:30
minority's results sit near the 16:00 UTC bar boundary, a caveat
recorded in the calendar file (the auction split is descriptive, so
the impact is limited to that split).

### Window counts

The macro window is the union of the CPI and FOMC window bars:
**118 bars total** (71 CPI + 48 FOMC), with exactly **one overlap
bar, 2026-12-09** — the December 9 FOMC statement and the December
10 CPI release share one bar (the CPI window bar is the day before
its release). That bar is out of sample. **In-sample: 116 bars
(69 CPI + 47 FOMC), zero overlap** — the preregistered ~116 estimate
exactly. The wide window (event bar ±1) holds 349 bars total, 343
in-sample.

## Timestamp conventions

- OKX daily bars open at **16:00 UTC**; 1H bars open on the UTC hour.
  `event_time` = bar open; `available_at` = bar close (open + bar
  duration); `ingested_at` = pull time. Only confirmed (OKX
  `confirm=1`) bars enter the panel; forming bars are excluded.
- **The two offsets (fixed in preregistration, locked by tests).**
  Under the close-to-close convention, the return indexed at bar open
  t measures the price change over [t, t+24h). Which bar contains a
  release depends on the release's time of day in UTC:
  - **CPI** releases at 08:30 ET = 12:30 UTC (daylight saving) or
    13:30 UTC (standard time) — **always before 16:00 UTC** — so it
    falls inside the bar opened at 16:00 UTC on the **day before**
    the release date. The CPI window bar is the release date minus one
    day (e.g. the 2026-11-10 release → window bar opened 2026-11-09
    16:00 UTC).
  - **FOMC statements** release at about 14:00 ET = 18:00 UTC
    (daylight saving) or 19:00 UTC (standard time) — **always after
    16:00 UTC** — so the statement falls inside the bar opened at
    16:00 UTC on the **statement day itself**. The FOMC window bar is
    the statement date.
  - Both offsets are **DST-independent**: CPI is always before 16:00
    UTC and FOMC always after it, in both daylight saving and standard
    time. No timezone conversion is needed anywhere in the code — the
    mapping is a fixed day offset per event type, which is exactly why
    it can be locked by tests on known dates (including a DST and a
    standard-time date for each type, and the delayed 2025-10-24 CPI
    release).
  - **Treasury auction results** (descriptive only) are announced
    shortly after the 1:00 PM ET competitive close = 17:00 UTC (DST)
    or 18:00 UTC (standard), always after 16:00 UTC, so the auction
    window bar is the auction date itself — the same offset as FOMC.
- Daily windows are half-open, aligned to 16:00 UTC bar opens, each
  separated by a one-day purge gap: train [2021-01-21, 2024-01-01),
  validation [2024-01-02, 2025-01-01), holdout [2025-01-02,
  2026-11-18). The 1H window is [2025-01-02T00:00Z,
  2026-11-18T00:00Z), aligned with the daily holdout start.

## Definitions and transformations

- **Returns:** close-to-close log returns, computed per instrument on
  its own series before synchronization; a return is admitted only when
  its two closes are exactly one bar apart.
- **Missing-data policy:** no forward filling; incomplete synchronized
  rows are dropped and the dropped count is reported (0 close rows
  dropped on every panel; 1 structural return row dropped per panel —
  the first, which has no prior close).
- **Macro window (PIT-correct):** a bar is a window bar when its open
  date is a CPI window bar or an FOMC window bar (see above). The
  release schedules are public in advance, so the window indicator at
  t is known at t; no future information enters the feature. Window
  rows: 116 of 2,124 daily regression rows (5.5%), 888 of 16,438
  hourly rows (37 window days × 24 hours).
- **Wide window (descriptive only):** event bar ±1 bar, 343 daily
  regression rows.
- **H0009 primary test (A):** interaction OLS of ETH[t+1] on ETH[t],
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
- **H0009 subsample test (B):** partial lead-lag on macro-window rows
  only (ETH[t+1] on ETH[t], SOL[t], BTC[t]), HAC max lag 5.
- **H0009 test family (Holm, target FWER 0.05):** (a) daily BTC→ETH
  interaction (primary), (b) daily BTC→ETH window subsample, (c) 1H
  BTC→ETH interaction. No-factor versions of each test are reported as
  upper-bound controls (not in the family).
- **H0010 tests:** OLS of daily |log return| on [1, window], Newey-West
  HAC (max lag 10 — absolute returns are more persistent than
  returns), testing the window coefficient. Effect size is the
  window/non-window mean |r| ratio, threshold 1.15 (preregistered,
  reusing H0006's threshold: macro release days are known
  high-volatility days, and a 15% uplift is the smallest effect worth
  noticing). The block-bootstrap 95% CI for the mean difference (block
  10, 2,000 resamples, seed 42) is computed on the weighted series
  whose mean is the difference of means. Test family (Holm): (a) BTC
  (primary), (b) ETH. No walk-forward, no cost gate — a level
  comparison is not a forecast and has no trading rule to cost. The
  mean comparison uses all 2,125 daily rows; the train/validation/
  holdout splits do not apply to H0010.
- **Walk-forward (H0009):** purged chronological splits over the daily
  regression rows, initial train 365 rows, test windows 90 rows,
  1-day embargo, label_end = decision_time + 2 days. Base model
  excludes the interaction; augmented model includes it. The
  acceptance criterion is the incremental OOS R² on macro-window
  holdout rows only.
- **Cost gate (H0009):** sign rule on holdout OOS augmented forecasts,
  1x, positioned on macro-window holdout rows only and flat on
  non-window rows. Entry from flat and final exit cost one taker side
  each (0.05%); a direction flip costs a full round trip (0.10%). The
  0.05% OKX VIP0 taker fee is a labelled assumption from the public
  fee schedule, not verified for any account. Funding, slippage and
  market impact are ignored (stated limitations). The net daily edge
  is averaged over all holdout test rows, including flat non-window
  rows.
- **Descriptive splits (no p-values, not in the test family):**
  FOMC-only vs CPI-only windows; auction-day windows (verified
  calendar); subperiods 2021–2023 vs 2024–2026; wide window.

## Results

### H0009 three-test family

| test | n | coef | SE | t | raw p | Holm-adj p | partial R² | incr R² |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A daily BTC→ETH interaction, SOL control | 2,124 | +0.0003 | 0.1294 | 0.00 | 0.9982 | 1.0 | 0.00000 | 0.00000 |
| A no-factor control | 2,124 | −0.0003 | 0.1293 | −0.00 | 0.9980 | — | 0.00000 | 0.00000 |
| B daily BTC→ETH window subsample, SOL control | 116 | −0.3211 | 0.2068 | −1.55 | 0.1205 | 0.3615 | 0.02123 | 0.02099 |
| B no-factor control | 116 | −0.3155 | 0.2229 | −1.42 | 0.1568 | — | 0.02052 | 0.02032 |
| C 1H BTC→ETH interaction, SOL control | 16,438 | −0.0351 | 0.0635 | −0.55 | 0.5804 | 1.0 | 0.00003 | 0.00003 |
| C no-factor control | 16,438 | −0.0328 | 0.0639 | −0.51 | 0.6071 | — | 0.00003 | 0.00003 |

No test in the family rejects, and the primary interaction is as null
as a test can be: +0.0003 ± 0.1294 (t = 0.002, Holm p = 1.0) with a
partial R² of 3.1e-09 — about 1/1,600,000th of the 0.005 threshold.
The window subsample (B) is the closest test (raw p = 0.1205), but
its coefficient is negative (−0.32): within macro windows, lag-1 BTC
is if anything *negatively* associated with next-day ETH. Its partial
R² (0.0212) clears the 0.005 threshold, but B is not the primary test,
its Holm-adjusted p (0.3615) does not reject, and the sign is wrong —
it is not a finding in the hypothesis's favour. (Study 004's subsample
test showed the same pattern: negative coefficient, partial R² above
threshold, no rejection.) The 1H robustness test is cleanly null. The
no-factor controls agree with the factor-controlled results
throughout, so the nulls are not artefacts of the factor control
absorbing the effect.

### H0009 descriptive splits

| split | coef | partial R² | rows |
| --- | --- | --- | --- |
| Wide window (event bar ±1) interaction | −0.0269 | 0.00007 | 343 window rows |
| FOMC-only windows | +0.2198 | 0.00089 | 47 window rows |
| CPI-only windows | −0.2072 | 0.00083 | 69 window rows |
| Auction-day windows | −0.0048 | 0.00000 | 546 window rows |
| Subperiod 2021–2023 | −0.0389 | 0.00005 | n = 1,074 |
| Subperiod 2024–2026 | +0.0183 | 0.00001 | n = 1,050 |

Coefficients and partial R² only; no p-values. The splits agree with
the null, and they explain *why* the primary interaction is zero: the
FOMC-only and CPI-only interactions point in opposite directions
(+0.22 vs −0.21) with near-identical magnitudes and partial R², so
they cancel in the union. Neither half is a finding on its own — both
partial R² values are far below 0.005 and no p-value was computed —
but the cancellation is exact enough to note. The wide window, the
auction split (546 rows, coefficient −0.005) and both subperiods are
all near zero with tiny effect sizes. There is no window definition
or subperiod in which the interaction is positive and material.

### Purged walk-forward OOS (H0009)

20 folds, 0 skipped, 1,759 test rows. All-folds incremental OOS R² is
**−0.00189**; holdout-only (9 folds, 683 rows) is **−0.00073**; the
preregistered criterion — macro-window holdout rows only (8 folds, 37
rows) — is **−0.01156** (baseline MSE 0.00124485 vs augmented MSE
0.00125924). Per-fold incremental OOS R²: 9 of 20 folds positive, 11
negative (best +0.0046, worst −0.0162). The interaction model
forecasts worse than the no-interaction baseline out of sample on
every scoring subset; the negative window-holdout value is the
largest in magnitude, so the window rows are where the interaction
hurts most — the same pattern as study 004.

### Cost gate (H0009)

Sign rule on the 683 holdout OOS days (37 macro-window days): 0 flips,
gross daily edge −0.0162%, total trading cost 3.7% over the holdout,
net daily edge **−0.0217%**, block-bootstrap 95% CI [−0.088%,
+0.038%], bootstrap p = 0.488 (block length 10, 2,000 resamples, seed
42). The edge is negative before costs and more negative after them.
There were no flips because positions are sparse — 37 window days
spread over 683 holdout days, so every position enters from flat and
exits to flat rather than reversing directly; the 3.7% total cost is
74 one-sided entries/exits at 0.05%.

### H0010 two-test family

| test | n (window / non-window) | mean \|r\| window | mean \|r\| non-window | mean diff | SE | t | raw p | Holm-adj p | ratio | 95% boot CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) BTC | 2,125 (116 / 2,009) | 0.024520 | 0.019609 | +0.004911 | 0.00190 | 2.58 | 0.0098 | 0.0098 | 1.2504 | [−0.00022, +0.01036] |
| (b) ETH | 2,125 (116 / 2,009) | 0.033676 | 0.025953 | +0.007723 | 0.00259 | 2.98 | 0.0029 | 0.0058 | 1.2976 | [+0.00072, +0.01515] |

Both tests reject after Holm correction, and both ratios clear the
1.15 threshold: BTC mean |log return| is 25% higher on macro-window
days, ETH 30% higher. The window indicator's OLS R² is small (0.0028
BTC, 0.0042 ETH) — the window explains little of the total variance
of |r|, as expected for a 116-row subset — but the mean shift itself
is significant by the preregistered test.

One tension must be reported honestly: the **BTC block-bootstrap 95%
CI just includes zero** ([−0.00022, +0.01036]) while the HAC test
rejects at p = 0.0098. In ratio terms the BTC interval spans roughly
0.99–1.53: it includes no effect and it includes the 1.15 threshold.
The ETH interval excludes zero ([+0.00072, +0.01515], ratio roughly
1.03–1.58). The preregistered acceptance criteria use the HAC
p-value and the ratio, both of which pass for BTC; the bootstrap
interval is reported uncertainty, not a criterion. But the honest
read is that the BTC finding is significant by the preregistered test
and marginal by the bootstrap interval — the interval is the more
conservative statement, and it does not exclude a zero difference for
BTC. The ETH finding is significant by both.

### H0010 descriptive splits

| split | BTC ratio | ETH ratio |
| --- | --- | --- |
| Wide window (event bar ±1) | 1.243 | 1.215 |
| FOMC-only windows | 1.381 | 1.485 |
| CPI-only windows | 1.147 | 1.151 |
| Auction-day windows | 1.231 | 1.176 |
| Subperiod 2021–2023 | 1.170 | 1.252 |
| Subperiod 2024–2026 | 1.361 | 1.354 |

Means and ratios only; no p-values. Every split, for both assets,
points the same way (ratio > 1), and most clear the 1.15 threshold.
FOMC-only windows show the strongest uplift (1.38 / 1.48) and
CPI-only the weakest (1.15 / 1.15 — right at the threshold), which is
consistent with the FOMC statement being the sharper intraday event
(a single 14:00 ET release vs a data print). Auction days are also
elevated (1.23 / 1.18) on a much larger window set (546 rows). Both
subperiods agree in direction for both assets. The descriptive splits
corroborate the family tests throughout — with the standing caveat
that they are the same data viewed by subgroup, not independent
evidence.

## Verdicts against the preregistered criteria

H0009 (trial T0011):

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted A p < 0.05 | 1.0 | no |
| A interaction partial R² ≥ 0.005 | 3.1e-09 | no |
| Window-holdout OOS incremental R² > 0 | −0.01156 | no |
| Net daily edge after costs > 0 | −0.0217%/day | no |

Zero of four criteria passed. **H0009 v1 is REJECTED.** There is no
evidence that BTC→ETH transmission strengthens inside macro windows:
the primary interaction is null to the third decimal, the subsample
and 1H tests are null, the interaction hurts out-of-sample forecasts,
and the trading rule loses money.

H0010 (trial T0012):

| acceptance criterion | result | pass |
| --- | --- | --- |
| Holm-adjusted BTC p < 0.05 | 0.0098 | yes |
| BTC window/non-window mean \|r\| ratio ≥ 1.15 | 1.2504 | yes |

Two of two criteria passed. **H0010 v1 is SUPPORTED.** Realized
volatility on macro-window days is higher than on other days for both
BTC (ratio 1.2504) and ETH (ratio 1.2976), with both Holm-adjusted
p-values below 0.05 and all descriptive splits agreeing in direction.
The BTC bootstrap interval's inclusion of zero is recorded above and
in the limitations; it tempers but does not overturn the
preregistered verdict, which rests on the HAC test and the ratio.

## Mechanism: what this study does and does not say

This study tests the macro-window *effect*, not any *mechanism*. It
does not measure macro surprises (no consensus/actuals data), does
not identify who trades on release days, and does not attribute the
volatility uplift to any particular flow (institutional rebalancing,
dealer hedging, liquidation cascades, or anything else). The null
H0009 result and the supported H0010 result together say something
specific and limited: **on macro release days, crypto gets more
volatile, but the cross-asset lead-lag structure does not change.**
Volatility rises; transmission does not.

The H0010 finding is a level effect on **known event days**, not a
forecast and not a trading signal. The window is public months in
advance, so the volatility uplift is presumably priced into options
implied volatility already — this study does not test whether it is,
and the supported verdict carries no implication that the uplift is
exploitable. There is no cost gate for H0010 by design: a level
comparison has no trading rule to cost. What the result rules out is
the claim that crypto ignores the macro calendar at the daily
frequency; what it rules in is only that realized volatility is
higher on release days, by about a quarter for BTC and a third for
ETH, on this sample.

## Limitations

- **Macro events are scarce.** 116 window rows over 5.8 years; the
  window subsample test (B) has n = 116 and the window-holdout OOS
  criterion has 37 rows. The H0010 BTC bootstrap interval spans
  roughly 0.99–1.53 in ratio terms, so the design establishes the
  point estimate and the HAC rejection but cannot pin down the
  uplift's size; the verdict is "effect found by the preregistered
  test", not "effect size precisely measured".
- **The BTC bootstrap interval includes zero.** The HAC test rejects
  (p = 0.0098) while the percentile bootstrap interval just touches
  zero ([−0.00022, +0.01036]). The two intervals answer slightly
  different questions (asymptotic HAC inference vs resampled
  percentile interval), and the preregistered criteria use the HAC
  test — but a reader who trusts the bootstrap interval more would
  call the BTC finding marginal. The ETH finding is significant by
  both.
- **No window main effect.** The preregistered interaction
  specification omits the window dummy's main effect, so the
  interaction coefficient is the slope difference between window and
  non-window days under the assumption of equal intercepts. Daily
  log-return means are near zero in both groups, so the practical
  impact is small, but the specification choice is recorded here.
- **Daily resolution.** A release's market impact concentrates in
  minutes to hours around the release moment and is diluted inside a
  daily bar. The 1H panel tests transmission, not the volatility
  level, and only over 2025–2026. An hourly volatility-level test was
  not preregistered.
- **The CPI calendar is a text-fetch transcription.** BLS returns HTTP
  403 to direct programmatic requests, so the calendar was extracted
  from schedule pages by text fetch and cross-checked (archive,
  second sources, internal validation) rather than taken from a
  structured BLS API. The 2025 shutdown adds two nonstandard entries
  (September delayed, October never published); both are documented
  in the calendar file.
- **The auction calendar lags the live schedule.** The Fiscal Data
  API's coverage ends 2026-10-22; the 7 most recent coupon dates come
  from the TreasuryDirect listing, justified by the exact 134/134
  overlap agreement. 92 of 628 coupon records close at 11:30 AM ET,
  near the 16:00 UTC bar boundary. Auction days are descriptive only,
  so these caveats touch one descriptive split, not the test family.
- **Cost model is stylized.** Funding rates (which can exceed taker
  fees), slippage and market impact are ignored; log returns proxy 1x
  P&L. All of these would make the net edge worse, not better.
- **HAC p-values are asymptotic.** With n = 2,124 (daily) and
  n = 16,438 (1H) the asymptotics are comfortable, but the p-values
  are not exact. The H0010 bootstrap CIs are percentile intervals from
  2,000 resamples; block-length sensitivity was not run (the
  preregistered block length is 10).
- **The H0010 verdict is not a trading result.** No walk-forward
  evaluation and no cost gate exist for a level comparison; the
  supported hypothesis says volatility is higher on known event days,
  which is the least surprising finding the lab could produce — and
  the most useful as a baseline: any future claim that a macro-day
  strategy "works" must beat the fact that these days are simply more
  volatile.

## Reproducibility

- Preregistration: `research/macro-windows-006/preregister.py` →
  H0009 v1, spec fingerprint
  `0e1ec3d3768c5da2b044c531e624857eee53be2939ee9e8ac0adc3d3fdf0b94e`,
  registration hash
  `d19b5c4dc4b624f11af833927bde65d976c1c221afc47acf9f7e05f819b1d847`;
  H0010 v1, spec fingerprint
  `a10ddda9553151ecaff7afc57394f1cc1674ce0733b8b663d6e878872a471656`,
  registration hash
  `f50c9a250b216bd61b2defe330008489a089cc6a8965c2747433bc02252e0132`.
  Both registered 2026-11-18T05:45Z, before any result was computed.
- Fetch: `research/macro-windows-006/fetch_data.py` →
  `manifest.json` (SHA-256 `55ea214a…797606`, full value in the Data
  section above).
- Trials: `research/macro-windows-006/run_trial.py` → trial T0011,
  ledger record
  `af641748117fe8fe3077fab5bd5f56ff082e6fafd6b913b704cc5c5a9f69e186`,
  code revision `903d0ee39f44dff7eda9f4b408192f7d77b2e6fa`,
  config fingerprint
  `8a3aa1c30aabdf8b849c30160765c7e3b4f50dc95047f7d64566d8cecfe512d4`;
  `research/macro-windows-006/run_trial_h0010.py` → trial T0012,
  ledger record
  `4b0dd1cce4fbe6e15849ba3ef80355d60591afdf9f3c0913f7cea8bf2681cb8d`,
  code revision `903d0ee39f44dff7eda9f4b408192f7d77b2e6fa`,
  config fingerprint
  `be3d6ca7473aafc8d9a3ac736b06d88151159447e68a47d080260b1b1c1cf97c`.
- Re-run from the repo root (after the fetch script restores the local
  caches): `.venv/bin/python research/macro-windows-006/run_trial.py`
  and `.venv/bin/python
  research/macro-windows-006/run_trial_h0010.py`. The trials refuse
  to run twice under the same trial id; the ledger is the permanent
  record.
- Graph: study 006 edges E0027–E0031 in
  `research/graph/registry.json`, built by
  `research/graph/build_graph.py` (trial-keyed).

### Independent recomputation

Before delivery, the headline daily numbers were recomputed
independently with plain numpy from freshly re-pulled OKX candles,
without using any repo code: 2,126 confirmed daily bars per
instrument, 2,125 return rows, and a macro window rebuilt from the
committed calendars (116 in-sample window bars: 69 CPI + 47 FOMC,
zero overlap; the only overlapping bar, 2026-12-09, is out of
sample). The recomputation reproduced the ledger exactly: the H0009
primary interaction (+0.0003 ± 0.1294, p = 0.9982, partial R² =
3.1e-09), the window subsample (−0.3211 ± 0.2068, p = 0.1205), the
FOMC-only (+0.2198) and CPI-only (−0.2072) interaction splits, and
the H0010 mean comparisons (BTC ratio 1.2504, Holm p = 0.0098; ETH
ratio 1.2976, Holm p = 0.0058), all to four decimals. The 1H
interaction, walk-forward OOS and cost-gate figures were not
recomputed independently.

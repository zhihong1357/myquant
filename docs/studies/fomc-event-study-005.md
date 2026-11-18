# FOMC event study: rates-credit-equity-options (study 005)

- **Study:** `research/fomc-event-study-005/` — hypotheses **H0007 v1**
  (trial **T0010**) and **H0008 v1** (trial **T0009**). Trial T0008, the
  first H0007 attempt, failed inside the experiment on an over-strict
  cycle-boundary guard before any results were computed; see
  [Reproducibility](#reproducibility).
- **Verdict H0007: REJECTED.** No evidence that scheduled FOMC statements
  produce a significant VIX cumulative abnormal return in the [0,+1]
  event window: the raw one-sided p-value is 0.040 but the Holm-adjusted
  p-value is 0.160 and the standardized mean CAR is −0.15, half the
  preregistered −0.3 threshold. Both acceptance criteria failed.
- **Verdict H0008: REJECTED.** No evidence that SPX event-window CARs are
  negatively related to DGS10 event-window CARs across FOMC events: the
  slope is positive (+0.000117, wrong sign), R² is 0.0057, and the
  split-half replication failed. All three acceptance criteria failed.
- **Status:** hypotheses H0007 v1 and H0008 v1 transitioned to REJECTED
  after trials T0010 and T0009.

Two secondary tests did reject within their Holm families — the TYVIX
CAR is strongly negative and the BAA10Y CAR is significantly related to
the DGS10 CAR — but neither rescues its hypothesis: the acceptance
criteria are on the primary tests only, and the BAA10Y result is partly
mechanical (the spread contains the 10-year yield by definition; see
[Results](#results)).

## Question

**H0007 (event response).** Do scheduled FOMC statement days produce
significant cumulative abnormal returns in the [0,+1] event window
across the rates (DGS10), credit (BAA10Y spread), equity (SPX) and
volatility (VIX, TYVIX) legs?

- **H0:** Mean CAR[0,+1] around scheduled FOMC statement days is zero on
  every leg; announcement days are indistinguishable from ordinary days
  after the constant-mean benchmark.
- **H1:** Mean CAR[0,+1] is negative for VIX (primary) and TYVIX and
  non-zero for SPX, DGS10 and BAA10Y, with the VIX standardized mean CAR
  at or below −0.3. The volatility-drop prior: scheduled announcements
  resolve policy uncertainty, so implied volatility should fall after
  the statement.

**H0008 (cross-event transmission).** Across FOMC events, is the SPX
event-window CAR negatively related to the DGS10 event-window CAR (a
rates-up move coinciding with equities down)?

- **H0:** The target leg's CAR is unrelated to the DGS10 CAR across
  events (zero slope).
- **H1:** The SPX CAR on DGS10 CAR slope is negative (primary), with
  R² ≥ 0.05 and split-half replication.

This is the roadmap's "Rates-credit-equity-options event studies" item
and the first real-data use of the repo's event-study CAR estimator.
It reuses study 003's FRED + Yahoo panel and data-source findings.

## The FOMC calendar: sourcing and verification

The event list is extracted from the Fed's own pages, not
rule-constructed. The fetch script pulls the 18 per-year historical
pages `fomchistorical{YYYY}.htm` (2003–2020) and the calendar page
`fomccalendars.htm` (2021 onwards), parses them with
`src/myquant/studies/fomc.py`, and verifies the result before any
analysis. All checks passed at fetch time (2026-11-18).

**Parsing.** Historical pages list one `<h5>` heading per entry:
`"January 29-30 Meeting - 2008"`, `"March 10 Conference Call - 2008"`,
`"March 17-18 (cancelled) Meeting - 2020"`, `"August 27 (notation vote)
- 2020"`, `"March 2 (unscheduled) Meeting - 2020"`. Classification comes
from the heading text: plain "Meeting" is scheduled; conference call,
(unscheduled), (cancelled) and (notation vote) are excluded. Three
format variants needed handling: cross-month meetings spelled
`"April/May 30-1"` (2013, 2017, 2018, 2019, sometimes with abbreviated
months) or `"July 31-August 1"` (2012), and unscheduled entries with no
"Meeting" word (`"October 16 (unscheduled) - 2013"`). The calendar page
uses month/date divs; cross-month labels (`"Apr/May"`, dates `"30-1"`),
SEP markers (trailing `*`, stripped) and notation-vote rows are handled.
The September 2003 meeting is listed as two one-day headings
("September 15 Meeting", "September 16 Meeting") and merged into one
two-day meeting with statement day September 16, matching the 2003
schedule press release.

**Verification (all checks passed, enforced by the fetch script).**

1. **Annual counts:** 8 scheduled meetings per year, 7 in 2020 (the
   March 17-18 meeting was cancelled; the Committee acted at unscheduled
   meetings instead). 2003–2027 totals 199 scheduled meetings.
2. **2003 schedule press release** (second source): reproduces all eight
   2003 statement days exactly.
3. **2020 minutes publication page** (second source): reproduces the
   seven scheduled 2020 meetings plus the unscheduled March 15 meeting
   (which replaced the cancelled March 17-18 meeting). The March 2
   unscheduled meeting has no separate minutes entry on that page.
4. **Known-date spot checks:** 2003-09-16, 2008-12-16 and 2020-12-16 are
   scheduled; the emergency action dates 2008-01-22, 2008-03-16,
   2008-10-08, 2020-03-03 and 2020-03-15 are not.

**Excluded meetings (31, all recorded in `fomc_calendar.json`).**

- **Conference calls (20):** 2003-03-25, 2003-04-01, 2003-04-08,
  2003-04-16, 2007-08-10, 2007-08-16, 2007-12-06, 2008-01-09,
  2008-01-21, 2008-03-10, 2008-07-24, 2008-09-29, 2008-10-07,
  2009-01-16, 2009-02-07, 2009-06-03, 2010-05-09, 2010-10-15,
  2011-08-01, 2011-11-28. The 2008 emergency rate actions were decided
  on conference calls (Jan 21, Mar 10, Oct 7); their announcement dates
  (Jan 22, Mar 16, Oct 8) never enter the scheduled list.
- **Unscheduled meetings (5):** 2013-10-16, 2014-03-04, 2019-10-04,
  2020-03-02, 2020-03-15.
- **Cancelled (1):** 2020-03-17–18.
- **Notation votes (5):** 2020-03-19, 2020-03-23, 2020-03-31,
  2020-08-27, 2025-08-22.

Minutes releases are not events in this study. The residual risk is a
parsing error in a year whose page format was not spot-checked; the
per-year count checks and the two second-source cross-checks bound that
risk, and every heading shape found across 2003–2020 is covered by
offline tests.

## Data and provenance

- **Sources:** FRED free fredgraph CSV (`fred` v1, no API key) for
  VIXCLS (VIX), VXTYN (TYVIX), DGS10 (10-year Treasury yield) and
  BAA10Y (Baa minus 10-year Treasury spread); Yahoo Finance public chart
  endpoint (`yahoo-finance` v1, no key) for the S&P 500 index (`^GSPC`,
  meta longName verified as "S&P 500" at fetch time). The FOMC calendar
  comes from federalreserve.gov (`federalreserve` v1, public schedule
  data). No new FRED series is introduced: the series combination is
  study 003's, already verified.
- **Sample:** daily closes 2003-01-02 → 2026-11-16. Rows fetched per
  series: VIXCLS 6,041; VXTYN 4,363 (ends 2020-05-15, discontinued);
  DGS10 5,972; BAA10Y 5,967; ^GSPC 6,007.
- **Missing values:** FRED fredgraph CSVs carry one row per weekday, with
  an **empty** value field on market holidays — not `"."` as FRED's API
  documentation suggests (verified in study 003; the adapter treats both
  as missing). Empty-value counts over the window: VIXCLS 187, VXTYN
  169, DGS10 256, BAA10Y 261. Yahoo ^GSPC had 0 null closes. Missing rows
  are excluded at fetch time and counted; no forward filling anywhere.
- **Panels:** main panel (five legs through the TYVIX coverage end)
  **4,330 return rows** (2003-01-03 → 2020-05-15), 51 dropped close rows
  and 52 dropped return rows; extended panel (four non-TYVIX legs)
  **5,959 return rows** (2003-01-03 → 2026-11-16), 90 dropped close rows
  and 91 dropped return rows. Dropped rows are partial holidays where
  some series trade and others do not (e.g., bond holidays when equities
  trade). Full market holidays appear in no series and never enter the
  panel.
- **Raw payloads and PIT parquet** live only in the local gitignored
  cache (`data/cache/fomc-event-study-005/`); they are not committed.
  The committed `manifest.json` records every fetch (endpoint,
  parameters, date ranges, payload SHA-256) and the calendar
  verification. Note the manifest's own SHA-256 is not reproducible
  across pulls: it embeds the fetch timestamp, and record hashes embed
  ingestion time. What is reproducible is the fetched data and every
  number in this report.
  Manifest SHA-256: `62a6275d2ef5a00d552885ca4c0ccc35b5797b9ee0af2b14ebca32cc4d7d457f`.
- **Quality:** 28,350 observation rows across 5 series, no quality
  issues, no missing expected series.
- **TYVIX substitution (from study 003, stated limitation).** TYVIX
  measures expected 30-day volatility of 10-year Treasury futures
  *prices*; the MOVE index measures Treasury *yield* volatility. TYVIX
  is the closest free substitute but the substitution is approximate,
  and TYVIX was discontinued in May 2020, so the main sample excludes
  the post-2020 rate-hiking cycle.

## Timestamp conventions

- FRED daily values are closing values dated `observation_date`; Yahoo
  daily bars carry the trading date derived in America/New_York. Both
  are recorded at a shared event time of **21:00 UTC** (16:00 ET close,
  fixed; DST is not modelled), with `available_at` equal to the event
  time.
- **FOMC statement timing (fixed in preregistration):** the statement is
  released at about 14:00 ET on the last meeting day, and the daily
  close (16:00 ET) already contains the reaction. t=0 is the statement
  day; the event window [0,+1] is the statement day plus the next
  trading day. The window was not shifted after seeing results.
- **FRED publication lag is not modelled** (stated limitation): values
  are posted after the close, sometimes the next morning, so
  `available_at` is optimistic by up to a day. For an event study this
  matters less than for a forecast — the analysis is retrospective — but
  the CARs are not executable at the recorded times.
- Daily windows are half-open, aligned to 21:00 UTC closes, each
  separated by a two-day purge gap: train [2003-01-02, 2012-01-01),
  validation [2012-01-03, 2017-01-01), holdout [2017-01-03, 2020-05-15).
  The windows exist for registry compatibility; the event study uses the
  full main sample, not the splits.
- All five series share one PIT store (`pit-1d/`): every series is daily
  at 21:00 UTC, so no cross-frequency collision of the kind study 001
  found between daily and hourly stores can occur.

## Definitions and transformations

- **Events:** scheduled FOMC meetings only; t=0 is the statement day
  (the last meeting day). Main sample: 138 scheduled statements from
  2003-01-29 to 2020-04-29. **135 events are included**; 3 are excluded
  and counted: 2003-01-29 and 2003-03-18 (the estimation window
  [-60,-11] extends before the panel start) and **2004-11-10** (t=0 is
  absent from the panel — see below). First included event 2003-05-06,
  last 2020-04-29.
- **The 2004-11-10 exclusion.** The FRED VXTYN series has a genuine
  two-day gap on 2004-11-10 and 2004-11-11 (verified against a fresh
  FRED pull: both days are empty in the source CSV, while DGS10 has a
  value on Nov 10; Nov 11 is Veterans Day, but Nov 10 is an unexplained
  single-day gap in TYVIX). With no forward filling, the Nov 10, 2004
  statement day is absent from the synchronized panel and the event is
  excluded per the preregistered missing-data policy.
- **Estimation window** [-60,-11] (50 trading days); **main event
  window** [0,+1]; **descriptive wide window** [-1,+1] (predeclared, not
  in either family). **Expected return** is the constant-mean benchmark:
  each event's expected change is the mean observed change over its own
  estimation window, estimated separately per event and per leg. The
  constant-mean benchmark is the standard choice for short windows; a
  market model would add estimation noise without a clear benefit over
  two days.
- **Transforms (preregistered):** VIX, TYVIX and SPX use log changes;
  DGS10 and BAA10Y use level changes in basis points. Both are computed
  **diff-then-join**: each series is differenced on its own dates before
  alignment to the panel's return index (study 003's lesson —
  join-then-diff corrupts a leg's one-day change after a partial holiday
  in another leg). The rate-leg changes use the new
  `level_changes_on_index` helper in `src/myquant/studies/panel.py`.
- **Estimator:** the repo's `event_study()` (`src/myquant/stats/
  event_study.py`), with the constant-mean expected series supplied per
  event (`src/myquant/studies/event_windows.py`). Scheduled meetings are
  at least four weeks apart, so [0,+1] windows never overlap: every
  event is its own cluster (135 events, 135 clusters in every family
  test), and the overlap-clustering inference is formal only. Inference
  is the cluster-based normal reference: SE = cross-event CAR standard
  deviation / √n.
- **One-sided p-values** for the volatility legs (H0007) and the primary
  cross-section slope (H0008) are derived from the z/t-statistic as
  Φ(z) for the "less than" direction, as preregistered. **Effect size**
  for H0007 is the standardized mean CAR (mean CAR divided by the
  cross-event standard deviation of CARs); the 0.3 threshold is a
  small-to-medium standardized effect — with ~135 events the standard
  error of the standardized mean is about 1/√135 ≈ 0.086, so 0.3 is
  about 3.5 standard errors.
- **Cross-section (H0008):** one observation per event; target-leg CAR
  regressed on DGS10 CAR with an intercept, heteroskedasticity-consistent
  HC0 standard errors via the repo's Newey-West estimator at max_lag=0.
  **Split-half replication:** events ordered chronologically, first half
  = first floor(n/2) = 67 events, second half = 68; replication requires
  both halves' slopes negative with one-sided HC0 p < 0.05.
- **Policy-cycle splits (descriptive, no p-values):** hiking
  2004-06-30:2006-06-29 and 2015-12-17:2018-12-19; cutting
  2007-09-18:2008-12-16 and 2019-07-31:2020-03-15; all other event dates
  unchanged. **Known transcription error (disclosed):** the second
  hiking range starts 2015-12-17, but the December 2015 meeting was
  December 15-16, so the inaugural hike meeting (2015-12-16) falls in
  the "unchanged" bucket. The ranges are executed exactly as
  preregistered — the preregistration is immutable, and the registry
  forbids amending a hypothesis once testing has started. The split is
  descriptive only, so no verdict is affected; the error moves one
  event of 135 between buckets.
- **Policy-surprise proxy (red line).** The DGS10 event-window move is
  only a proxy for the policy surprise, not the surprise itself: no free
  federal funds futures surprise series exists (a Kuttner-style surprise
  needs futures data). H0008 tests the cross-sectional association
  between the rates leg and the other legs, not a causal "surprise
  effect". Nothing in this report claims to measure the policy surprise.
- **No walk-forward, no cost gate.** An event study measures
  announcement responses, not a forecast; there is no trading rule to
  cost. A significant CAR is not tradable alpha, and this report does
  not present one as such.

## Results

### H0007 — event response (trial T0010)

The preregistered five-test Holm family on the main window [0,+1],
n = 135 events, 135 clusters:

| test | leg | mean CAR | SE | z | raw p | Holm p | std. mean CAR | reject |
|---|---|---|---|---|---|---|---|---|
| vix_car (primary, one-sided < 0) | VIX (log pts) | −0.015517 | 0.008863 | −1.7508 | 0.03999 | 0.1600 | −0.1507 | no |
| spx_car (two-sided) | SPX (log pts) | +0.000669 | 0.001407 | +0.4757 | 0.6343 | 1.0 | +0.0409 | no |
| dgs10_car (two-sided) | DGS10 (bp) | −0.949926 | 0.906095 | −1.0484 | 0.2945 | 0.8834 | −0.0902 | no |
| baa10y_car (two-sided) | BAA10Y (bp) | +0.271704 | 0.508069 | +0.5348 | 0.5928 | 1.0 | +0.0460 | no |
| tyvix_car (one-sided < 0) | TYVIX (log pts) | −0.038112 | 0.006793 | −5.6108 | 1.007e-08 | 5.036e-08 | −0.4829 | **yes** |

The primary VIX result is in the expected direction and nominally
significant (raw one-sided p = 0.040), but it does not survive the
preregistered multiplicity control (Holm p = 0.160) and the effect is
small (standardized −0.15, half the −0.3 threshold). SPX, DGS10 and
BAA10Y are clean nulls. The TYVIX leg is the exception: rates implied
volatility falls sharply after FOMC statements (mean CAR −3.8 log
points over two days, standardized −0.48), and the rejection survives
Holm comfortably. The volatility-drop story holds for rates volatility
but not convincingly for equity volatility in this sample — a
divergence between the two volatility legs, not a rescue of H0007.

### H0008 — cross-event transmission (trial T0009)

The preregistered three-test Holm family of cross-event OLS (target CAR
on DGS10 CAR, HC0 standard errors), n = 135 events:

| test | slope | SE | t | raw p | Holm p | R² | reject |
|---|---|---|---|---|---|---|---|
| spx_on_dgs10 (primary, one-sided < 0) | +0.000117 | 0.000195 | +0.6015 | 0.7262 | 0.7262 | 0.0057 | no |
| vix_on_dgs10 (two-sided) | −0.001232 | 0.000955 | −1.2910 | 0.1967 | 0.3934 | 0.0159 | no |
| baa10y_on_dgs10 (two-sided) | −0.284260 | 0.075573 | −3.7614 | 0.000169 | 0.000507 | 0.2570 | **yes** |

The primary slope is positive — the wrong sign for the hypothesis — with
R² = 0.0057. The split-half replication failed outright: first half
(67 events) slope +0.000045 (one-sided p = 0.579, R² = 0.0009), second
half (68 events) slope +0.000316 (one-sided p = 0.850, R² = 0.0338);
both halves are positive. There is no rates→equity transmission in the
event window in this sample, in either half.

The BAA10Y slope rejects strongly, but it must be read with its
definitional caveat: **BAA10Y is the BAA corporate yield minus the
10-year Treasury yield (DGS10)**, so the BAA10Y CAR contains −DGS10 CAR
by construction. The slope of −0.284 is (β_BAA − 1), where β_BAA is the
slope of BAA yield changes on DGS10 changes: it says BAA yields move
about 72% as much as Treasury yields around FOMC statements. The
rejection means corporate yields under-react relative to Treasuries in
the event window — a statement about relative repricing, not a clean
"rates surprise moves credit spreads" transmission result — and the
R² = 0.257 is inflated by the shared DGS10 component. The report does
not claim a transmission channel from this test alone.

Per-event CAR dispersion (main window, n = 135): DGS10 CARs range
−43.92 to +34.20 bp (std 10.53 bp); SPX CARs −0.0588 to +0.0579 (std
0.0163); VIX CARs −0.3339 to +0.3294 (std 0.1030); BAA10Y CARs −17.12
to +26.72 bp (std 5.90 bp). Event-window moves are large in both
directions; the nulls are nulls of the *average* response, not of
event-day volatility.

### Descriptives (not in the test families)

**Wide window [-1,+1] (main sample, n = 135).** The pattern matches the
main window: TYVIX CAR −0.034707 (z = −4.57, one-sided p = 2.49e-06,
std −0.39) stays strongly negative; VIX CAR −0.014555 (p = 0.086,
std −0.12) weakens slightly; DGS10 −1.684 bp (p = 0.104); SPX and
BAA10Y null. Cross-section: BAA10Y slope −0.394 (p = 1.42e-05,
R² = 0.367); SPX slope +0.000444 (one-sided p = 0.934, wrong sign);
VIX slope −0.002572 (two-sided p = 0.0128, R² = 0.063) — nominally
significant in the descriptive window only, while the main-window VIX
test is null (p = 0.197); reported as descriptive, no claim made.

**Extended sample (four legs, 2003–2026, n = 188 events).** VIX CAR
−0.011899 (one-sided p = 0.069, std −0.108); DGS10 −1.407 bp (p = 0.064,
std −0.135); SPX +0.000027 (p = 0.983); BAA10Y +0.316 bp (p = 0.466).
Cross-section: BAA10Y slope −0.293 (p = 9.64e-07, R² = 0.263); SPX
slope +0.000024 (p = 0.559, R² = 0.0002); VIX slope −0.000847
(p = 0.345). The extended sample — which includes the post-2020 hiking
cycle the main sample lacks — tells the same story: no equity
transmission, a weak VIX drop, a persistent BAA10Y association. Eleven
statements are excluded from the extended sample: the two early-2003
estimation-window exclusions, the December 2026 meeting (beyond the
panel end 2026-11-16) and the eight 2027 meetings.

**Policy-cycle splits (main window, no p-values).** Mean CAR /
standardized mean CAR by cycle:

| cycle | events | VIX | TYVIX | SPX | DGS10 (bp) | BAA10Y (bp) |
|---|---|---|---|---|---|---|
| cutting | 16 | −0.0294 / −0.22 | −0.0512 / −0.56 | +0.0066 / +0.26 | −3.640 / −0.35 | −0.965 / −0.12 |
| hiking | 40 | −0.0129 / −0.14 | −0.0348 / −0.68 | −0.0023 / −0.23 | −1.761 / −0.29 | +0.256 / +0.07 |
| unchanged | 79 | −0.0140 / −0.14 | −0.0372 / −0.42 | +0.0010 / +0.06 | +0.006 / +0.00 | +0.530 / +0.08 |

The TYVIX drop is present in all three cycles (standardized −0.42 to
−0.68); the VIX drop is modest everywhere (−0.14 to −0.22). The DGS10
response is negative in hiking and cutting cycles but exactly zero on
average in unchanged periods (+0.006 bp) — sensible, since no policy
change means no systematic rates repricing. The December 2015 meeting
sits in the "unchanged" bucket because of the disclosed boundary typo;
moving it would not change any of these readings materially (one event
of 79 in that bucket).

## Verdicts against the preregistered criteria

**H0007 (trial T0010): REJECTED.** Both criteria failed: the
Holm-adjusted primary p-value is 0.160 (criterion: < 0.05) and the
primary standardized mean CAR is −0.151 (criterion: ≤ −0.3). The
nominally significant raw p-value (0.040) does not meet the
preregistered standard, which is the Holm-adjusted p-value and the
effect-size threshold jointly.

**H0008 (trial T0009): REJECTED.** All three criteria failed: the
Holm-adjusted primary p-value is 0.726 (criterion: < 0.05), the primary
R² is 0.0057 (criterion: ≥ 0.05), and the split-half replication failed
(criterion: both halves negative and significant; both halves are
positive).

## Limitations

- **The main sample ends 2020-05-15** (TYVIX discontinued) and excludes
  the post-2020 hiking cycle. The extended-sample descriptives cover
  2003–2026 for the four non-TYVIX legs and agree with the main results,
  but the TYVIX finding is a 2003–2020 statement only.
- **DGS10 is a proxy for the policy surprise, not the surprise itself.**
  Without fed funds futures data, H0008 cannot separate a genuine
  surprise effect from the correlation between the rates move and
  whatever else moved equities that day. A null here does not rule out
  transmission of true policy surprises.
- **The BAA10Y cross-section test shares its regressor by definition**
  (BAA10Y = BAA yield − DGS10). Its slope and R² are not comparable to
  a clean two-asset transmission test; see [Results](#results).
- **The constant-mean benchmark** assumes each event's expected change
  is its own 50-day mean. Estimation windows may contain a prior
  meeting's event window (2 of 50 days when meetings are five weeks
  apart); the contamination is small and the simple [-60,-11] rule was
  kept as preregistered.
- **The cycle-boundary transcription error** (2015-12-17 instead of
  2015-12-16) puts the December 2015 meeting in the "unchanged"
  descriptive bucket. Disclosed above; descriptive only.
- **A significant CAR is not tradable alpha.** The event study measures
  announcement responses on realized data; it does not produce a
  forecast, a signal, or a costed trading rule.
- **FRED publication lag is not modelled** (see [Timestamp
  conventions](#timestamp-conventions)).
- **Single central bank, single sample.** 135 events from one
  institution's scheduled meetings; the results speak to FOMC
  announcements in 2003–2020, not to central-bank announcements in
  general.

## Reproducibility

- **Preregistration:** H0007 v1 spec fingerprint
  `c9a278bf137182d5491a5e496c1e5533b92c56d4b2067194d117dad7c7d30782`,
  H0008 v1 spec fingerprint
  `f76d5b6075672990d3462715e48a9109d062c99fa837bd4d03ef7d9daec7582b`
  (`research/fomc-event-study-005/preregister.py`, run before any
  result-level analysis).
- **Trials:** T0010 record
  `4942fb6135ac364d57cee042518dd81cfb8680126ffe54a9c9a0b9898d042f56`,
  T0009 record
  `c82c6182f15f4177c43fc4265c699864fb5e305484dcb93cb7d28f96645324af`
  (hash-chained ledger `research/fomc-event-study-005/trials.jsonl`).
  Trial T0008 (the first H0007 attempt, record
  `d685bb2142b5d1d07a7d0e673eeac3848e04721c59af43913d47b268eb62929e`)
  failed inside the experiment on the over-strict cycle-boundary guard
  described above; no T0008 results were computed or recorded, and the
  corrected trial re-ran as T0010 (trial IDs are unique per attempt).
- **Code:** fetch `research/fomc-event-study-005/fetch_data.py`;
  calendar parser `src/myquant/studies/fomc.py`; event-study helpers
  `src/myquant/studies/event_windows.py`; level changes
  `src/myquant/studies/panel.py` (`level_changes_on_index`); estimator
  `src/myquant/stats/event_study.py`; trials
  `research/fomc-event-study-005/run_trial.py` (T0010) and
  `run_trial_h0008.py` (T0009).
- **Independent recompute:** all headline numbers (all five T0010
  event-study tests and both reported T0009 cross-section slopes, with
  standard errors, z/t-statistics, p-values, R² and standardized
  effects) were recomputed with plain numpy from freshly re-fetched
  FRED + Yahoo data, outside the repo's code, and match the ledgers to
  four decimals. The recompute script is not committed (verification
  only).
- **Manifest:** `research/fomc-event-study-005/manifest.json`, SHA-256
  `62a6275d2ef5a00d552885ca4c0ccc35b5797b9ee0af2b14ebca32cc4d7d457f`
  (see the note in [Data and provenance](#data-and-provenance) on what
  the manifest hash does and does not reproduce).

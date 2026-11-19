# Research intelligence (Stage 6)

Stage 6 turns the lab's own records — the market graph, the
decision records, the power audit — into tools that help run the
lab: planning what to test next, checking sources, assisting
experiments, reviewing claims adversarially, and keeping the
research library. Everything in this layer reads the lab's records
and writes drafts, rankings or reviews. Nothing here registers a
hypothesis, runs a trial, changes the registry, or generates a
trading signal.

## 1. Hypothesis planner (6a)

`src/myquant/planner/` ranks the graph's untested candidate pairs
by explicit, auditable criteria and drafts preregistrations for
the shortlist. Validation: `research/planner-6a/validate_planner.py`
(offline, deterministic), report in
`research/planner-6a/validation_report.md`, full ranking in
`research/planner-6a/ranking.json`, top-10 drafts in
`research/planner-6a/templates/`.

### What the planner is (and is not)

The planner sorts. It does not predict which hypothesis will be
supported, and it does not judge whether a pair is economically
plausible. "Adjacent to a supported edge" is a graph fact;
"therefore likely to be supported" is a forbidden inference, and
the planner never makes it. The ranking is a heuristic: the
validation report shows the tie structure that dominates the
top-10 and how the shortlist moves (or does not move) under other
weights.

### Inputs

- `research/graph/registry.json` — nodes, tested edges, untested
  candidates. Loaded through the strict `MarketGraph` validation
  (content hash and all); the planner never writes to it.
- `research/decision-records/records/DR-E*.json` — supported-edge
  decision records, mapped edge id -> record id so the shortlist
  cites the evidence behind each adjacent supported edge.
- `research/statistical-audit-2b/summary.json` — the Stage 2B
  audit's MDE table. The planner recomputes every audit MDE entry
  from its sample size with the same analytic formulas and
  cross-checks before scoring (15/15 match).
- `research/fomc-event-study-005/fomc_calendar.json` — scheduled
  FOMC statement dates, for cross-section event counts.
- `research/planner-6a/data_availability.json` — one verified
  panel record per graph node, hand-written from the studies'
  manifests with a `verified_by` citation per node. A node with no
  record is *unknown* (never assumed available); a record may also
  state that a panel is *unavailable* (verified: no usable panel).

### Scoring

Each component scores 0–1; the total is the weighted sum (default
weights adjacency 0.4 / data 0.3 / power 0.3 — see "Weights"
below). Ties break by (source, target) lexicographic order, so
identical inputs always produce identical output.

**Adjacency.** 1.0 when the candidate shares a node with a
SUPPORTED edge; 0.5 when it shares a node one hop away (connected
to a supported-edge node by any tested edge); 0 otherwise. Only
SUPPORTED edges define tier 1, and only tested edges (supported
or rejected) define adjacency — DESCRIPTIVE and PENDING edges do
not count. The tier values are parameters
(`PlannerConfig.adjacency_tier_direct` /
`adjacency_tier_one_hop`, defaults 1.0 / 0.5), not hard-coded
constants. The tiers are a heuristic ordering device: sharing a
node with a supported edge says nothing about whether the
candidate pair will be supported.

**Data availability.** 1.0 when both endpoints have verified
panels, 0.5 when one endpoint's panel is verified unavailable
(half the pair is ready; the missing side needs a fetch, not a
redesign), 0 when both are. A node with no availability record is
unknown: its candidates go to the unrankable list with the reason,
never into the ranking on assumed data.

**Power feasibility.** 1 when the design's MDE at the available
sample size is below the lab threshold for the suggested test
type, 0 otherwise. The MDEs use the audit's analytic formulas
(`src/myquant/stats/power.py`): lead-lag partial R²
λ²/(λ²+n) against the 0.005 threshold (the minimum effect size
preregistered in every lead-lag study); cross-section R², same
formula, against 0.05 (H0008's criterion); event-study
standardized mean CAR λ/√n (one-sided) against 0.3 (H0007/H0011's
criterion). Mean comparison has no MDE in the planner — it needs
window/non-window group sizes the planner does not know until the
window is defined — so its power component is None: the component
drops out and the remaining weights renormalize instead of
scoring 0. An unmapped test type is likewise None.

Sample sizes are *estimated* from the verified per-node panels:
daily lead-lag uses the estimated joint rows in the overlap window
(each panel's verified row count spread pro-rata by days; the
sparser panel binds); CPI-as-source uses the target's daily rows
inside the step-predictor window (first release to panel end);
CPI-as-target uses the calendar months in the overlap;
cross-section counts FOMC statements in the overlap window after
an 84-calendar-day warm-up (approximating the 60-trading-day CAR
estimation window) and requires one post-statement day for the
event window. Every estimate is labelled as such, and the
preregistration drafts mark the confirmed sample size TODO.

### Weights

The default weights (adjacency 0.4, data 0.3, power 0.3) are a
documented choice, not a derived optimum: adjacency carries the
largest weight because it is the only component that uses the
lab's own evidence (supported edges); data and power are
feasibility gates of equal standing. The weights are parameters,
not findings — no weighting is "optimal" or "validated". The
validation report runs two alternative weightings
(adjacency-heavy 0.6/0.2/0.2, power-heavy 0.2/0.2/0.6) and reports
how the top-10 moves. In the current run it does not move at all:
35 pairs saturate all three components and score 1.00 under any
weights, so the top-10 is the same lexicographic slice of that
tier under every weighting; the weights only reorder the lower
tiers.

### Anti-retest guard (hard rule, not a score)

- **Excluded:** a candidate whose (pair, test type, condition)
  exactly matches a tested edge (supported or rejected) — the
  suggested tests are unconditional, so the comparison is against
  unconditional tested edges. Re-running it would duplicate the
  test.
- **Downgraded:** a candidate on a pair already REJECTED under a
  different test type or condition is admitted at half score
  (factor 0.5, in the config) and flagged "same pair rejected
  under a different setting". The lab's recurring pattern is
  same-day transmission with no next-day carryover, so re-testing
  the same pair under another setting needs a new reason.
- A SUPPORTED edge on the same pair under a different setting
  neither excludes nor downgrades: the follow-up question is
  different from re-testing a null.

On the current registry the guard never fires: candidates are by
construction pairs with no tested edge. It is a safety net for
future registries and manually supplied candidate lists, enforced
in code and tested on synthetic inputs.

### Test-type suggestion (explicit mapping)

| Rule (precedence order) | Suggested test | Mechanism |
| --- | --- | --- |
| Target is `macro:cpi-mom` | Monthly lead-lag | transmission |
| Source is `rates:us-10y-yield` | FOMC cross-event regression | cross-section |
| Otherwise | Daily lead-lag | transmission |

A monthly series cannot be the target of a daily-grid test, so
CPI-as-target gets a monthly design. DGS10 is the lab's
policy-surprise proxy, so a DGS10 source gets the H0008
cross-section design (target CAR on DGS10 CAR across FOMC events).
Everything else gets the lab's standard first test: unconditional
daily lead-lag. First tests are unconditional by design —
conditional designs (regime, window) are follow-ups to an
unconditional result, not first tests — and the suggestion is
labelled as such in the draft ("suggested value, researcher to
confirm"). Vol-level, event-response and regime-conditional labels
exist in the controlled vocabulary but do not occur among
candidates: level and event-response tests are self-loops (never
candidates), and regime-conditional designs are follow-ups.

### Preregistration drafts

`generate_prereg_draft` mirrors the registry's spec fields for a
ranked candidate. Known fields are filled (pair, suggested test
type and frequency, lab threshold, estimated joint sample with
its basis, data sources, standard acceptance criteria for the
test type); unknown fields — mechanism, research motivation,
benchmark, cost model, train/validation/holdout windows,
confounders — are marked `TODO`. The draft is a file under
`research/planner-6a/templates/`; it is never written to the
registry, never registers a hypothesis, and never runs a trial.
Template generation is a pure function, and a test asserts the
registry file is byte-identical before and after.

### Validation results (current registry)

- 123 candidates: **111 ranked, 0 excluded, 12 unrankable**.
- The 12 unrankable pairs are all TYVIX against post-2020-only
  nodes (crypto perpetuals, DVOL, CPI): TYVIX ends 2020-05-15
  (discontinued) while the crypto/DVOL/CPI panels start in 2021 —
  no overlapping window. TYVIX cannot be extended. VXN was
  re-fetched past 2020 (see `research/planner-6a/vxn_refresh.json`):
  the full FRED VXNCLS history, 6,487 rows, 2001-02-02 to
  2026-11-17; its 12 pairs moved from unrankable to ranked.
- Score tiers (default weights): 1.00 × 35, 0.80 × 9, 0.70 × 47,
  0.60 × 2, 0.50 × 18. The top-10 is the first ten of the 35-way
  tie at 1.00 in lexicographic order: BAA10Y→SPX, BAA10Y→TYVIX,
  BAA10Y→VIX, BAA10Y→VXN, BAA10Y→DGS10, BTC→BTC_DVOL,
  BTC→ETH_DVOL, ETH→BTC, ETH→SOL, ETH→BTC_DVOL.
- Mechanisms: 104 transmission, 7 cross-section (all DGS10-sourced:
  DGS10→VXN reaches the top tier at rank 35 — its overlap window
  now runs to 2026, 188 FOMC events, MDE 0.0401 vs the 0.05
  threshold — while the other six sit at ranks 85–90 with power
  0: MDE 0.1514 at 44 events, 0.1485 at 45 events, 0.0546 at 136
  events).
- The 12 recovered VXN pairs all score power 0: their joint-n
  estimates (1,422–1,470) sit just under the sample size the
  0.005 lead-lag threshold needs (MDEs 0.00531–0.00549).
  Near-misses, not comfortably powered — and the joint-n figures
  are pro-rata estimates, so the power verdict on these pairs is
  marginal either way.
- Weight sensitivity: top-10 identical (10/10) under all three
  weightings, for the reason above — the top tier saturates every
  component.
- MDE cross-check: 15/15 audit entries reproduced exactly.
- Independent recomputation (6a review, on the pre-refresh
  ranking): the full ranking was re-derived a second time in
  plain Python with no repo imports — adjacency tiers, test-type
  suggestions, joint-n estimates, power components, the guard,
  and the ranking under all three weight sets — from the registry,
  the availability config, the FOMC calendar and the audit
  summary. All 99 ranked rows matched exactly (scores, joint n,
  MDEs, adjacent edges, decision records), as did the 24
  unrankable pairs, the score tiers and the weight-invariance
  result. The pair census was also checked: 144 ordered pairs =
  17 with edges + 123 candidates + 5 self-pairs with neither
  (SOL, BTC_DVOL, ETH_DVOL, VXN, CPI) − 1 pair in both sets:
  VIX→TYVIX, whose only tested edge (E0013) is descriptive, so
  the guard (tested edges only) correctly leaves the candidate
  ranked. The VXN refresh changed the ranking to 111 ranked /
  12 unrankable (above); the refreshed ranking was re-run and
  reproduced byte-identically (`ranking.json`) except the report
  timestamp.
- Independent review of the VXN refresh: the FRED pull was
  re-fetched independently (plain urllib, no User-Agent) and is
  byte-identical to the refresh payload (SHA-256 `8d356b55…`);
  all counts agree (6,487 valued rows, 242 empty-field missing,
  2001-02-02 → 2026-11-17; overlap 4,372 / 161, new segment
  1,637 / 60). The overlap window was additionally cross-checked
  value-by-value against Yahoo ^VXN: from 2003-09-22 onward the
  two series agree exactly on 99.4% of common dates (5,722 of
  5,755 from 2004 onward; the 33 exceptions are Yahoo-side
  artefacts — a stale-quote run in February 2017 and two
  crisis-day bad ticks). Before 2003-09-22 Yahoo carries the
  pre-methodology-change series (mismatches run 2003-01-02 →
  2003-09-19 and stop exactly at the 22 September 2003 CBOE
  methodology launch), so Yahoo cannot validate the first nine
  months of the study-003 window — FRED, the official CBOE
  series, remains the lab's source throughout. The ranking
  delta was also re-derived independently: all 12 recovered
  pairs' MDEs recomputed from their joint-n estimates, the
  DGS10→VXN event count re-counted from the FOMC calendar
  (188 statements in the overlap window), the tier counts
  tallied from `ranking.json`, and the top-10 confirmed
  unchanged.

### Limitations

- The ranking is a heuristic with coarse components: 35 pairs tie
  at the top score, so the top-10 is decided by the lexicographic
  tie-break, not by discriminating evidence. A finer power
  component (e.g. a continuous MDE margin) would break the tie,
  but that is a design decision for a later planner version.
- Joint sample sizes are estimates, not verified joint counts.
- The analytic MDE ignores HAC/autocorrelation adjustments that
  would raise the true MDE; a pair scored power 1 is "detectable
  in principle", not "powered in practice".
- CPI-as-source pairs use daily rows for the MDE, matching the
  H0012 audit treatment; the effective sample size is 69 distinct
  step values, so their power scores are optimistic. Each such
  draft carries the caveat.
- The planner knows nothing about economics: it cannot tell a
  plausible mechanism from a spurious pair, and it does not try.

## 2. Evidence and source analyst (6b)

`src/myquant/evidence/` collects the source facts the seven
studies verified by hand — FRED's keyless CSVs, the Deribit
expired-instruments quirk, BLS blocking curl, OKX's `after`-only
pagination, the 90-day trade retention, the one-trading-day FRED
publication lag — into one registry with a checker, so the next
study can confirm its sources are still alive and still behave
the way they were recorded to behave. Validation:
`research/evidence-6b/probe_sources.py` (live, 13 small requests),
report in `research/evidence-6b/report.md` and
`research/evidence-6b/evidence_report.json`.

### What the analyst is (and is not)

The analyst checks. It does not judge whether a source is
reliable or will stay available: a PASS means only that this
probe, at this moment, matched the recorded expectation. It does
not re-verify everything — expensive checks (the OKX 90-day
retention bisection, the FRED lag timing) stay recorded-only with
their recheck method written down, and the report keeps live
observations and recorded-only items in separate sections. It
reads the planner's `data_availability.json` for panel freshness
but never writes to it, the registry, or any study data.

### Registry

`research/evidence-6b/sources.json` (hand-written, schema
version 1): 8 sources, each with id, provider, description, base
URL, auth (all public, no key), the studies that use it, the
endpoints used with their expected response structure, retention
and publication lag, a `last_verified` date, and quirks — each
quirk cited to the study and date that verified it. 41 quirks in
total, 33 of them recorded-only (not re-checked by the probe).
`recorded_only` is false only when a probe check *asserts* the
quirk's claim — or the fetch itself proves it, as with FRED's
keyless access. A quirk the probe merely observes without
asserting (the Yahoo User-Agent requirement, the 09:30 ET bar
timestamps, the full DVOL history count) stays recorded-only,
with its recheck method written down.
Duplicate source ids are rejected; unknown source or probe ids
are refused, never guessed; a manual-only source must have a
`manual_check` method and no probes, an automatic source needs at
least one probe.

| Source | Probes | Notes |
| --- | --- | --- |
| OKX public REST | 1 (candles, limit 2) | 1D bars open 16:00 UTC; history-trades ~90 days; funding 8h grid, ~93-day retention with a moving floor |
| Deribit public API | 2 (expired instruments, DVOL) | expired=true returns only the most recent batch; DVOL needs a `currency` param |
| FRED fredgraph CSV | 6 (one per series) | no key; no User-Agent header (custom UAs hang); missing = empty fields; 1-trading-day publication lag |
| Yahoo Finance chart | 1 (^GSPC) | Mozilla UA required; `^MOVE` is an ETF, `^TYVIX` delisted |
| Fiscal Data API | 1 (recent auctions) | lags the live schedule ~4 weeks |
| Fed FOMC pages | 1 (calendar page) | smoke check only, not a parse |
| BLS | 0 — manual-only | curl gets HTTP 403; the CPI calendar is a text-fetch transcription |
| Hyperliquid | 1 (allMids) | reachable without a key; no study uses it |

### Check kinds

Every check returns PASS / FAIL / SKIP + evidence (timestamps,
counts, a payload hash, or an excerpt); a FAIL always carries a
reason. Checks are pure functions over a payload — they never
make network requests, and the tests never import the fetch layer
(an AST test enforces the separation).

- **Reachability** — HTTP status, or the error type when no
  response arrived.
- **Structure** — the expected fields/columns exist (FRED CSV has
  a DATE column; OKX `code` is `"0"`).
- **Source-specific assertions** — Deribit's expired contracts all
  share one expiry date (the recorded single-batch behaviour);
  a discontinued series still ends at its recorded end.
- **Freshness** — see below.
- **SKIP** — the payload check is not run when no payload arrived,
  and manual-only sources get a SKIP with the manual method.

The thin fetch layer (`fetch.py`) is stdlib urllib with a
timeout, an explicit per-source User-Agent, one request, no
retries. A failed fetch is recorded with its status code or error
type, never silently skipped.

### Panel freshness

`research/evidence-6b/panel_freshness.json` maps each of the 12
planner panels to a lag rule and the probe key that supplies its
latest point. The verdict compares the panel's `last` date with
the latest point the source serves *now*: FRESH when the panel
already holds everything the source serves, STALE with the
calendar-days-behind count otherwise, UNKNOWN when no latest
point was observed or the source serves *less* than the panel
(possible truncation or revision). The expected latest is judged
against the source's known lag (FRED: previous trading day; OKX
daily: yesterday's bar open; DVOL: yesterday's point; Yahoo:
latest close at the 21:00 UTC convention; CPI: latest reference
month whose BLS release date has passed) — but the verdict is
judged against what the source serves, not the expectation, so a
holiday-week expectation being one day early cannot flip a
verdict; the mismatch is recorded as a note instead.

Two rules handle data that is still forming. The OKX check reports
the latest *confirmed* bar (the newest row is usually still
forming). The DVOL check, given the probe date, excludes the
current day's provisional row — the endpoint serves it with a
running close, and the lab's adapter treats a point as usable
only from the next day, 00:00 UTC. TYVIX is marked discontinued
(series end 2020-05-15): a panel ending there is the expected
state, not staleness; new data past the recorded end would make
it STALE with a note that the "discontinued" fact itself is
stale.

The ETH/SOL perpetual panels share the OKX 1D bar grid with BTC,
and the ETH DVOL panel shares the DVOL daily grid with BTC DVOL,
so those panels' latest points come from the BTC probes; the
config says so explicitly rather than fetching the same grid four
times.

### Validation results (probe 2026-11-18T21:45Z)

13 requests, 27 checks passed, 0 failed, 1 skipped (BLS,
manual-only). The report is a snapshot of probe time: re-running
changes the timestamp, the observed latest dates and the freshness
verdicts; the registry citations and recorded-only items do not
change.

- **Deribit's single-batch behaviour confirmed live**: 62 expired
  contracts, one batch expiring 2026-11-18.
- **VXTYN still ends 2020-05-15** (discontinued series-end check).
- **Fiscal Data API lag persists**: latest auction 2026-10-22,
  27 days behind the probe date.
- **BAA10Y posts later than the other FRED series**: at probe
  time its latest was 2026-11-16 while VIXCLS, VXNCLS and DGS10
  had 2026-11-17 — the one-trading-day FRED lag is not uniform
  across series. The panel is fresh (it holds everything the
  source serves); the note records the source's own lag.
- **Panels: 5 fresh, 7 stale.** Fresh: BAA10Y, BTC DVOL, ETH
  DVOL, TYVIX (discontinued, as expected), CPI. Stale by 1 day:
  BTC/ETH/SOL perpetuals, VIX, DGS10 — routine overnight lag, the
  panels were verified on 2026-11-16. SPX stale by 2 days (the
  Yahoo panel's last close is 2026-11-16; the probe saw the
  2026-11-18 close). VXN stale by 2,377 days: the FRED series
  continues (latest 2026-11-17) but the lab's verified panel ends
  2020-05-15 — the panel needs a re-fetch, not the source a fix.

Note (2026-11-19): the VXN panel has since been re-fetched past
2020-05-15 (see `research/planner-6a/vxn_refresh.json`); the
2,377-day figure above is the probe-time snapshot, kept as
recorded.

Two corrections the live probe forced, both fixed and tested
before this section was written:

- The first draft of the Hyperliquid check assumed the allMids
  response was a `{"mids": [...]}` wrapper; the live response is
  a flat symbol-to-price map (1,427 entries at probe time). The
  check now verifies that shape and the presence of BTC/ETH.
- The first DVOL check reported the current day's row as the
  latest point; the probe caught it (a 2026-11-18 row with a
  running close at 21:34 UTC). The check now excludes provisional
  points, and freshness notes when a source serves past the
  expected latest.

Independent review (plain urllib re-probe, no repo imports,
~5 minutes after the first probe) confirmed every live fact:
all 13 endpoints returned 200; OKX's latest confirmed bar opens
2026-11-17T16:00Z; Deribit returned 62 expired contracts in one
batch expiring 2026-11-18; DVOL's latest final point is
2026-11-17 close 43.29 with a provisional 2026-11-18 row present;
FRED's VIXCLS/VXNCLS/DGS10 end 2026-11-17, BAA10Y ends 2026-11-16
(the one-day BAA10Y lag is real, not a probe artefact), VXTYN
ends 2020-05-15, CPIAUCSL ends 2026-10-01; Yahoo's ^GSPC latest
is the 2026-11-18 close; Fiscal Data's latest auction is
2026-10-22 (27 days behind); the Fed page is byte-identical at
166,359 bytes; Hyperliquid is a flat map of 1,427 string prices.
The re-probe also confirmed the raw forms the checks assert: the
DGS10/BAA10Y missing rows are empty fields, not "."; the Yahoo
bar timestamps are 14:30 UTC (09:30 EST); the Deribit listing
carries `base_currency` and no top-level `currency` key.

The same review corrected the registry's live/recorded
classification, which had over-claimed in places: several
quirks marked live were only observed by the probe, not
asserted — the Yahoo User-Agent requirement and bar-timestamp
convention are now recorded-only, and the bundled DVOL, VXTYN
and Deribit-listing quirks are split so the live-asserted half
(00:00 UTC timestamps; the discontinued series end; the
`base_currency` field) is separated from the recorded half (the
2,065-point history; the 2003 start; the absent `currency`
field). The checks were strengthened to match: the OKX check
asserts the 16:00 UTC bar open, the DVOL check asserts the
00:00 UTC timestamping, the FRED check fails on a "."-form
missing value, and the fiscal check reports the lag in days.
The registry's Hyperliquid endpoint description still said
`{"mids": [...]}` after the check was fixed; it now states the
flat-map shape.

### Limitations

- One probe is one moment: a passing check says nothing about
  the source tomorrow, and a failing check may be a transient
  outage — re-probe before concluding anything.
- The expected-latest rules use a weekday calendar and ignore
  market holidays, so a holiday-week expectation can be one day
  early; the verdict is judged against what the source serves
  for exactly this reason.
- The Fed page check is a smoke check (markers present), not a
  parse of the meeting list; the Fiscal Data API lag is observed
  from the latest auction date, not measured against the live
  schedule.
- BLS has no automated probe: its calendar stays a manual
  transcription until someone re-checks it by hand.
- 33 of the 41 registry quirks are recorded-only. The expensive
  re-checks (OKX retention bisection, FRED lag timing, the
  TreasuryDirect cross-check) have their methods written down
  but have not been re-run since the citing study.
- The DVOL provisional-point exclusion depends on the probe
  date: a probe run without `as_of` counts the current day's row
  as the latest point. The probe script always passes it.

## 3. Experiment/code assistant (6c)

`src/myquant/scaffolding/` generates the standard study directory
for a new study: README, design, preregister/fetch/run_trial
skeletons, contract stubs, a parked planner draft, and a report
template. Validation: `research/scaffold-6c/validate_scaffold.py`
(offline, deterministic), report in
`research/scaffold-6c/validation_report.md`, an as-generated
inspection copy (TODOs intact) in `research/scaffold-6c/generated/`.

### What the scaffold is (and is not)

The scaffold wires structure. It does not design: the generated
`run_trial.py` carries explicit TODO markers for every study-specific
design decision (regression settings, acceptance criteria,
window/sample definitions), and the scaffold never picks a
threshold, a window, or a test. Thresholds and criteria come from
the study spec, written verbatim. The scaffold does not start a
study either: after generation, no hypothesis is registered, no
trial has run, no data has been pulled — the directory contains no
`trials.jsonl`, no `manifest.json`, no panel. A study starts when
its hypothesis is registered, not when its directory is generated.

### Inputs

Two ways to specify a study:

- A `StudySpec` (pydantic `StrictContract`): study number and slug,
  hypothesis id, source/target instruments, test type (lead-lag,
  mean comparison, event study, cross-section), frequency (daily,
  1h, monthly), source ids, universe, calendar ids, the minimum
  effect size, and the acceptance criteria. Mean-comparison and
  event-study specs must be self-loops (source == target);
  lead-lag and cross-section specs must have distinct instruments.
  Instrument ids must already satisfy the catalog contract's
  pattern, so a bad id is refused at spec time.
- A 6a preregistration draft (`spec_from_planner_draft`): the
  draft's known fields (pair, suggested test, frequency, lab
  threshold, estimated joint sample, templated question and
  hypotheses) map onto a spec, and its TODO fields stay TODO —
  never silently filled. Source ids and calendar ids are explicit
  parameters, not derived from the draft: the draft's
  `source_versions` are descriptive strings, not ids, and the
  mapping never guesses an id from prose.

### Generated files

For a spec, `generate()` writes (13 files for the BAA10Y→SPX
validation case):

- `README.md` — question, design, data, results; all TODO.
- `spec.json` — the scaffold spec, sorted JSON.
- `design.json` — the preregistration design. Filled fields come
  from the spec (or, for the purge gap, from the spec horizon:
  the purge gap equals the horizon, the minimum the validator
  allows). Every other design decision is a literal `"TODO"`.
- `preregister.py` — reads `design.json`, scans it and the stubs
  for TODOs, and refuses to register while any remain, listing
  exactly what is missing by JSON path. When TODO-free it builds
  the `HypothesisSpec` through the repo's real validation and
  registers through the repo's `HypothesisRegistry` (fingerprint,
  immutable v1 snapshot, hash-chained event). No scaffold-side
  registration machinery exists.
- `fetch_data.py` — fetches the registered sample window
  ([train start, holdout end)) into a RawStore and a PIT store,
  and writes a manifest and a panel summary (counts only). Each
  instrument's source is inferred from its catalog metadata key
  (`fred_series`, `yahoo_symbol`, `okx_inst_id`,
  `deribit_currency`, `hyperliquid_coin`); an instrument with no
  known key — or several — is refused. Implemented fetchers call
  the repo's real adapter APIs (OKX, FRED, Yahoo, Deribit DVOL,
  Hyperliquid); sources without an adapter helper (Fiscal Data,
  Federal Reserve, BLS) and frequencies an adapter cannot serve
  are TODO fetchers that fail fast before any fetch.
- `run_trial.py` — loads the panel, runs the primary test for the
  spec's test type, adjusts the (single-test) family, and records
  the verdict through the `ExperimentRunner`. The verdict covers
  the primary criterion only; the walk-forward OOS evaluation and
  the cost gate are stub functions, not wired in. Design hooks
  (`condition_mask`, `load_events`, `load_event_cars`) raise
  `NotImplementedError` until the researcher defines them. The
  mean-comparison test carries the study 004/006 bootstrap
  cross-check (the OLS coefficient must equal the weighted-series
  mean — the guard that caught the T0006 weights bug).
- `sources/<id>/v1.json` stubs — provider and description from the
  6b registry; everything else TODO, license `"unknown"` until the
  researcher sets `"approved"` with a permission basis. Only
  `SourceDefinition` fields appear, so a filled stub is a valid
  contract.
- `catalog/instruments/<id>/v1.json` and
  `catalog/calendars/<id>/v1.json` stubs — same convention.
- `hypotheses/registrations/<HID>/draft.json` — the planner-draft
  format JSON, parked. The registry only globs `v*.json`, so the
  draft is invisible to it: it is not a registration.
- `docs/studies/<slug>.md` — the report template.

### Guards

The generator refuses rather than guesses: an unknown source id
(not in the caller-supplied known-source mapping), an existing
target directory, an existing report, or a target that does not
sit directly under `research/` all raise `ScaffoldError` and write
nothing. Generation is deterministic: the same spec, known sources
and source metadata always produce byte-identical files — no
generation timestamps, sorted file and JSON-key order.

### Validation results

From `research/scaffold-6c/validation_report.md` (planner template
BAA10Y→SPX, rank 1, daily lead-lag; hypothesis id H9001 and trial id
T9001 are synthetic wiring-test ids, deliberately never lab ids —
the next real hypothesis id is H0013):

- (a) The unfilled scaffold's `preregister.py` exits 1 listing 51
  missing items by JSON path. With a minimal design filled in
  (values mirror the committed study 003/005 contracts; mechanism
  and cost text marked as wiring placeholders), it registers H9001
  as v1: fingerprint
  `30c355bc3934e445f4d2e38d9404a514835728f2beda2321765e41c87f279c5e`
  (recomputed independently from the registered spec, matches).
- (b) The generated Python files pass ruff and mypy strict for all
  four test types (12 files). mypy runs with `MYPYPATH=src`
  because the installed `myquant` package carries no `py.typed`
  marker; one study at a time, because all four share filenames
  and mypy rejects duplicate modules. Note the bar is stricter
  than the repo's own study scripts: study 001's `run_trial.py`
  has 2 pre-existing strict errors under the same invocation.
- (c) The same spec generated twice: 13 files, all byte-identical.
- (d) All three guards refuse: existing directory, unknown source
  id, unknown test type.
- (e) The generated `run_trial.py` runs end to end in a tmp git
  repo on a fixed-seed synthetic panel (seed 1234, 500 daily bars,
  independent random walks): 499 return rows, trial T9001
  completed, 1 ledger record verified with `read_and_verify`,
  primary test 498 observations, coefficient 0.074561, p 0.1483,
  partial R² 0.004470, verdict False. Conclusion: the wiring
  works. The numbers claim nothing — independent walks have no
  transmission by construction.

### Limitations

- One test type (lead-lag) was wired end to end. The other three
  types were generated and lint-checked, but their design hooks
  raise `NotImplementedError` until a researcher defines them —
  no wiring run exists for them yet.
- The synthetic panel is Gaussian daily noise with a simplified
  PIT convention (`available_at` = `event_time`); it validates
  machinery, not market behaviour.
- The fetch skeleton was not run against live endpoints in
  validation (no real data was fetched by design). Its fetchers
  mirror the adapters' real APIs and the fetch flows of studies
  001/003/005, but the first real fetch of a scaffolded study is
  still untested ground.
- The planner-draft mapping covers the 6a draft format only. A
  draft with an unknown test type, a non-two-instrument universe,
  or a non-draft flag is refused, not repaired.
- The scaffold knows nothing about economics and does not try:
  it cannot tell a sensible study from a nonsensical one. That
  judgement stays with the researcher — which is the point.
- Fixed after first real use (study 008): the scaffold used to
  generate `bar_seconds=86400` for daily studies, which would
  invalidate every Monday/post-holiday return on a trading
  calendar (~30% of rows). Daily now generates no gap
  invalidation (per-trading-day returns, the study-003
  convention); 1h keeps it, monthly never had it. The other six
  items of study 008's scaffold feedback are recorded in that
  study's report, not fixed here.
- Second real use (study 009): generated from the planner's
  BAA10Y→TYVIX template, it exposed no new gaps — every
  hand-adaptation was a repeat of a study-008 item — and the
  `bar_seconds` fix was verified in the generated file
  (`BAR_SECONDS = None`). See that study's report.
- Third real use (study 010): generated from the planner's
  BAA10Y→VIX template, it exposed no new gaps either — every
  hand-adaptation was a repeat of a study-008 item — and the
  `bar_seconds` fix was verified again in the generated file.
  The generated files contain no real-ID placeholder specs
  (only the real H0015; the H9002/H9003/H9004 placeholders
  live only in the 6c validation). See that study's report.

### Independent review

The validation was re-run from a clean checkout and reproduced
the report exactly except the three wall-clock values (report
timestamp, registration hash, ledger record hash). The synthetic
wiring numbers were recomputed independently in plain numpy (no
repo imports: the panel regenerated from seed 1234, the partial
lead-lag OLS and the Bartlett Newey-West HAC re-derived from
first principles): 498 observations, coefficient 0.074561,
p 0.1483, partial R² 0.004470, verdict False — all match. The
study-001 comparison was also checked directly: 001's
`run_trial.py` has exactly 2 pre-existing strict errors under
the same mypy invocation (an `arg-type` at line 203 and an
`operator` at line 579), so the scaffold's stricter bar is a
real difference, not a claim. One review fix: the validation
originally used hypothesis id H0013 — the next real lab id —
for its placeholder spec; it now uses H9001, mirroring T9001,
so no validation fingerprint can ever be confused with a real
H0013 registration. The same staleness recurred with the
other-type placeholder specs (H0014/H0015/H0016 in
`_other_type_specs`): study 009's real H0014 collided with
the mean-comparison placeholder, and H0015 was the next real
id in line. All three were renamed to H9002/H9003/H9004 in
the study-009 review; re-running the validation reproduced
the report except the three wall-clock values, and the H9001
fingerprint is still `30c355bc…`.

## 4. Adversarial reviewer (6d)

### What the reviewer is (and is not)

The reviewer is a read-only study auditor: it runs a set of
checks over one study or the whole lab and returns a verdict
(PASS / FAIL / UNVERIFIED / NOTE) plus located evidence for
each. It is the lab's own review discipline — re-derive the
numbers, check the bindings, compare the report against the
ledger — written as code, so a future study can be audited the
same way the first seven were.

It is not a study: it registers no hypothesis, runs no trial,
fetches no market data and makes no alpha claim. It is not a
fixer: when it finds a real problem in an existing study, it
reports the problem and leaves the study untouched — the fix is
a separate delivery decision. It is not a judge of economics:
it checks internal consistency (does the record agree with its
preregistration, its ledger, its report?), not whether a study
was worth doing.

### Verdict semantics

- **PASS**: the check ran and the record satisfies it.
- **FAIL**: the check ran and the record violates it, with
  located evidence (file, record hash, expected vs actual).
- **UNVERIFIED**: the check could not be performed — data not
  retained, value not locatable, prerequisite unreadable. This
  is **not** a pass. "No problem found" and "could not check"
  are different outcomes and the reviewer never conflates them.
- **NOTE**: informational only; the check never fails (MDE
  annotations from the 2B audit).

The reviewer is **read-only**: it reads study directories,
registries, ledgers, reports, the audit summary and the PIT
cache, and writes only its own review report under
`research/review-6d/`. The runner loads ledgers fail-closed: if
a ledger cannot be verified, the checks that need its records
are reported UNVERIFIED ("ledger unreadable") rather than run
on untrusted records. The review is deterministic for a fixed
timestamp — the timestamp is an input parameter, and re-runs
reproduce the report byte-identically.

### Checks

| check | what it verifies | evidence on failure |
| --- | --- | --- |
| `ledger_chain` | each study's `trials.jsonl` hash chain, via the repo's own `read_and_verify` (no home-grown hash logic) | the verification error |
| `ledger_anchor` | the ledger against its anchor file (truncation detection — the chain alone cannot catch deleted trailing records) | the anchor mismatch; absent anchor → UNVERIFIED |
| `registry_events` | the hypothesis registry's lifecycle-event chain and transition legality, via `HypothesisRegistry.read_events` | the verification error |
| `prereg_binding` | per trial (completed and failed): the trial's hypothesis fingerprint matches the registered spec fingerprint; the research plan matches the preregistration (via the runner's own matcher, so the reviewer applies exactly the definition of "matches" the runner enforces); the record's spec fingerprint matches the stored spec | expected vs recorded fingerprint, or the plan mismatch |
| `multiple_testing` | per completed trial: the recorded Holm family has exactly the planned test count; every recorded raw p-value matches its test's p-value; every adjusted p-value and reject flag recomputes with the repo's `adjust_pvalues` (tolerance 1e-9) | recorded vs recomputed value |
| `verdict_consistency` | per completed trial: `supported` equals the conjunction of the recorded criteria; the Holm-adjusted primary p-value criterion and the primary effect criterion re-derive from the metrics and the spec's thresholds | the contradicting criterion and values |
| `hypothesis_state` | per tested hypothesis version: the registry's lifecycle state (SUPPORTED/REJECTED) matches the latest completed trial's verdict | state vs verdict |
| `trial_sequence` | lab-wide: trial IDs form a contiguous sequence from T0001, except T0003 (reserved for the preregistered H0003 forward test, not yet run); the known failed trials T0006/T0008/T0014 are present with status `failed` | the missing or duplicated ID |
| `report_ledger` | per study report: 52 rules locate results-table rows by label and compare the numeric columns against the ledger within the rounding tolerance implied by the report's stated precision | report vs ledger value and tolerance |
| `pit_spot_check` | per study: every retained PIT observation satisfies `available_at >= event_time` (scoped to historical market-data observations; forecasts legitimately differ) | the violating observation; no retained data → UNVERIFIED |
| `power_note` | per completed trial: the 2B audit's MDE entry for the primary test, restated next to the trial (informational; an underpowered null is a recorded limitation, not a defect) | — |

Two conventions the checks rely on, both verified against the
current lab and stated here so a future deviation is visible:
the primary test of a trial is the first entry of its recorded
Holm family (`metrics["holm"][0]` — true for all 11 completed
trials, and the report check independently confirms each
primary test's identity from the report tables); and the
verdict criteria keys follow the patterns
`holm_adjusted_*_p_below_<alpha>`,
`partial_r_squared_at_least_<t>` / `r_squared_at_least_<t>` /
`standardized_mean_car_at_most_minus_<t>` /
`effect_ratio_at_least_<t>`.

### Validation results

From `research/review-6d/validation_report.md` (review at
2026-11-18T23:30Z; re-runs with the same timestamp reproduce
all three outputs byte-identically):

**Full-lab review — 94 checks: 75 PASS, 0 FAIL, 8 UNVERIFIED,
11 NOTE.** Every ledger chain verifies; every trial binds to
its preregistration (14 records, completed and failed); every
multiple-testing adjustment recomputes (11 completed trials);
every verdict re-derives; every lifecycle state agrees; the
trial-ID sequence is complete with T0003 reserved and all
three failed trials recorded. The 52 report rules verified
all 52 rows, across 336 compared numeric cells.

**The reviewer's first run found three real discrepancies —
and they were fixed, not just reported.** The first run
(2026-11-19T07:30Z) came back 72 PASS / 3 FAIL / 8 UNVERIFIED
/ 11 NOTE, all three FAILs report–ledger discrepancies.
Each was independently confirmed against the raw ledger and
report files (not taken on the reviewer's word), then
corrected in the same delivery — five numbers in three
reports — and the re-run above is clean. None changes any
verdict or conclusion — all are in the fifth or sixth decimal
of null results — but each was a genuine disagreement, and
the reviewer caught real errors in the lab's own records on
its first run. That is the loop the tool exists for:

1. **Study 003** (3 rows): the "incr R²" column duplicated the
   partial R² column instead of the ledger's
   `incremental_r_squared` (R²_full − R²_base). Daily row:
   report 0.000035, ledger incremental 0.000034; weekly row:
   report 0.0000086, ledger incremental 0.0000083; weekly
   no-factor row: report 0.0000086, ledger incremental
   0.0000084. The other three rows agree at the displayed
   precision. The mapping is confirmed, not assumed: studies
   002 and 006 show distinct partial and incremental values
   that both match their ledgers (e.g. 002 A1: 0.00376 vs
   0.00374; 006 B: 0.02123 vs 0.02099), and the kernel defines
   the two quantities differently. The 003 author copied the
   partial column into the incremental column.
2. **Study 004** (1 row): the ETH mean-comparison bootstrap CI
   upper bound read 0.00518 in the report; the ledger value
   0.0051748 rounds to 0.00517 — a one-unit-in-the-last-place
   transcription slip. The interval includes zero either way.
3. **Study 007** (1 row): the DGS10 lagged-CAR standard error
   read 0.785383 in the report; the ledger value 0.78538236
   rounds to 0.785382 — a one-unit-in-the-last-place
   transcription slip. The z-statistic and p-value are
   unaffected at the displayed precision.

**The eight UNVERIFIEDs are seven PIT checks and one anchor.**
Studies 001–007 retain no PIT parquet locally, so their PIT
discipline is currently unverified, not verified — the absence
of data is not evidence of discipline. Study 005 has no
`trials.jsonl.anchor`, so truncation of its ledger cannot be
ruled out by the anchor (only the trial-ID sequence check
would notice, and only if the deleted record's ID left a gap).

**Adversarial fixtures — 6/6 caught.** Six deliberately
broken fixtures in tmp dirs, each isolating one violation
with a valid hash chain except where the violation is the
chain itself: a tampered ledger record (chain breaks), a
trial fingerprint that does not match the preregistration, a
changed adjusted p-value, a verdict flag contradicting its
criteria, a synthetic panel with `available_at` before
`event_time`, and the failed trial T0006 deleted from its
ledger. Every fixture FAILs with the correct reason.

**Rounding-margin diagnostic.** For the 336 compared numeric
cells, |report − ledger| / rounding-tolerance: the highest
passing ratio is 0.990 (a correctly rounded value near its
rounding boundary — expected, since rounding residuals spread
uniformly in [0, 1]); no cell falls outside tolerance. On the
first run, before the three discrepancies above were fixed,
the four failing numeric cells sat at 1.17–5.10, a separate
population from the passing cells — evidence the tolerance
is not tuned to pass.

### Limitations

- **Report coverage is table-bound**: only the 52
  results-table rows with explicit rules are checked. Prose
  numbers, descriptive split tables and the verdict-criteria
  tables are not mechanically compared; a discrepancy there
  would not be caught. Adding a rule is a one-line change in
  `tables.py`, but each rule's row label and column mapping
  must be quoted from the report, not guessed.
- **The primary test is the first Holm-family entry** (see
  above). A future trial that orders its family differently
  would be misread by the verdict check.
- **PIT coverage depends on retained data**: the check runs
  only where parquet batches still exist. The seven study
  caches are gone, so the lab's PIT discipline is currently
  unverified.
- **Truncation needs anchors**: study 005 has no anchor file
  (see above). A future study that ships without an anchor
  has the same gap.
- **The reviewer trusts the registry's own verification**:
  registration and event-log integrity come from the repo's
  `HypothesisRegistry` code, not from an independent
  reimplementation. A bug shared by the registry and the
  reviewer would be invisible to both. The reviewer does
  independently recompute the things it can — adjusted
  p-values, verdicts, spec fingerprints — but the hash-chain
  primitive itself is reused by design, not re-derived.

## 5. Research librarian and report generator (6e)

### What the librarian is (and is not)

The librarian is the lab's catalogue: it scans the committed
records — registrations, trial ledgers, the graph registry,
decision records, planner output, the evidence registry, the
6d review report and the 2B audit summary — and builds a
unified catalog (`research/library-6e/catalog.json`) plus a
lab status report (`lab_report.md` + `lab_report.json`). The
records live in a dozen directories; the librarian is the one
place that knows how they link together.

It is not a study: it registers no hypothesis, runs no trial,
fetches no market data and makes no alpha claim. It is not a
fixer: it never modifies a source record — a broken link or a
missing file is reported in the catalog and the report, and
the repair is a separate delivery decision. It is not a
judge of correctness: it checks that references *resolve*,
not that the referenced values are right. Catching wrong
numbers is the reviewer's job; the librarian quotes the
reviewer's verdicts.

Every number in the catalog is derived by reading a record —
nothing is transcribed by hand. The 6d review proved
hand-transcribed report numbers drift; the librarian's
answer is to never type a number in the first place.

### Catalog contents

| section | contents | source |
| --- | --- | --- |
| studies | 10 empirical studies: report path, hypotheses, trials, anchor/manifest/panel-summary presence, open/closed | `research/*/trials.jsonl` |
| hypotheses | 15 hypotheses, 16 versions: fingerprints, registration hashes, lifecycle states, trials, edges, decision records | `hypotheses/registrations/`, event logs |
| trials | 17 records: status, verdict, primary-test summary (effect, adjusted p, n) | trial ledgers |
| edges | 42 edges: endpoints, status, trial/test key, decision record, audit survival | `research/graph/registry.json` |
| decision records | 18 records: edge/hypothesis/trial/study links | `research/decision-records/records/` |
| candidates | 120 pairs: rank, score, mechanism, template presence | `research/planner-6a/ranking.json` |
| sources | 8 sources: quirks, recorded-only counts, probe outcomes | `research/evidence-6b/` |
| panels | 12 panels: probe-time freshness | evidence report |
| review | 6d counts and unverified items, quoted | `research/review-6d/review_report.json` |
| audit | lab-wide Holm/BH survivors, quoted | `research/statistical-audit-2b/summary.json` |

The catalog also records its own provenance: the 69 source
files read (repo-relative paths), the generation timestamp,
the broken-link list and the missing-optional list.

Two conventions the catalog relies on, both verified against
the current lab and stated here so a future deviation is
visible: the primary test of a trial is the first entry of
its recorded Holm family (the same convention as the 6d
reviewer); and a trial-id gap counts as *reserved* only when
its number matches a hypothesis with no trial yet and a
pending edge — the lab numbers a hypothesis's first trial
after the hypothesis (T0001 ran H0001, T0002 ran H0002, …),
so the pending H0003 reserves T0003. A gap with no such basis
is flagged as a broken link, not silently treated as
reserved.

### Integrity: references must resolve

The builder runs eleven cross-reference checks and records
every failure as a broken link (referrer, kind, referenced
id, reason):

- edges to their trial, test key, hypothesis, nodes and files
- planner candidates to registry candidates and nodes
- decision records to their edge, hypothesis, trial, study
  and files
- planner templates to their ranked pair and rank
- the 6d review to the studies it must cover (and no others)
- the 2B audit's supported edges to the registry
- availability panels to their nodes and cited files
- evidence sources' `used_by` entries to research directories
- the trial-id sequence (gaps need a recorded reservation)
- hypotheses with no trial (need a pending edge or an open
  state)
- studies to their report files

Pending edges have no trial and no test key by design; the
two descriptive edges have a trial but no test key. Neither
is a broken link. Missing *optional* files (ledger anchors,
manifests, panel summaries) are recorded separately in
`missing_optional` — absence is a fact, not a failure.

### The lab status report

`lab_report.md` is the one-page view of the lab: a studies
table (one row per completed trial, with the primary effect,
adjusted p-value and sample size from the ledger), the graph
summary (42 edges by status; the 6 supported edges with their
lab-wide audit survival, quoted from the 2B summary), the
candidate queue (top-10 and tier counts), data freshness
(probe-time snapshot, plus post-probe updates recorded in
committed files — currently the VXN re-fetch), the 6d review
status (quoted, UNVERIFIED items listed as not-passes), the
pending items (H0003 forward test, T0003 reserved, 12
unrankable TYVIX pairs, the study-005 anchor, PIT discipline
unverified for 7 studies), the integrity section, and the
full source list. `lab_report.json` carries the same content
as structured data.

### Validation results

From `research/library-6e/validation_report.md` (catalog
generated 2026-11-18T23:52Z):

**Counts — every catalog count re-derived from the raw files
with plain Python, all matching**: 7 studies, 12 hypotheses
(13 versions), 14 trial records (11 completed, 3 failed, 1
reserved), 39 edges (6 supported, 30 rejected, 1 pending, 2
descriptive), 15 decision records, 123 candidates (111
ranked, 12 unrankable), 10 templates, 8 sources (41 quirks,
33 recorded-only), 27 probe passes / 1 skip, 12 panels (5
fresh, 7 stale).

**Number spot-check — all 11 completed trials' primary
numbers re-derived from the raw ledgers and matching
exactly** (effect, Holm-adjusted p, raw p, n, verdict,
secondary effect). The 6 supported edges' Holm/BH survival,
the planner top-10 and tier counts, and the 6d review counts
were likewise re-derived and match.

**Integrity — 0 broken links**, confirmed by a second,
independent cross-reference pass over the raw files (written
without importing the librarian). No new inconsistency was
found in the lab's records. The only gap is the one already
known from the 6d review: study 005 has no ledger anchor,
recorded in `missing_optional` and in the report's pending
items, not repaired.

**Broken-link validation — the checks catch real breaks.**
Two damaged copies of the lab in tmp dirs: deleting study
001's only trial record surfaces as `edge_trial`,
`record_trial`, `trial_gap` and `hypothesis_no_trial`; changing
decision record DR-E0023's edge id to E9999 surfaces as
`record_edge`. A third copy with two optional files removed
builds without crashing and records both as missing.

**Determinism and drift.** Two builds with one timestamp
are byte-identical across all three artifacts, and the
committed artifacts equal a fresh rebuild with the committed
timestamp (drift test in `tests/test_librarian.py`).

**Independent review.** The build was re-run with the
committed timestamp and reproduced all three artifacts
byte-identically. Every count was re-derived a second time
from the raw files with plain Python (no librarian imports):
7 studies, 13 hypothesis versions across 12 hypotheses, 14
trial records (11 completed, 3 failed, T0003 the only gap),
39 edges (30 rejected, 6 supported, 2 descriptive, 1
pending), 12 nodes, 15 decision records, 123 candidates
(111 ranked, 12 unrankable), tiers 35/9/47/2/18, 8 sources.
All 11 primary-test numbers were re-derived from the trial
ledgers (effect, Holm-adjusted p, n, verdict — including the
mean-comparison ratios and the event-study standardized CARs,
which the report renders as the primary effect). The 6
supported edges' Holm/BH survival was re-derived from the 2B
audit summary (4 Holm survivors, 5 BH survivors; E0030
survives neither, E0031 BH only), as were the quirks
(41 / 33 recorded-only), the probe counts (27 pass, 1 skip —
BLS has a single skip check; its `manual_check` field is the
instruction text, not a second skip) and the panels (5 fresh,
7 stale). Three link classes were checked independently of
the librarian's own pass: all 39 edges resolve to a trial and
a hypothesis, all 15 decision records resolve to an edge and
a hypothesis, and all 10 templates resolve to ranked pairs
with matching ranks 1–10. Everything agrees with the
catalog's 0 broken links.

### Limitations

- **The catalog trusts the records it reads**: a wrong-but-
  resolving number passes the integrity checks. Correctness
  of values is the reviewer's job, not the librarian's.
- **The primary test is the first Holm-family entry** (see
  above). A future trial that orders its family differently
  would be misread by the primary-test summary.
- **Reserved trial ids rest on a numbering convention** (see
  above). If the lab ever numbers a trial out of sequence,
  the reservation logic would misread the gap.
- **Freshness is a probe-time snapshot**: panel status comes
  from the 6b evidence report (probed 2026-11-18T21:45Z),
  not from a live check. Post-probe updates appear only when
  a committed record exists.
- **The catalog covers the ten empirical studies**: stages
  without trial ledgers (microstructure, portfolio, planner,
  evidence, scaffolding, review) appear only through their
  outputs, not as catalogued studies.

### Regeneration after study 008

The catalog and lab report were regenerated when study 008
landed (generated 2026-11-19T00:37Z): 8 studies, 13
hypotheses (14 versions), 15 trial records (12 completed, 3
failed, T0003 reserved), 40 edges (6 supported, 31 rejected,
1 pending, 2 descriptive), 16 decision records, 122
candidates (110 ranked, 12 unrankable), 65 source files.
Integrity still holds: **0 broken links**, and the only
missing optional file is still the study-005 anchor. The
regenerated report quotes the 6d review at 104 checks (84
pass, 0 fail, 8 unverified, 12 note) and the 2B audit at
family 37 (4 Holm survivors, 5 BH survivors). The counts in
the Validation results section above are the 6e validation's
own record (2026-11-18T23:52Z) and are left as they were.

### Regeneration after study 009

The catalog and lab report were regenerated when study 009
landed (generated 2026-11-19T02:13Z): 9 studies, 14
hypotheses (15 versions), 16 trial records (13 completed, 3
failed, T0003 reserved), 41 edges (6 supported, 32 rejected,
1 pending, 2 descriptive), 17 decision records, 121
candidates (109 ranked, 12 unrankable), 69 source files.
Integrity still holds: **0 broken links**, and the only
missing optional file is still the study-005 anchor. The
regenerated report quotes the 6d review at 114 checks (93
pass, 0 fail, 8 unverified, 13 note) and the 2B audit at
family 38 (3 Holm survivors, 5 BH survivors) — E0033 dropped
out of the Holm survivor set when the family grew (Holm p
0.04971 → 0.05117), which is the audit's normal operation,
not an error. The counts in the Validation results section
above are the 6e validation's own record (2026-11-18T23:52Z)
and are left as they were.

Independent review of study 009 (plain numpy, no repo
imports, panel rebuilt from the raw cached FRED payloads):
the panel counts, all four partial tests (36 numbers), all
six scan correlations, all four sub-periods, the MDE, the
walk-forward evaluation (27 folds, both MSEs, both OOS R²
values, all 27 per-fold values) and the full informational
cost gate (gross edge, sign accuracy, bootstrap CI and p)
all match the T0017 ledger record. The E0033 flip was
confirmed from the audit summary itself (family 38, Holm
p 0.051172, BH p 0.01389 — still a BH survivor).

### Regeneration after study 010

The catalog and lab report were regenerated when study 010
landed (generated 2026-11-19T03:01Z): 10 studies, 15
hypotheses (16 versions), 17 trial records (14 completed, 3
failed, T0003 reserved), 42 edges (6 supported, 33 rejected,
1 pending, 2 descriptive), 18 decision records, 120
candidates (108 ranked, 12 unrankable), 73 source files.
Integrity still holds: **0 broken links**, and the only
missing optional file is still the study-005 anchor. The
regenerated report quotes the 6d review at 124 checks (102
pass, 0 fail, 8 unverified, 14 note) and the 2B audit at
family 39 (3 Holm survivors, 5 BH survivors) — E0033's BH p
rose to 0.01426 (from 0.01389 at family 38) and it remains a
BH survivor; E0030's BH p rose to 0.06381 and it remains
outside both survivor sets. The counts in the Validation
results section above are the 6e validation's own record
(2026-11-18T23:52Z) and are left as they were.

Independent review of study 010 (plain numpy, no repo
imports, panel rebuilt from the raw cached FRED/Yahoo
payloads): the panel counts, all four partial tests (36
numbers), all six scan correlations, all five sub-periods,
the MDE, the walk-forward evaluation (40 folds, both MSEs,
both OOS R² values, all 40 per-fold values) and the full
informational cost gate (gross edge, sign accuracy, bootstrap
CI and p) all match the T0018 ledger record. E0033's BH
survival was confirmed from the audit summary itself (family
39, BH p 0.014255, Holm p 0.052634 — still outside the Holm
set).

Stage 6 is complete with this item: the planner (§1), the
evidence analyst (§2), the experiment assistant (§3), the
adversarial reviewer (§4) and the research librarian (§5)
are all in place.


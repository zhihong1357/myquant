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
H0013 registration.

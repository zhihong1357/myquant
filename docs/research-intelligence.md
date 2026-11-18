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
34 pairs saturate all three components and score 1.00 under any
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

- 123 candidates: **99 ranked, 0 excluded, 24 unrankable**.
- The 24 unrankable pairs are all TYVIX/VXN against post-2020-only
  nodes (crypto perpetuals, DVOL, CPI): TYVIX ends 2020-05-15
  (discontinued) and VXN is verified only through 2020-05-15,
  while the crypto/DVOL/CPI panels start in 2021 — no overlapping
  window. Re-fetching VXN past 2020 would make 12 of them
  rankable; TYVIX cannot be extended.
- Score tiers (default weights): 1.00 × 34, 0.80 × 9, 0.70 × 44,
  0.60 × 2, 0.50 × 10. The top-10 is the first ten of the 34-way
  tie at 1.00 in lexicographic order: BAA10Y→SPX, BAA10Y→TYVIX,
  BAA10Y→VIX, BAA10Y→VXN, BAA10Y→DGS10, BTC→BTC_DVOL,
  BTC→ETH_DVOL, ETH→BTC, ETH→SOL, ETH→BTC_DVOL.
- Mechanisms: 92 transmission, 7 cross-section (all DGS10-sourced,
  ranks 80–86 — their power component is 0 at every available
  event count: MDE 0.1514 at 44 events, 0.1485 at 45 events,
  0.0546 at 136 events, vs the 0.05 threshold).
- Weight sensitivity: top-10 identical (10/10) under all three
  weightings, for the reason above — the top tier saturates every
  component.
- MDE cross-check: 15/15 audit entries reproduced exactly.
- Independent recomputation (review): the full ranking was
  re-derived a second time in plain Python with no repo imports —
  adjacency tiers, test-type suggestions, joint-n estimates,
  power components, the guard, and the ranking under all three
  weight sets — from the registry, the availability config, the
  FOMC calendar and the audit summary. All 99 ranked rows matched
  exactly (scores, joint n, MDEs, adjacent edges, decision
  records), as did the 24 unrankable pairs, the score tiers and
  the weight-invariance result. The pair census was also checked:
  144 ordered pairs = 17 with edges + 123 candidates + 5
  self-pairs with neither (SOL, BTC_DVOL, ETH_DVOL, VXN, CPI) −
  1 pair in both sets: VIX→TYVIX, whose only tested edge (E0013)
  is descriptive, so the guard (tested edges only) correctly
  leaves the candidate ranked.

### Limitations

- The ranking is a heuristic with coarse components: 34 pairs tie
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

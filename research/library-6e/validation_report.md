# Research librarian validation (Stage 6e)

Validated at: 2026-11-18T23:52:00+00:00 (the committed artifacts'
generation timestamp; the catalog and reports in this directory were
built with `build_library.py --generated-at 2026-11-18T23:52:00+00:00`).

## What was validated

1. **Catalog build**: `build_catalog` scans the lab's committed
   records and produces `catalog.json` (61 source files read),
   `lab_report.md` and `lab_report.json`.
2. **Count reconciliation**: every catalog count re-derived from the
   raw files with plain Python (no librarian code).
3. **Number spot-check**: all 11 completed trials' primary numbers
   re-derived from the raw ledgers with plain Python.
4. **Independent integrity pass**: a second, independent
   cross-reference pass over the raw files, written without importing
   the librarian, agreeing with the catalog's 0 broken links.
5. **Broken-link validation**: damaged copies in tmp dirs, proving
   the integrity checks catch real breaks (not just pass clean data).
6. **Determinism and drift**: two builds with one timestamp are
   byte-identical; the committed artifacts equal a fresh rebuild with
   the committed timestamp (drift test in `tests/test_librarian.py`).

## Count reconciliation

| count | catalog | re-derived | source |
| --- | --- | --- | --- |
| studies | 7 | 7 | `research/*/trials.jsonl` |
| hypotheses | 12 | 12 | registration dirs |
| hypothesis versions | 13 | 13 | registration files (H0004 v1+v2) |
| trial records | 14 | 14 | ledger lines |
| trials completed | 11 | 11 | ledger `status` |
| trials failed | 3 | 3 | T0006, T0008, T0014 |
| trials reserved | 1 | 1 | T0003 (pending H0003) |
| nodes | 12 | 12 | `registry.json` |
| edges total | 39 | 39 | `registry.json` |
| edges supported / rejected | 6 / 30 | 6 / 30 | `registry.json` |
| edges pending / descriptive | 1 / 2 | 1 / 2 | E0011 / E0012, E0013 |
| decision records | 15 | 15 | `research/decision-records/records/DR-*.json` |
| candidate pairs | 123 | 123 | `ranking.json` total |
| candidates ranked / unrankable | 111 / 12 | 111 / 12 | `ranking.json` |
| planner templates | 10 | 10 | `research/planner-6a/templates/*.json` |
| sources | 8 | 8 | `sources.json` |
| quirks / recorded-only | 41 / 33 | 41 / 33 | `sources.json` + evidence report |
| probe checks pass / skip | 27 / 1 | 27 / 1 | evidence report |
| panels | 12 | 12 | evidence report |
| panels fresh / stale | 5 / 7 | 5 / 7 | evidence report |
| broken links | 0 | 0 | independent pass (below) |
| missing optional files | 1 | 1 | study 005 anchor |

## Number spot-check

All 11 completed trials' primary numbers (effect, Holm-adjusted p,
raw p, n, verdict, secondary effect) were re-derived from the raw
`trials.jsonl` files with plain Python — no librarian code — and
match the catalog exactly. The primary test is the first entry of
each trial's recorded Holm family.

| trial | primary test | effect | adj p | n | verdict |
| --- | --- | --- | --- | --- | --- |
| T0001 | daily_btc_eth | coef 0.0251765 | 1 | 1414 | REJECTED |
| T0002 | daily_btc_sol_interaction | coef 0.221701 | 0.283145 | 1133 | REJECTED |
| T0004 | daily_tyvix_vix | coef −0.00934091 | 1 | 4327 | REJECTED |
| T0005 | daily_btc_eth_interaction | coef −0.0358324 | 0.693823 | 2124 | REJECTED |
| T0007 | btc_mean_abs_return_comparison | effect ratio 1.00006 | 1 | 2125 | REJECTED |
| T0009 | spx_on_dgs10 | slope 0.000117383 | 0.726243 | 135 | REJECTED |
| T0010 | vix_car | std mean CAR −0.150685 | 0.159962 | 135 | REJECTED |
| T0011 | daily_btc_eth_interaction | coef 0.000290488 | 1 | 2124 | REJECTED |
| T0012 | btc_mean_abs_return_comparison | effect ratio 1.25043 | 0.00981768 | 2125 | SUPPORTED |
| T0013 | tyvix_lagged_car | std mean CAR −0.515657 | 5.20144e-09 | 135 | SUPPORTED |
| T0015 | spx_daily | coef −0.0374021 | 0.754874 | 1468 | REJECTED |

Also re-derived and matching: the 6 supported edges' Holm/BH
survival against the 2B audit summary (E0023, E0026, E0032, E0033
survive both; E0030 survives neither; E0031 survives BH only),
the planner top-10 pairs and scores, the tier counts
(1.00 × 35, 0.80 × 9, 0.70 × 47, 0.60 × 2, 0.50 × 18), and the
6d review counts (75 pass, 0 fail, 8 unverified, 11 note).

## Independent integrity pass

A second cross-reference pass, written in plain Python without
importing the librarian, checked every link class over the raw
files: edges to trials/test keys/hypotheses/nodes/files (39
edges), planner pairs to registry candidates (123 pairs),
templates to ranked pairs and ranks (10 templates), decision
records to edges/hypotheses/trials/studies/files (15 records),
review coverage (7 studies), audit supported edges (6 edges),
availability citations (12 panels), and source `used_by` entries
(8 sources). Result: **0 broken links**, agreeing with the
catalog. No new inconsistency was found in the lab's records.

## Broken-link validation

Two damaged copies of the lab (full `research/` + `docs/` trees
in tmp dirs) prove the checks catch real breaks:

| damage | caught as |
| --- | --- |
| study 001's only trial record (T0001) deleted | `edge_trial` T0001 (3 edges), `record_trial` T0001, `trial_gap` T0001, `hypothesis_no_trial` H0001 |
| decision record DR-E0023's edge id changed to E9999 | `record_edge` E9999, referrer `decision record DR-E0023` |

Synthetic unit tests cover the remaining check classes (missing
test key, template rank mismatch, candidate not in registry,
unreserved trial gap, hypothesis with no trial and no pending
edge, review coverage gap, unknown audit edge, missing
availability file/node, unknown `used_by` directory, missing
study report). Pending and descriptive edges correctly need no
test key.

A third copy, with study 002's `panel-summary.json` and
`manifest.json` removed, builds without crashing and records
both files in `missing_optional` — absence is recorded, not a
failure.

## Findings

One genuine gap, already known from the 6d review and restated
here rather than discovered: study 005
(`fomc-event-study-005`) has no `trials.jsonl.anchor`, so
truncation of its ledger cannot be ruled out by an anchor. It
is the catalog's only `missing_optional` entry and appears in
the lab report's pending items. No repair was made (the
librarian never modifies source records).

## Limitations

- **The catalog trusts the records it reads**: it checks that
  references resolve, not that the referenced values are
  correct. A wrong-but-resolving number would pass; catching
  wrong numbers is the 6d reviewer's job (report–ledger
  comparison), and the librarian quotes its verdicts.
- **The primary test is the first Holm-family entry** (the same
  convention as the 6d reviewer, true for all 11 completed
  trials). A future trial that orders its family differently
  would be misread by the primary-test summary.
- **Reserved trial ids rest on a numbering convention**: a gap
  is treated as reserved only when its number matches a
  hypothesis with no trial yet and a pending edge (T0003 for
  H0003). The convention — a hypothesis's first trial takes its
  number — holds for all 12 hypotheses so far.
- **Freshness is a probe-time snapshot**: panel status comes
  from the 6b evidence report (probed 2026-11-18T21:45Z), not
  from a live check. Post-probe updates are recorded only when
  a committed record exists (currently just the VXN re-fetch).
- **The catalog covers the seven empirical studies**: stages
  without trial ledgers (microstructure, portfolio, planner,
  evidence, scaffolding, review) appear only through their
  outputs (registry, ranking, sources, review report), not as
  catalogued studies.

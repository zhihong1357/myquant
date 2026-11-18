# Market graph and edge registry

The registry (`registry.json`) records every transmission edge tested by a
myquant study: which directed pair, at which frequency and condition, with
which evidence — plus the preregistered-but-untested edges, the
descriptive-only checks, and the directed pairs nobody has tested yet.

## The one rule: generate, never hand-copy

The registry is **generated** by `build_graph.py` from the studies'
committed artifacts:

- trial ledgers (`research/<study>/trials.jsonl`) — all statistics;
- preregistrations (`research/<study>/hypotheses/registrations/`) — design,
  fingerprints, source versions, fixed parameters;
- the H0003 sample check (`research/lowvol-002/h0003-sample-check.json`) —
  forward-sample counts for the pending edge;
- instrument catalogs (`research/<study>/catalog/instruments/`) — node names
  and asset classes.

The builder is deterministic and offline: it reads only local files, never
the network and never market data. Running it twice produces byte-identical
output. A registry that drifts from the ledgers is a bug, and
`tests/test_graph.py` fails the build if the committed registry does not
match a fresh builder run.

The only hand-written part is the *correspondence*: `EDGE_SPECS` in
`build_graph.py` declares which ledger test becomes which edge (source,
target, frequency, condition, method, control). No number lives there —
every statistic is read from the ledger at build time. The builder refuses
to run if any Holm-family test in a ledger has no edge spec, so no tested
edge can silently go unregistered.

## Rebuilding

From the repo root:

```bash
.venv/bin/python research/graph/build_graph.py
```

This regenerates `research/graph/registry.json` and the generated section
of `docs/market-graph.md` (between the `BEGIN GENERATED` / `END GENERATED`
markers). Commit both files together.

## Adding a new study's edges

1. Finish the study first: preregistration, trial ledger, report.
2. In `build_graph.py`, add the study to `STUDIES` (hypothesis id,
   registration version, trial id, report path).
3. Add one `EdgeSpec` per Holm-family test, in ledger order. Give the new
   edges the next free ids (`E0014`, `E0015`, …) — never reuse or renumber
   an existing id.
4. If the study adds instruments, extend `SHORT_LABELS` and make sure the
   study's catalog carries the new instruments.
5. If the study has a descriptive-only check worth recording, add a
   builder function for it (mirroring `_build_cross_venue_edge` /
   `_build_reverse_placebo_edge`) with status `DESCRIPTIVE` and no verdict.
6. Re-run the builder and commit the regenerated registry and doc.

## Edge records are versioned and immutable

An edge record carries a `version` (v1 for all current edges). A
correction produces a new version of the record; old versions are never
edited in place. The registry itself carries a `content_hash` (SHA-256
over the canonical JSON of its contents); loading a tampered registry
fails validation.

## Statuses

- `REJECTED` / `SUPPORTED`: verdicts from a completed test family.
- `PENDING`: preregistered, no trial has run. Carries a forward-sample
  record (counts only), never statistics.
- `DESCRIPTIVE`: a descriptive check only. Never in a test family, no
  verdict, no Holm-adjusted p-value. Must never be cited as test evidence.

Trial-level metrics (holdout OOS R², cost gate) attach to the primary edge
of each trial only; other edges in the same trial carry a note saying so.
Attaching a trial-level number to a non-primary edge would imply a
measurement that was never made.

## Querying

```python
from myquant.graph import EdgeStatus, MarketGraph

graph = MarketGraph.from_file("research/graph/registry.json")
graph.edges_by(source="crypto:btc-usdt-perp", status=EdgeStatus.REJECTED)
graph.edge_between("index:tyvix", "index:vix")
graph.untested_candidates(target="crypto:eth-usdt-perp")
graph.summary()
```

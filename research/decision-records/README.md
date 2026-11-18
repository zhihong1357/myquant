# Statistical decision records (Stage 2B)

One structured record per lab conclusion, closing the
"evidence-backed statistical decision records" item in both Stage 2A
and Stage 2B of the roadmap:

- 6 `supported_edge` records, one per SUPPORTED edge
  (DR-E0023, DR-E0026, DR-E0030, DR-E0031, DR-E0032, DR-E0033);
- 9 `rejected_hypothesis` records, one per rejected primary hypothesis
  (DR-H0001, DR-H0002, DR-H0004, DR-H0005, DR-H0006, DR-H0007,
  DR-H0008, DR-H0009, DR-H0012).

H0010 and H0011 are SUPPORTED hypotheses; their records are the
primary-edge records DR-E0030 and DR-E0032 (plus the secondary-edge
record DR-E0031 for H0010's ETH leg). H0003 is pending (forward test
not yet run) and has no record.

## Contents

- `build_decision_records.py` — the generator. Deterministic and
  offline: reads the graph registry, the trial ledgers and the Stage
  2B audit summary. Every number in every record is read
  programmatically from those files; the only hand-written content is
  the correspondence (which edge/hypothesis each record covers), the
  conclusion-scope sentences, and the qualitative limitations.
- `records/DR-*.json` — the 15 generated records (schema v1; see the
  builder's docstring for the schema).

## Regenerate

From the repo root (requires the audit summary to exist — run
`research/statistical-audit-2b/audit.py` first if it is missing):

```sh
.venv/bin/python research/decision-records/build_decision_records.py
```

Re-running reproduces all records byte-identically (no timestamps).
`tests/test_decision_records.py` enforces this with a drift test and
independently verifies every committed record's key numbers against
its trial ledger.

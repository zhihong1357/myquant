# Adversarial reviewer validation (Stage 6d)

Validated at: 2026-11-19T17:28:01.794967+00:00

## What was validated

1. **Full-lab review**: the reviewer ran over all eight empirical studies and all trial ledgers (16 records: 12 completed, 3 failed, 1 reserved). The review itself is in `review_report.md` / `review_report.json` in this directory.
2. **Adversarial fixtures**: six deliberately broken fixtures in tmp dirs, each isolating one violation. Every fixture must FAIL with the correct reason — passing only clean studies does not count as validation.
3. **Rounding-margin diagnostic**: the report check compares numbers within the tolerance implied by the report's stated precision; the diagnostic shows the failures are not rounding noise.

## Full-lab review summary

- Checks run: 154
- PASS: 129
- FAIL: 0
- UNVERIFIED: 8
- NOTE: 17

### Per-check breakdown

| check | pass | fail | unverified | note |
| --- | --- | --- | --- | --- |
| `hypothesis_state` | 17 | 0 | 0 | 0 |
| `ledger_anchor` | 12 | 0 | 1 | 0 |
| `ledger_chain` | 13 | 0 | 0 | 0 |
| `multiple_testing` | 17 | 0 | 0 | 0 |
| `pit_spot_check` | 6 | 0 | 7 | 0 |
| `power_note` | 0 | 0 | 0 | 17 |
| `prereg_binding` | 20 | 0 | 0 | 0 |
| `registry_events` | 13 | 0 | 0 | 0 |
| `report_ledger` | 13 | 0 | 0 | 0 |
| `trial_sequence` | 1 | 0 | 0 | 0 |
| `verdict_consistency` | 17 | 0 | 0 | 0 |

### The FAILs

Each FAIL below is a genuine disagreement between a record and the source it should agree with, with located evidence. The reviewer reports them; it does not fix the studies (fixes are a separate delivery decision). The analyst's reading of these failures — what caused them and whether they matter — is in `docs/research-intelligence.md` §4, not in this generated report.

None.


### The UNVERIFIEDs

UNVERIFIED means the check could not be performed — it is not a pass. Each entry states why.

- **btc-eth-001** `pit_spot_check`: no PIT parquet retained locally for this study
  - btc-eth-001: data/cache/btc-eth-001/ holds no *.parquet batches
- **lowvol-002** `pit_spot_check`: no PIT parquet retained locally for this study
  - lowvol-002: data/cache/lowvol-002/ holds no *.parquet batches
- **move-vix-003** `pit_spot_check`: no PIT parquet retained locally for this study
  - move-vix-003: data/cache/move-vix-003/ holds no *.parquet batches
- **options-expiry-004** `pit_spot_check`: no PIT parquet retained locally for this study
  - options-expiry-004: data/cache/options-expiry-004/ holds no *.parquet batches
- **fomc-event-study-005** `ledger_anchor`: no anchor file; truncation undetectable
  - research/fomc-event-study-005/trials.jsonl: trials.jsonl.anchor absent, the chain verifies tampering only
- **fomc-event-study-005** `pit_spot_check`: no PIT parquet retained locally for this study
  - fomc-event-study-005: data/cache/fomc-event-study-005/ holds no *.parquet batches
- **macro-windows-006** `pit_spot_check`: no PIT parquet retained locally for this study
  - macro-windows-006: data/cache/macro-windows-006/ holds no *.parquet batches
- **publication-lag-007** `pit_spot_check`: no PIT parquet retained locally for this study
  - publication-lag-007: data/cache/publication-lag-007/ holds no *.parquet batches

### Report coverage

- 78 report rules across the 13 reports; 78 rows verified, 0 rows disagree.
- 498 numeric cells compared (window-count and bootstrap-CI cells compared separately).

## Adversarial fixtures

| fixture | check | verdict | reason |
| --- | --- | --- | --- |
| tampered ledger record | `ledger_chain` | fail | hash chain verification failed: record hash mismatch at line 1 |
| fingerprint mismatch vs registry | `prereg_binding` | fail | trial hypothesis fingerprint does not match preregistration |
| wrong adjusted p-value | `multiple_testing` | fail | adjusted p-value for 'daily_btc_eth' does not recompute |
| verdict contradicts metrics | `verdict_consistency` | fail | recorded 'supported' flag contradicts the recorded criteria |
| PIT violation (available_at < event_time) | `pit_spot_check` | fail | 1 observation(s) with available_at < event_time (showing first 1) |
| failed trial T0006 deleted | `trial_sequence` | fail | trial ID(s) missing from the ledgers: T0006 |

**6/6 fixtures caught.** All six violation classes fail with the correct reason.

## Rounding-margin diagnostic

- Numeric cells compared: 498
- Cells outside tolerance: 0
- Highest passing ratio (|diff| / tolerance): 0.999
- Lowest failing ratio: none (no cell outside tolerance)

The highest passing ratio is a correctly rounded value sitting near its rounding boundary — expected, since rounding residuals spread uniformly in [0, 1]. No cell falls outside tolerance. (The study 004 bootstrap-CI bound is compared through the CI path, not this numeric path, so it does not appear in these counts.)

Largest ratios:

- 0.999: credit-spread-spx-008 T0016 daily_baa10y_spx_naive (raw p)
- 0.996: credit-spread-tyvix-009 T0017 daily_baa10y_tyvix_no_factor (partial R²)
- 0.993: credit-spread-tyvix-009 T0017 daily_tyvix_baa10y_reverse (partial R²)
- 0.99: fomc-event-study-005 T0009 baa10y_on_dgs10 (slope)
- 0.987: btc-eth-001 T0001 daily_btc_sol_no_factor (SE)
- 0.983: btc-eth-001 T0001 daily_btc_sol (incr R²)

## Limitations

- **Report coverage is table-bound**: only the 52 results-table rows with explicit rules are checked. Prose numbers, descriptive split tables and the verdict-criteria tables are not mechanically compared; a discrepancy there would not be caught.
- **The primary test is the first Holm-family entry**: the verdict check re-derives the primary criteria from `metrics["holm"][0]`. This holds for all 12 completed trials in the lab, and the report check independently confirms each primary test's identity from the report tables — but a future trial that orders its family differently would be misread.
- **PIT coverage depends on retained data**: the check runs only where parquet batches still exist. The seven older study caches are gone, so the lab's PIT discipline is verified only for study 008 (the only retained cache) and unverified for the rest.
- **Truncation needs anchors**: study 005 has no anchor file, so a deleted trailing record in its ledger would pass the chain check; only the trial-ID sequence check would notice (and only if the deleted record's ID left a gap).
- **The reviewer trusts the registry's own verification**: registration and event-log integrity come from the repo's `HypothesisRegistry` code, not from an independent reimplementation. A bug shared by the registry and the reviewer would be invisible to both.

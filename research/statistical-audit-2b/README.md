# Lab-wide statistical audit (Stage 2B)

Post-hoc second-layer analysis of the lab's seven completed studies.
It does **not** change any preregistered verdict and does **not** touch
the market graph: the graph records each study's own verdict, and this
audit answers the separate question of the lab's overall
false-discovery posture, plus calibration, power and overfitting
diagnostics for the lab's methods.

## Contents

- `audit.py` — the generator. Deterministic and offline: reads only
  committed local files (the graph registry, trial ledgers), never the
  network and never market data. Every number in the outputs is
  computed from those files or from fixed-seed simulations; the only
  hand-written content is the edge correspondence (which primary edge
  belongs to which trial) and the two annotation caveats (E0026
  mechanicality, E0030 bootstrap marginality), verified against the
  registry/ledgers at run time.
- `summary.json` — machine-readable audit results (generated).
- `report.md` — the audit report (generated).

## Regenerate

From the repo root:

```sh
.venv/bin/python research/statistical-audit-2b/audit.py
```

Re-running reproduces both outputs byte-identically (no timestamps).
`tests/test_statistical_audit.py` enforces this with a drift test.

## Independent recomputation

The headline numbers were re-derived independently (plain Python,
stdlib only, no repo imports) from the registry and the trial ledgers:
all 36 lab-wide Holm and BH adjusted p-values (including the 6
supported edges' values and the 4/6 Holm, 5/6 BH survivor counts),
the 8 raw rejections, the Storey pi0 estimate, all 18 DSR
reference-table cells (the Bailey & Lopez de Prado formula
re-implemented from scratch), every lead-lag / CAR / mean-comparison
MDE and every observed effect against the ledger test records, and
all six calibration Monte Carlo standard errors. All checks matched
the generated outputs. (The review also fixed one generator bug: the
section-2 reading judged Holm FWER control by a strict `<= nominal`
comparison, which failed on simulation noise — the independent
variant measured 0.0504 with MC SE 0.0031 — and the criterion is now
"not significantly above nominal", consistent with section 5.)

## Headline results

- Lab-wide family: 36 tested edges. Under lab-wide Holm correction,
  4 of the 6 supported edges remain significant; under lab-wide BH,
  5 of 6. Expected false positives at the uncorrected 5% level: 1.8
  (observed raw rejections: 8).
- Calibration: the HAC test holds its nominal size, Holm controls
  FWER, and the block-bootstrap interval is approximately calibrated
  at the lab's sample sizes.
- Power: the lead-lag partial-R² MDE at n = 1,414 is 0.0055 —
  essentially the lab's 0.005 effect-size threshold. Every observed
  lead-lag effect sits below its MDE.
- PBO/DSR are validated on synthetic data only: the lab has no stored
  strategy-return series, so no lab-real-data PBO/DSR is computed.

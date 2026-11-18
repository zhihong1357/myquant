# Stage 6a hypothesis-planner validation report

- Validated at: 2026-11-18T20:58:37.295434+00:00
- Offline and deterministic: fixed inputs, no network, no clock reads inside the scoring. Re-running reproduces `ranking.json` byte-identically and this report except this timestamp line.
- Registry: 12 nodes, 39 edges, 123 candidates; content hash `3d0515bd4fa1...`
- Availability: 12 nodes, all verified from study manifests (see `data_availability.json`); no unknown nodes.

## What the planner is (and is not)

The planner sorts untested pairs by three explicit components — adjacency to supported edges, data availability, power feasibility — under declared weights. It does not predict which hypothesis will be supported: adjacency is a graph fact, not evidence, and the ranking is a heuristic. The top-10 below is the first ten pairs in (source, target) order among the pairs tied at the top score — read it as 'these pass every stated screen', not as 'these are the ten most promising hypotheses'.

## MDE cross-check (planner formulas vs the Stage 2B audit)

Every audit MDE entry recomputed from its sample size with the planner's formulas (same analytic functions):

- PASS: lead-lag partial R² MDE (E0001, n=1414): audit 0.00552019, recomputed 0.00552019
- PASS: lead-lag partial R² MDE (E0004, n=1133): audit 0.00687986, recomputed 0.00687986
- PASS: lead-lag partial R² MDE (E0008, n=4327): audit 0.00181065, recomputed 0.00181065
- PASS: lead-lag partial R² MDE (E0014, n=2124): audit 0.00368172, recomputed 0.00368172
- PASS: lead-lag partial R² MDE (E0027, n=2124): audit 0.00368172, recomputed 0.00368172
- PASS: lead-lag partial R² MDE (E0037, n=1468): audit 0.00531821, recomputed 0.00531821
- PASS: cross-section R² MDE (E0024, n=135): audit 0.0549453, recomputed 0.0549453
- PASS: standardized CAR MDE (E0019, n=135): audit 0.214002, recomputed 0.214002
- PASS: standardized CAR MDE (E0023, n=135): audit 0.214002, recomputed 0.214002
- PASS: standardized CAR MDE (E0032, n=135): audit 0.214002, recomputed 0.214002
- PASS: standardized CAR MDE (E0033, n=135): audit 0.214002, recomputed 0.214002
- PASS: Cohen's d MDE (E0017, n=280/1845): audit 0.179683, recomputed 0.179683
- PASS: Cohen's d MDE (E0018, n=280/1845): audit 0.179683, recomputed 0.179683
- PASS: Cohen's d MDE (E0030, n=116/2009): audit 0.267525, recomputed 0.267525
- PASS: Cohen's d MDE (E0031, n=116/2009): audit 0.267525, recomputed 0.267525

## Ranking summary (default weights)

- Candidates: 123
- Ranked: 99
- Excluded by the anti-retest guard: 0
- Unrankable: 24

Score tiers (default weights): 1.00 x 34, 0.80 x 9, 0.70 x 44, 0.60 x 2, 0.50 x 10.

The top tier holds 34 pairs at 1.00: every component saturated (adjacent to a supported edge, both panels verified, MDE below the lab threshold). The top-10 is the first ten of that tier in lexicographic order — the tie, not the weights, decides it.

## Top-10 shortlist

### 1. credit:baa-10y-spread -> index:sp500

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 5967 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00131 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0026; decision records: DR-E0026
- Preregistration draft: `templates/credit-baa-10y-spread__index-sp500.json`

### 2. credit:baa-10y-spread -> index:tyvix

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 4341 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00180 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0023, E0026, E0032; decision records: DR-E0023, DR-E0026, DR-E0032
- Preregistration draft: `templates/credit-baa-10y-spread__index-tyvix.json`

### 3. credit:baa-10y-spread -> index:vix

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 5967 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00131 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0026, E0033; decision records: DR-E0026, DR-E0033
- Preregistration draft: `templates/credit-baa-10y-spread__index-vix.json`

### 4. credit:baa-10y-spread -> index:vxn

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 4341 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00180 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0026; decision records: DR-E0026
- Preregistration draft: `templates/credit-baa-10y-spread__index-vxn.json`

### 5. credit:baa-10y-spread -> rates:us-10y-yield

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 5967 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00131 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0026; decision records: DR-E0026
- Preregistration draft: `templates/credit-baa-10y-spread__rates-us-10y-yield.json`

### 6. crypto:btc-usdt-perp -> index:btc-dvol

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 2064 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00379 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0030; decision records: DR-E0030
- Preregistration draft: `templates/crypto-btc-usdt-perp__index-btc-dvol.json`

### 7. crypto:btc-usdt-perp -> index:eth-dvol

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 2064 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00379 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0030; decision records: DR-E0030
- Preregistration draft: `templates/crypto-btc-usdt-perp__index-eth-dvol.json`

### 8. crypto:eth-usdt-perp -> crypto:btc-usdt-perp

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 2126 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00368 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0030, E0031; decision records: DR-E0030, DR-E0031
- Preregistration draft: `templates/crypto-eth-usdt-perp__crypto-btc-usdt-perp.json`

### 9. crypto:eth-usdt-perp -> crypto:sol-usdt-perp

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 2126 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00368 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0031; decision records: DR-E0031
- Preregistration draft: `templates/crypto-eth-usdt-perp__crypto-sol-usdt-perp.json`

### 10. crypto:eth-usdt-perp -> index:btc-dvol

- Suggested test: lead_lag (daily), mechanism transmission. Default first test for an untested cross-instrument pair: unconditional daily lead-lag transmission.
- Score: 1.00 (adjacency 1.0, data 1.0, power 1.0)
- Joint n (estimated): 2064 — estimated daily rows in the overlap window (pro-rata by days, sparser panel binds)
- MDE: 0.00379 (partial_r_squared, threshold 0.005)
- Adjacent supported edges: E0031; decision records: DR-E0031
- Preregistration draft: `templates/crypto-eth-usdt-perp__index-btc-dvol.json`

## Excluded (anti-retest guard)

None. The guard cannot fire on the current registry: candidates are by construction pairs with no tested edge, so no candidate matches a tested (pair, test type, condition). The guard is a safety net for future registries and manually supplied candidate lists; it is enforced in code and tested on synthetic inputs (`tests/test_planner.py`).

## Unrankable

- crypto:btc-usdt-perp -> index:tyvix: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- crypto:btc-usdt-perp -> index:vxn: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- crypto:eth-usdt-perp -> index:tyvix: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- crypto:eth-usdt-perp -> index:vxn: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- crypto:sol-usdt-perp -> index:tyvix: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- crypto:sol-usdt-perp -> index:vxn: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:btc-dvol -> index:tyvix: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:btc-dvol -> index:vxn: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:eth-dvol -> index:tyvix: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:eth-dvol -> index:vxn: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:tyvix -> crypto:btc-usdt-perp: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:tyvix -> crypto:eth-usdt-perp: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:tyvix -> crypto:sol-usdt-perp: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:tyvix -> index:btc-dvol: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:tyvix -> index:eth-dvol: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:tyvix -> macro:cpi-mom: no overlapping panel window for the suggested lead_lag test (calendar months in the overlap of the monthly panel with the other panel)
- index:vxn -> crypto:btc-usdt-perp: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:vxn -> crypto:eth-usdt-perp: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:vxn -> crypto:sol-usdt-perp: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:vxn -> index:btc-dvol: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:vxn -> index:eth-dvol: no overlapping panel window for the suggested lead_lag test (no overlapping panel window)
- index:vxn -> macro:cpi-mom: no overlapping panel window for the suggested lead_lag test (calendar months in the overlap of the monthly panel with the other panel)
- macro:cpi-mom -> index:tyvix: no overlapping panel window for the suggested lead_lag test (estimated daily rows of the target panel inside the step-predictor window (first release to panel end))
- macro:cpi-mom -> index:vxn: no overlapping panel window for the suggested lead_lag test (estimated daily rows of the target panel inside the step-predictor window (first release to panel end))

All 24 unrankable pairs are TYVIX/VXN against post-2020-only nodes (crypto perpetuals, DVOL, CPI): the TYVIX panel ends 2020-05-15 (discontinued) and the VXN panel is verified only through 2020-05-15, while the crypto/DVOL/CPI panels start in 2021 — there is no overlapping window to test on. Re-fetching VXN past 2020 (the series continues on FRED) would make 12 of these pairs rankable; TYVIX cannot be extended.

## Weight sensitivity

### default (adjacency 0.4 / data 0.3 / power 0.3)

- Top-10 intersection with default: 10/10
- Entered the top-10: none
- Left the top-10: none

### adjacency-heavy (0.6 / 0.2 / 0.2)

- Top-10 intersection with default: 10/10
- Entered the top-10: none
- Left the top-10: none

### power-heavy (0.2 / 0.2 / 0.6)

- Top-10 intersection with default: 10/10
- Entered the top-10: none
- Left the top-10: none

Conclusion: the top-10 is weight-invariant in this run. The 34 pairs in the top tier saturate all three components, so they score 1.00 under any weights, and the top-10 is the same lexicographic slice of that tier under every weighting. The weights only reorder the lower tiers (under adjacency-heavy weights the adjacency-1/power-0 tier outranks the adjacency-0.5/power-1 tier; under power-heavy weights it is the other way round). The ranking's discriminating power is limited by its coarse components — a finer power component (e.g. a continuous MDE margin) would be needed to break the 34-way tie, and that is a design decision for a later planner version, not something to smuggle in here.

## Mechanism distribution

- All ranked pairs: transmission 92, cross-section 7.
- Top-10: transmission 10.

Cross-section pairs (7, all DGS10-sourced) sit at ranks 80–86: their power component is 0 at every available event count (MDE 0.1514 at 44 events, 0.1485 at 45 events, 0.0546 at 136 events, vs the 0.05 threshold), so they cannot reach the top tier. Vol-level, event-response and regime-conditional labels do not occur among candidates: level and event-response tests are self-loops (never candidates) and regime-conditional designs are follow-ups, not first tests.

## Full ranking (default weights)

| Rank | Pair | Test | Score | Adj | Data | Power | Joint n | MDE | Mechanism |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | credit:baa-10y-spread -> index:sp500 | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5967 | 0.00131 | transmission |
| 2 | credit:baa-10y-spread -> index:tyvix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4341 | 0.00180 | transmission |
| 3 | credit:baa-10y-spread -> index:vix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5967 | 0.00131 | transmission |
| 4 | credit:baa-10y-spread -> index:vxn | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4341 | 0.00180 | transmission |
| 5 | credit:baa-10y-spread -> rates:us-10y-yield | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5967 | 0.00131 | transmission |
| 6 | crypto:btc-usdt-perp -> index:btc-dvol | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 7 | crypto:btc-usdt-perp -> index:eth-dvol | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 8 | crypto:eth-usdt-perp -> crypto:btc-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2126 | 0.00368 | transmission |
| 9 | crypto:eth-usdt-perp -> crypto:sol-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2126 | 0.00368 | transmission |
| 10 | crypto:eth-usdt-perp -> index:btc-dvol | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 11 | crypto:eth-usdt-perp -> index:eth-dvol | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 12 | crypto:sol-usdt-perp -> crypto:btc-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2126 | 0.00368 | transmission |
| 13 | crypto:sol-usdt-perp -> crypto:eth-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2126 | 0.00368 | transmission |
| 14 | index:btc-dvol -> crypto:btc-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 15 | index:btc-dvol -> crypto:eth-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 16 | index:eth-dvol -> crypto:btc-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 17 | index:eth-dvol -> crypto:eth-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 18 | index:sp500 -> credit:baa-10y-spread | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5967 | 0.00131 | transmission |
| 19 | index:sp500 -> index:tyvix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4363 | 0.00180 | transmission |
| 20 | index:sp500 -> index:vix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 6007 | 0.00130 | transmission |
| 21 | index:sp500 -> rates:us-10y-yield | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5972 | 0.00131 | transmission |
| 22 | index:tyvix -> credit:baa-10y-spread | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4341 | 0.00180 | transmission |
| 23 | index:tyvix -> index:sp500 | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4363 | 0.00180 | transmission |
| 24 | index:tyvix -> rates:us-10y-yield | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4344 | 0.00180 | transmission |
| 25 | index:vix -> credit:baa-10y-spread | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5967 | 0.00131 | transmission |
| 26 | index:vix -> index:sp500 | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 6007 | 0.00130 | transmission |
| 27 | index:vix -> index:tyvix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4363 | 0.00180 | transmission |
| 28 | index:vix -> index:vxn | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4372 | 0.00179 | transmission |
| 29 | index:vix -> rates:us-10y-yield | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 5972 | 0.00131 | transmission |
| 30 | index:vxn -> credit:baa-10y-spread | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4341 | 0.00180 | transmission |
| 31 | index:vxn -> index:tyvix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4363 | 0.00180 | transmission |
| 32 | index:vxn -> index:vix | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4372 | 0.00179 | transmission |
| 33 | index:vxn -> rates:us-10y-yield | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 4344 | 0.00180 | transmission |
| 34 | macro:cpi-mom -> crypto:eth-usdt-perp | lead_lag (daily) | 1.00 | 1.0 | 1.0 | 1.0 | 2126 | 0.00368 | transmission |
| 35 | crypto:sol-usdt-perp -> index:btc-dvol | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 36 | crypto:sol-usdt-perp -> index:eth-dvol | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 37 | index:btc-dvol -> crypto:sol-usdt-perp | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 38 | index:eth-dvol -> crypto:sol-usdt-perp | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2064 | 0.00379 | transmission |
| 39 | index:sp500 -> index:vxn | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 4370 | 0.00179 | transmission |
| 40 | index:vxn -> index:sp500 | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 4370 | 0.00179 | transmission |
| 41 | macro:cpi-mom -> crypto:sol-usdt-perp | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2126 | 0.00368 | transmission |
| 42 | macro:cpi-mom -> index:btc-dvol | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2065 | 0.00379 | transmission |
| 43 | macro:cpi-mom -> index:eth-dvol | lead_lag (daily) | 0.80 | 0.5 | 1.0 | 1.0 | 2065 | 0.00379 | transmission |
| 44 | credit:baa-10y-spread -> crypto:btc-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1454 | 0.00537 | transmission |
| 45 | credit:baa-10y-spread -> crypto:eth-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1454 | 0.00537 | transmission |
| 46 | credit:baa-10y-spread -> crypto:sol-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1454 | 0.00537 | transmission |
| 47 | credit:baa-10y-spread -> index:btc-dvol | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1412 | 0.00553 | transmission |
| 48 | credit:baa-10y-spread -> index:eth-dvol | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1412 | 0.00553 | transmission |
| 49 | credit:baa-10y-spread -> macro:cpi-mom | lead_lag (monthly) | 0.70 | 1.0 | 1.0 | 0.0 | 72 | 0.09830 | transmission |
| 50 | crypto:btc-usdt-perp -> credit:baa-10y-spread | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1454 | 0.00537 | transmission |
| 51 | crypto:btc-usdt-perp -> index:sp500 | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1464 | 0.00533 | transmission |
| 52 | crypto:btc-usdt-perp -> index:vix | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1472 | 0.00530 | transmission |
| 53 | crypto:btc-usdt-perp -> macro:cpi-mom | lead_lag (monthly) | 0.70 | 1.0 | 1.0 | 0.0 | 70 | 0.10082 | transmission |
| 54 | crypto:btc-usdt-perp -> rates:us-10y-yield | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1456 | 0.00536 | transmission |
| 55 | crypto:eth-usdt-perp -> credit:baa-10y-spread | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1454 | 0.00537 | transmission |
| 56 | crypto:eth-usdt-perp -> index:sp500 | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1464 | 0.00533 | transmission |
| 57 | crypto:eth-usdt-perp -> index:vix | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1472 | 0.00530 | transmission |
| 58 | crypto:eth-usdt-perp -> macro:cpi-mom | lead_lag (monthly) | 0.70 | 1.0 | 1.0 | 0.0 | 70 | 0.10082 | transmission |
| 59 | crypto:eth-usdt-perp -> rates:us-10y-yield | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1456 | 0.00536 | transmission |
| 60 | crypto:sol-usdt-perp -> credit:baa-10y-spread | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1454 | 0.00537 | transmission |
| 61 | crypto:sol-usdt-perp -> index:vix | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1472 | 0.00530 | transmission |
| 62 | crypto:sol-usdt-perp -> rates:us-10y-yield | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1456 | 0.00536 | transmission |
| 63 | index:btc-dvol -> credit:baa-10y-spread | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1412 | 0.00553 | transmission |
| 64 | index:btc-dvol -> index:vix | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1429 | 0.00546 | transmission |
| 65 | index:btc-dvol -> rates:us-10y-yield | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1413 | 0.00552 | transmission |
| 66 | index:eth-dvol -> credit:baa-10y-spread | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1412 | 0.00553 | transmission |
| 67 | index:eth-dvol -> index:vix | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1429 | 0.00546 | transmission |
| 68 | index:eth-dvol -> rates:us-10y-yield | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1413 | 0.00552 | transmission |
| 69 | index:sp500 -> crypto:btc-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1464 | 0.00533 | transmission |
| 70 | index:sp500 -> crypto:eth-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1464 | 0.00533 | transmission |
| 71 | index:vix -> crypto:btc-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1472 | 0.00530 | transmission |
| 72 | index:vix -> crypto:eth-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1472 | 0.00530 | transmission |
| 73 | index:vix -> crypto:sol-usdt-perp | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1472 | 0.00530 | transmission |
| 74 | index:vix -> index:btc-dvol | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1429 | 0.00546 | transmission |
| 75 | index:vix -> index:eth-dvol | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1429 | 0.00546 | transmission |
| 76 | index:vix -> macro:cpi-mom | lead_lag (monthly) | 0.70 | 1.0 | 1.0 | 0.0 | 72 | 0.09830 | transmission |
| 77 | macro:cpi-mom -> credit:baa-10y-spread | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1460 | 0.00535 | transmission |
| 78 | macro:cpi-mom -> index:vix | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1478 | 0.00528 | transmission |
| 79 | macro:cpi-mom -> rates:us-10y-yield | lead_lag (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 1461 | 0.00534 | transmission |
| 80 | rates:us-10y-yield -> crypto:btc-usdt-perp | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 45 | 0.14852 | cross-section |
| 81 | rates:us-10y-yield -> crypto:eth-usdt-perp | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 45 | 0.14852 | cross-section |
| 82 | rates:us-10y-yield -> crypto:sol-usdt-perp | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 45 | 0.14852 | cross-section |
| 83 | rates:us-10y-yield -> index:btc-dvol | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 44 | 0.15138 | cross-section |
| 84 | rates:us-10y-yield -> index:eth-dvol | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 44 | 0.15138 | cross-section |
| 85 | rates:us-10y-yield -> index:tyvix | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 136 | 0.05456 | cross-section |
| 86 | rates:us-10y-yield -> index:vxn | cross_section (daily) | 0.70 | 1.0 | 1.0 | 0.0 | 136 | 0.05456 | cross-section |
| 87 | rates:us-10y-yield -> macro:cpi-mom | lead_lag (monthly) | 0.70 | 1.0 | 1.0 | 0.0 | 72 | 0.09830 | transmission |
| 88 | index:btc-dvol -> index:eth-dvol | lead_lag (daily) | 0.60 | 0.0 | 1.0 | 1.0 | 2065 | 0.00379 | transmission |
| 89 | index:eth-dvol -> index:btc-dvol | lead_lag (daily) | 0.60 | 0.0 | 1.0 | 1.0 | 2065 | 0.00379 | transmission |
| 90 | crypto:sol-usdt-perp -> index:sp500 | lead_lag (daily) | 0.50 | 0.5 | 1.0 | 0.0 | 1464 | 0.00533 | transmission |
| 91 | crypto:sol-usdt-perp -> macro:cpi-mom | lead_lag (monthly) | 0.50 | 0.5 | 1.0 | 0.0 | 70 | 0.10082 | transmission |
| 92 | index:btc-dvol -> index:sp500 | lead_lag (daily) | 0.50 | 0.5 | 1.0 | 0.0 | 1421 | 0.00549 | transmission |
| 93 | index:btc-dvol -> macro:cpi-mom | lead_lag (monthly) | 0.50 | 0.5 | 1.0 | 0.0 | 68 | 0.10348 | transmission |
| 94 | index:eth-dvol -> index:sp500 | lead_lag (daily) | 0.50 | 0.5 | 1.0 | 0.0 | 1421 | 0.00549 | transmission |
| 95 | index:eth-dvol -> macro:cpi-mom | lead_lag (monthly) | 0.50 | 0.5 | 1.0 | 0.0 | 68 | 0.10348 | transmission |
| 96 | index:sp500 -> crypto:sol-usdt-perp | lead_lag (daily) | 0.50 | 0.5 | 1.0 | 0.0 | 1464 | 0.00533 | transmission |
| 97 | index:sp500 -> index:btc-dvol | lead_lag (daily) | 0.50 | 0.5 | 1.0 | 0.0 | 1421 | 0.00549 | transmission |
| 98 | index:sp500 -> index:eth-dvol | lead_lag (daily) | 0.50 | 0.5 | 1.0 | 0.0 | 1421 | 0.00549 | transmission |
| 99 | index:sp500 -> macro:cpi-mom | lead_lag (monthly) | 0.50 | 0.5 | 1.0 | 0.0 | 72 | 0.09830 | transmission |

## Limitations

- The ranking is a heuristic with coarse components: 34 pairs tie at the top score, so the top-10 is decided by the lexicographic tie-break, not by any discriminating evidence. Do not read it as a prediction.
- Joint sample sizes are estimates (pro-rata by days from the verified per-node panels), not verified joint counts. The true joint row count must be confirmed when the study panel is built; the preregistration drafts mark it TODO.
- The power component uses the analytic normal-approximation MDE at 80% power, α = 0.05, and ignores HAC/autocorrelation adjustments that would raise the true MDE (the audit's own caveat: the lead-lag MDE at n = 1,414 is essentially the lab's 0.005 threshold). A pair scored power 1 is 'detectable in principle', not 'powered in practice'.
- CPI-as-source pairs use daily rows for the MDE, matching the H0012 audit treatment; the effective sample size is 69 distinct step values, so their power scores are optimistic. Each such draft carries the caveat.
- Event counts for cross-section designs are statement counts in the overlap window after an 84-calendar-day warm-up approximating the 60-trading-day estimation window; events dropped for data gaps (e.g. the 2004-11-10 DGS10 gap in study 005) are not subtracted.
- VXN is verified only through 2020-05-15; re-fetching it would change 12 pairs from unrankable to ranked. TYVIX cannot be extended (discontinued).
- The planner knows nothing about economics: it cannot tell a plausible mechanism from a spurious pair, and it does not try. The mechanism label is a classification of the suggested design, not a judgement about the market.

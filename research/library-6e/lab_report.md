# MyQuant lab status report

Generated at: 2026-11-19T17:28:45.968505+00:00

Read-only report generated from the lab's committed records by the research librarian (Stage 6e). Every number below is derived by reading a record — nothing is transcribed by hand. The report states what the records say; it draws no new conclusions, and a supported edge is a statistical result, not a tradeable signal.

## Studies

One row per completed trial. The primary test is the first entry of the trial's recorded Holm family; the effect, adjusted p-value and sample size come from the trial ledger.

| study | trial | hypothesis | verdict | primary test | effect | adj p | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| btc-eth-001 | T0001 | H0001 | REJECTED | daily_btc_eth | coef 0.0251765 (partial R² 0.000109905) | 1 | 1414 |
| lowvol-002 | T0002 | H0002 | REJECTED | daily_btc_sol_interaction | coef 0.221701 (partial R² 0.00375922) | 0.283145 | 1133 |
| move-vix-003 | T0004 | H0004 | REJECTED | daily_tyvix_vix | coef -0.00934091 (partial R² 3.48403e-05) | 1 | 4327 |
| options-expiry-004 | T0005 | H0005 | REJECTED | daily_btc_eth_interaction | coef -0.0358324 (partial R² 8.3656e-05) | 0.693823 | 2124 |
| options-expiry-004 | T0007 | H0006 | REJECTED | btc_mean_abs_return_comparison | effect ratio 1.00006 | 1 | 2125 |
| fomc-event-study-005 | T0009 | H0008 | REJECTED | spx_on_dgs10 | slope 0.000117383 (R² 0.00571466) | 0.726243 | 135 |
| fomc-event-study-005 | T0010 | H0007 | REJECTED | vix_car | std mean CAR -0.150685 (mean CAR -0.0155174) | 0.159962 | 135 |
| macro-windows-006 | T0011 | H0009 | REJECTED | daily_btc_eth_interaction | coef 0.000290488 (partial R² 3.08126e-09) | 1 | 2124 |
| macro-windows-006 | T0012 | H0010 | SUPPORTED | btc_mean_abs_return_comparison | effect ratio 1.25043 | 0.00981768 | 2125 |
| publication-lag-007 | T0013 | H0011 | SUPPORTED | tyvix_lagged_car | std mean CAR -0.515657 (mean CAR -0.030216) | 5.20144e-09 | 135 |
| publication-lag-007 | T0015 | H0012 | REJECTED | spx_daily | coef -0.0374021 (partial R² 0.000102239) | 0.754874 | 1468 |
| credit-spread-spx-008 | T0016 | H0013 | REJECTED | daily_baa10y_spx | coef 1.80489e-05 (partial R² 2.19264e-05) | 0.893517 | 5957 |
| credit-spread-tyvix-009 | T0017 | H0014 | REJECTED | daily_baa10y_tyvix | coef -0.000125573 (partial R² 6.10033e-05) | 0.753984 | 4327 |
| credit-spread-vix-010 | T0018 | H0015 | REJECTED | daily_baa10y_vix | coef -6.25819e-05 (partial R² 6.55263e-06) | 0.88964 | 5957 |
| credit-spread-vxn-011 | T0019 | H0016 | REJECTED | daily_baa10y_vxn | coef -9.71477e-05 (partial R² 2.2859e-05) | 0.800103 | 5955 |
| credit-spread-dgs10-012 | T0020 | H0017 | REJECTED | daily_baa10y_dgs10 | coef -0.0490852 (partial R² 0.00057572) | 0.18194 | 5957 |
| btc-dvol-013 | T0021 | H0018 | REJECTED | daily_btc_dvol | coef 0.100154 (partial R² 0.00119487) | 0.226898 | 2065 |

Failed trials (recorded in the ledgers, no metrics):

- T0006 (options-expiry-004, H0006): bootstrap point estimate does not match the OLS coefficient: 5.931247862987306e-10 vs 1.2603901708849118e-06
- T0008 (fomc-event-study-005, H0007): cycle boundary 2015-12-17 (cycle_hiking_2) is neither a scheduled statement day nor an unscheduled meeting day
- T0014 (publication-lag-007, H0012): releases without a usable MoM: ('2025-11', '2026-11'), expected ('2025-11',)

Open studies (a hypothesis still registered/testing): lowvol-002.

## Graph

12 nodes, 45 edges: 6 supported, 36 rejected, 1 pending, 2 descriptive.

Supported edges (within-study verdicts; the lab-wide audit columns are quoted from the 2B audit summary, not recomputed):

| edge | pair | hypothesis | trial | Holm survives | BH survives |
| --- | --- | --- | --- | --- | --- |
| E0023 | TYVIX→TYVIX | H0007 | T0010 | yes | yes |
| E0026 | DGS10→BAA10Y | H0008 | T0009 | yes | yes |
| E0030 | BTC→BTC | H0010 | T0012 | no | no |
| E0031 | ETH→ETH | H0010 | T0012 | no | yes |
| E0032 | TYVIX→TYVIX | H0011 | T0013 | yes | yes |
| E0033 | VIX→VIX | H0011 | T0013 | no | yes |

- E0026: Partly mechanical: BAA10Y is defined as the BAA yield minus the 10-year Treasury yield (DGS10), so the cross-sectional slope is (beta_BAA - 1) by construction, not a clean transmission estimate. See docs/studies/fomc-event-study-005.md.
- E0030: Bootstrap-marginal: the HAC test is significant, but the block-bootstrap 95% CI for the mean difference just includes zero. The ETH leg (E0031) is significant by both methods.

Lab-wide audit (2B): family of 42 tested edges; 3 of 6 supported edges survive Holm, 5 survive BH. This is a post-hoc second-layer reading; it does not change any within-study verdict.

## Candidate queue

117 untested candidate pairs: 105 ranked, 12 unrankable. Score tiers: 1.00 × 29, 0.80 × 11, 0.70 × 47, 0.50 × 18.

Top 10 (the ranking is a heuristic; the top tier is a tie broken lexicographically — see the planner report):

| rank | pair | score | mechanism | test |
| --- | --- | --- | --- | --- |
| 1 | BTC→ETH_DVOL | 1.00 | transmission | lead_lag |
| 2 | ETH→BTC | 1.00 | transmission | lead_lag |
| 3 | ETH→SOL | 1.00 | transmission | lead_lag |
| 4 | ETH→BTC_DVOL | 1.00 | transmission | lead_lag |
| 5 | ETH→ETH_DVOL | 1.00 | transmission | lead_lag |
| 6 | SOL→BTC | 1.00 | transmission | lead_lag |
| 7 | SOL→ETH | 1.00 | transmission | lead_lag |
| 8 | BTC_DVOL→BTC | 1.00 | transmission | lead_lag |
| 9 | BTC_DVOL→ETH | 1.00 | transmission | lead_lag |
| 10 | ETH_DVOL→BTC | 1.00 | transmission | lead_lag |

## Data freshness

Probe-time snapshot from the 6b evidence report (probed 2026-11-18T21:45:56.107388Z); panel freshness is judged against what each source serves, not against today.

| source | probe | pass | skip | fail | quirks | recorded-only | last verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bls | manual-only | 0 | 1 | 0 | 3 | 3 | 2026-11-18 |
| deribit | automatic | 4 | 0 | 0 | 7 | 4 | 2026-11-18 |
| federalreserve | automatic | 2 | 0 | 0 | 3 | 3 | 2026-11-18 |
| fiscaldata | automatic | 2 | 0 | 0 | 4 | 3 | 2026-11-18 |
| fred | automatic | 13 | 0 | 0 | 10 | 7 | 2026-11-18 |
| hyperliquid | automatic | 2 | 0 | 0 | 2 | 2 | 2026-11-18 |
| okx-public | automatic | 2 | 0 | 0 | 8 | 7 | 2026-11-19 |
| yahoo-finance | automatic | 2 | 0 | 0 | 4 | 4 | 2026-11-18 |

Panels: 5 fresh, 7 stale at probe time.

- crypto:btc-usdt-perp (okx-public): panel last 2026-11-16, expected 2026-11-17, 1 day behind
- crypto:eth-usdt-perp (okx-public): panel last 2026-11-16, expected 2026-11-17, 1 day behind
- crypto:sol-usdt-perp (okx-public): panel last 2026-11-16, expected 2026-11-17, 1 day behind
- index:sp500 (yahoo-finance): panel last 2026-11-16, expected 2026-11-18, 2 days behind
- index:vix (fred): panel last 2026-11-16, expected 2026-11-17, 1 day behind
- index:vxn (fred): panel last 2020-05-15, expected 2026-11-17, 2377 days behind
- rates:us-10y-yield (fred): panel last 2026-11-16, expected 2026-11-17, 1 day behind

Update after the probe: index:vxn — Re-fetched past 2020-05-15 after the probe: full series 2001-02-02 to 2026-11-17 (6487 rows, 242 missing) (see `research/planner-6a/vxn_refresh.json`).

## Review status (6d, quoted)

Full-lab review at 2026-11-19T17:28:01.794967Z: 129 pass, 0 fail, 8 unverified, 17 note.

Unverified items (not passes):

- btc-eth-001: pit_spot_check — no PIT parquet retained locally for this study
- fomc-event-study-005: ledger_anchor — no anchor file; truncation undetectable
- fomc-event-study-005: pit_spot_check — no PIT parquet retained locally for this study
- lowvol-002: pit_spot_check — no PIT parquet retained locally for this study
- macro-windows-006: pit_spot_check — no PIT parquet retained locally for this study
- move-vix-003: pit_spot_check — no PIT parquet retained locally for this study
- options-expiry-004: pit_spot_check — no PIT parquet retained locally for this study
- publication-lag-007: pit_spot_check — no PIT parquet retained locally for this study

## Pending items

- Forward test pending: hypothesis H0003 (edge E0011, BTC→ETH); no trial run yet; 0/60 low-vol rows observed, not ready (window 2026-11-18T16:00:00Z to 2027-03-31T16:00:00Z); sample check at research/lowvol-002/h0003-sample-check.json
- Trial id T0003 is reserved (sequence gap with a recorded reservation); no ledger record exists yet
- 12 candidate pairs unrankable (no overlapping panel window): BTC_DVOL→TYVIX, BTC→TYVIX, CPI_MoM→TYVIX, ETH_DVOL→TYVIX, ETH→TYVIX, SOL→TYVIX, TYVIX→BTC, TYVIX→BTC_DVOL, TYVIX→CPI_MoM, TYVIX→ETH, TYVIX→ETH_DVOL, TYVIX→SOL
- Missing ledger anchor: research/fomc-event-study-005/trials.jsonl.anchor — ledger anchor absent; truncation undetectable
- PIT discipline unverified for 7 studies (no PIT parquet retained locally) — see Review status

## Integrity

0 broken links — every cross-reference resolves (edges, candidates, decision records, templates, review, audit, availability, sources, trial sequence).

Missing optional files (recorded, not failures):

- `research/fomc-event-study-005/trials.jsonl.anchor` — ledger anchor absent; truncation undetectable

## Sources

Files read to build this report (repo-relative paths):

- `research/btc-dvol-013/hypotheses/hypothesis-events.jsonl`
- `research/btc-dvol-013/hypotheses/registrations/H0018/v1.json`
- `research/btc-dvol-013/trials.jsonl`
- `research/btc-eth-001/hypotheses/hypothesis-events.jsonl`
- `research/btc-eth-001/hypotheses/registrations/H0001/v1.json`
- `research/btc-eth-001/trials.jsonl`
- `research/credit-spread-dgs10-012/hypotheses/hypothesis-events.jsonl`
- `research/credit-spread-dgs10-012/hypotheses/registrations/H0017/v1.json`
- `research/credit-spread-dgs10-012/hypotheses/registrations/H0017/v2.json`
- `research/credit-spread-dgs10-012/trials.jsonl`
- `research/credit-spread-spx-008/hypotheses/hypothesis-events.jsonl`
- `research/credit-spread-spx-008/hypotheses/registrations/H0013/v1.json`
- `research/credit-spread-spx-008/trials.jsonl`
- `research/credit-spread-tyvix-009/hypotheses/hypothesis-events.jsonl`
- `research/credit-spread-tyvix-009/hypotheses/registrations/H0014/v1.json`
- `research/credit-spread-tyvix-009/trials.jsonl`
- `research/credit-spread-vix-010/hypotheses/hypothesis-events.jsonl`
- `research/credit-spread-vix-010/hypotheses/registrations/H0015/v1.json`
- `research/credit-spread-vix-010/trials.jsonl`
- `research/credit-spread-vxn-011/hypotheses/hypothesis-events.jsonl`
- `research/credit-spread-vxn-011/hypotheses/registrations/H0016/v1.json`
- `research/credit-spread-vxn-011/trials.jsonl`
- `research/decision-records/records/DR-E0023.json`
- `research/decision-records/records/DR-E0026.json`
- `research/decision-records/records/DR-E0030.json`
- `research/decision-records/records/DR-E0031.json`
- `research/decision-records/records/DR-E0032.json`
- `research/decision-records/records/DR-E0033.json`
- `research/decision-records/records/DR-H0001.json`
- `research/decision-records/records/DR-H0002.json`
- `research/decision-records/records/DR-H0004.json`
- `research/decision-records/records/DR-H0005.json`
- `research/decision-records/records/DR-H0006.json`
- `research/decision-records/records/DR-H0007.json`
- `research/decision-records/records/DR-H0008.json`
- `research/decision-records/records/DR-H0009.json`
- `research/decision-records/records/DR-H0012.json`
- `research/decision-records/records/DR-H0013.json`
- `research/decision-records/records/DR-H0014.json`
- `research/decision-records/records/DR-H0015.json`
- `research/decision-records/records/DR-H0016.json`
- `research/decision-records/records/DR-H0017.json`
- `research/decision-records/records/DR-H0018.json`
- `research/evidence-6b/evidence_report.json`
- `research/evidence-6b/panel_freshness.json`
- `research/evidence-6b/sources.json`
- `research/fomc-event-study-005/hypotheses/hypothesis-events.jsonl`
- `research/fomc-event-study-005/hypotheses/registrations/H0007/v1.json`
- `research/fomc-event-study-005/hypotheses/registrations/H0008/v1.json`
- `research/fomc-event-study-005/trials.jsonl`
- `research/graph/registry.json`
- `research/lowvol-002/hypotheses/hypothesis-events.jsonl`
- `research/lowvol-002/hypotheses/registrations/H0002/v1.json`
- `research/lowvol-002/hypotheses/registrations/H0003/v1.json`
- `research/lowvol-002/trials.jsonl`
- `research/macro-windows-006/hypotheses/hypothesis-events.jsonl`
- `research/macro-windows-006/hypotheses/registrations/H0009/v1.json`
- `research/macro-windows-006/hypotheses/registrations/H0010/v1.json`
- `research/macro-windows-006/trials.jsonl`
- `research/move-vix-003/hypotheses/hypothesis-events.jsonl`
- `research/move-vix-003/hypotheses/registrations/H0004/v1.json`
- `research/move-vix-003/hypotheses/registrations/H0004/v2.json`
- `research/move-vix-003/trials.jsonl`
- `research/options-expiry-004/hypotheses/hypothesis-events.jsonl`
- `research/options-expiry-004/hypotheses/registrations/H0005/v1.json`
- `research/options-expiry-004/hypotheses/registrations/H0006/v1.json`
- `research/options-expiry-004/trials.jsonl`
- `research/planner-6a/data_availability.json`
- `research/planner-6a/ranking.json`
- `research/planner-6a/templates/crypto-btc-usdt-perp__index-eth-dvol.json`
- `research/planner-6a/templates/crypto-eth-usdt-perp__crypto-btc-usdt-perp.json`
- `research/planner-6a/templates/crypto-eth-usdt-perp__crypto-sol-usdt-perp.json`
- `research/planner-6a/templates/crypto-eth-usdt-perp__index-btc-dvol.json`
- `research/planner-6a/templates/crypto-eth-usdt-perp__index-eth-dvol.json`
- `research/planner-6a/templates/crypto-sol-usdt-perp__crypto-btc-usdt-perp.json`
- `research/planner-6a/templates/crypto-sol-usdt-perp__crypto-eth-usdt-perp.json`
- `research/planner-6a/templates/index-btc-dvol__crypto-btc-usdt-perp.json`
- `research/planner-6a/templates/index-btc-dvol__crypto-eth-usdt-perp.json`
- `research/planner-6a/templates/index-eth-dvol__crypto-btc-usdt-perp.json`
- `research/planner-6a/vxn_refresh.json`
- `research/publication-lag-007/hypotheses/hypothesis-events.jsonl`
- `research/publication-lag-007/hypotheses/registrations/H0011/v1.json`
- `research/publication-lag-007/hypotheses/registrations/H0012/v1.json`
- `research/publication-lag-007/trials.jsonl`
- `research/review-6d/review_report.json`
- `research/statistical-audit-2b/summary.json`

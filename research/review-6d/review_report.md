# Adversarial review report (Stage 6d)

Reviewed at: 2026-11-19T03:00:55+00:00

Read-only review of the lab's 10 empirical studies: ledger integrity, preregistration binding, multiple-testing recomputation, verdict consistency, lifecycle state, report-ledger agreement, trial-ID sequence and point-in-time discipline. UNVERIFIED means the check could not be performed — it is not a pass. NOTE entries are informational MDE annotations from the 2B audit and never fail.

## Summary

- PASS: 102
- FAIL: 0
- UNVERIFIED: 8
- NOTE: 14

## btc-eth-001

- Report: `docs/studies/btc-eth-transmission-001.md`
- Checks: 8 pass, 0 fail, 1 unverified, 1 note

- **[PASS]** `ledger_chain` (research/btc-eth-001/trials.jsonl): hash chain intact (1 record(s))
  - research/btc-eth-001/trials.jsonl: 1 record(s), latest record hash 7cf678cdaffa...
- **[PASS]** `ledger_anchor` (research/btc-eth-001/trials.jsonl): ledger matches its anchor (1 record(s))
  - research/btc-eth-001/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/btc-eth-001/hypotheses): event chain intact (3 event(s))
  - research/btc-eth-001/hypotheses: 3 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0001): bound to H0001 v1 (fingerprint, plan, spec hash)
  - T0001: fingerprint 1938d1bd8e5a..., spec hash 17d7b851aea9...
- **[PASS]** `multiple_testing` (T0001): holm adjustment recomputes (3 test(s), family size matches plan)
  - T0001: 3 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0001): verdict re-derives from metrics and spec (primary test daily_btc_eth)
  - T0001: supported=False equals the conjunction of 4 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 1.0); primary_partial_r_squared_at_least_0.005=False (partial_r_squared 0.00010990546273016321 >= 0.005)
- **[NOTE]** `power_note` (T0001): MDE annotation from the 2B audit (1 entry)
  - E0001: lead-lag n=1414, MDE partial R²=0.005520192649316948, observed=0.00010990546273016321 (below MDE)
- **[PASS]** `hypothesis_state` (H0001 v1): lifecycle state rejected matches the trial verdict
  - btc-eth-001 H0001 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (btc-eth-001): 6/6 report row(s) verified against the ledger
  - T0001 daily_btc_eth: 8 column(s) match
  - T0001 daily_btc_eth_no_factor: 7 column(s) match
  - T0001 daily_btc_sol: 8 column(s) match
  - T0001 daily_btc_sol_no_factor: 7 column(s) match
  - T0001 hourly_btc_eth: 8 column(s) match
  - T0001 hourly_btc_eth_no_factor: 7 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (btc-eth-001): no PIT parquet retained locally for this study
  - btc-eth-001: data/cache/btc-eth-001/ holds no *.parquet batches

## lowvol-002

- Report: `docs/studies/lowvol-transmission-002.md`
- Checks: 8 pass, 0 fail, 1 unverified, 1 note

- **[PASS]** `ledger_chain` (research/lowvol-002/trials.jsonl): hash chain intact (1 record(s))
  - research/lowvol-002/trials.jsonl: 1 record(s), latest record hash 1240f8d7a520...
- **[PASS]** `ledger_anchor` (research/lowvol-002/trials.jsonl): ledger matches its anchor (1 record(s))
  - research/lowvol-002/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/lowvol-002/hypotheses): event chain intact (4 event(s))
  - research/lowvol-002/hypotheses: 4 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0002): bound to H0002 v1 (fingerprint, plan, spec hash)
  - T0002: fingerprint 08b43b7d4769..., spec hash ab4af4e70486...
- **[PASS]** `multiple_testing` (T0002): holm adjustment recomputes (4 test(s), family size matches plan)
  - T0002: 4 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0002): verdict re-derives from metrics and spec (primary test daily_btc_sol_interaction)
  - T0002: supported=False equals the conjunction of 4 criteria; holm_adjusted_a1_p_below_0.05=False (adjusted p 0.28314473469230644); a1_partial_r_squared_at_least_0.005=False (partial_r_squared 0.0037592235722866065 >= 0.005)
- **[NOTE]** `power_note` (T0002): MDE annotation from the 2B audit (1 entry)
  - E0004: lead-lag n=1133, MDE partial R²=0.0068798592642495575, observed=0.0037592235722866065 (below MDE)
- **[PASS]** `hypothesis_state` (H0002 v1): lifecycle state rejected matches the trial verdict
  - lowvol-002 H0002 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (lowvol-002): 8/8 report row(s) verified against the ledger
  - T0002 daily_btc_sol_interaction: 8 column(s) match
  - T0002 daily_btc_sol_interaction_no_factor: 7 column(s) match
  - T0002 daily_btc_sol_lowvol: 8 column(s) match
  - T0002 daily_btc_sol_lowvol_no_factor: 7 column(s) match
  - T0002 hourly_btc_eth_interaction: 8 column(s) match
  - T0002 hourly_btc_eth_interaction_no_factor: 7 column(s) match
  - T0002 hourly_btc_eth_lowvol: 8 column(s) match
  - T0002 hourly_btc_eth_lowvol_no_factor: 7 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (lowvol-002): no PIT parquet retained locally for this study
  - lowvol-002: data/cache/lowvol-002/ holds no *.parquet batches

## move-vix-003

- Report: `docs/studies/move-vix-transmission-003.md`
- Checks: 8 pass, 0 fail, 1 unverified, 1 note

- **[PASS]** `ledger_chain` (research/move-vix-003/trials.jsonl): hash chain intact (1 record(s))
  - research/move-vix-003/trials.jsonl: 1 record(s), latest record hash 77f2789ca1ea...
- **[PASS]** `ledger_anchor` (research/move-vix-003/trials.jsonl): ledger matches its anchor (1 record(s))
  - research/move-vix-003/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/move-vix-003/hypotheses): event chain intact (5 event(s))
  - research/move-vix-003/hypotheses: 5 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0004): bound to H0004 v2 (fingerprint, plan, spec hash)
  - T0004: fingerprint c3923f5a530e..., spec hash d2fbf05159af...
- **[PASS]** `multiple_testing` (T0004): holm adjustment recomputes (3 test(s), family size matches plan)
  - T0004: 3 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0004): verdict re-derives from metrics and spec (primary test daily_tyvix_vix)
  - T0004: supported=False equals the conjunction of 3 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 1.0); primary_partial_r_squared_at_least_0.005=False (partial_r_squared 3.484028991192486e-05 >= 0.005)
- **[NOTE]** `power_note` (T0004): MDE annotation from the 2B audit (1 entry)
  - E0008: lead-lag n=4327, MDE partial R²=0.0018106466804513129, observed=3.484028991192486e-05 (below MDE)
- **[PASS]** `hypothesis_state` (H0004 v2): lifecycle state rejected matches the trial verdict
  - move-vix-003 H0004 v2: supported=False, state=rejected
- **[PASS]** `report_ledger` (move-vix-003): 6/6 report row(s) verified against the ledger
  - T0004 daily_tyvix_vix: 8 column(s) match
  - T0004 daily_tyvix_vix_no_factor: 7 column(s) match
  - T0004 daily_tyvix_vxn: 8 column(s) match
  - T0004 daily_tyvix_vxn_no_factor: 7 column(s) match
  - T0004 weekly_tyvix_vix: 8 column(s) match
  - T0004 weekly_tyvix_vix_no_factor: 7 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (move-vix-003): no PIT parquet retained locally for this study
  - move-vix-003: data/cache/move-vix-003/ holds no *.parquet batches

## options-expiry-004

- Report: `docs/studies/options-expiry-004.md`
- Checks: 13 pass, 0 fail, 1 unverified, 2 note

- **[PASS]** `ledger_chain` (research/options-expiry-004/trials.jsonl): hash chain intact (3 record(s))
  - research/options-expiry-004/trials.jsonl: 3 record(s), latest record hash 69d75c944b75...
- **[PASS]** `ledger_anchor` (research/options-expiry-004/trials.jsonl): ledger matches its anchor (3 record(s))
  - research/options-expiry-004/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/options-expiry-004/hypotheses): event chain intact (6 event(s))
  - research/options-expiry-004/hypotheses: 6 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0005): bound to H0005 v1 (fingerprint, plan, spec hash)
  - T0005: fingerprint 5c9d73af2bd7..., spec hash fc5e4c6d6397...
- **[PASS]** `multiple_testing` (T0005): holm adjustment recomputes (3 test(s), family size matches plan)
  - T0005: 3 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0005): verdict re-derives from metrics and spec (primary test daily_btc_eth_interaction)
  - T0005: supported=False equals the conjunction of 4 criteria; holm_adjusted_a_p_below_0.05=False (adjusted p 0.6938231572768055); a_partial_r_squared_at_least_0.005=False (partial_r_squared 8.365601959676024e-05 >= 0.005)
- **[NOTE]** `power_note` (T0005): MDE annotation from the 2B audit (1 entry)
  - E0014: lead-lag n=2124, MDE partial R²=0.003681724257737793, observed=8.365601959676024e-05 (below MDE)
- **[PASS]** `prereg_binding` (T0006): bound to H0006 v1 (fingerprint, plan, spec hash)
  - T0006: fingerprint 0c48d2ac4fc3..., spec hash 998b16ad3afb...
- **[PASS]** `prereg_binding` (T0007): bound to H0006 v1 (fingerprint, plan, spec hash)
  - T0007: fingerprint 0c48d2ac4fc3..., spec hash a07490ac2170...
- **[PASS]** `multiple_testing` (T0007): holm adjustment recomputes (2 test(s), family size matches plan)
  - T0007: 2 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0007): verdict re-derives from metrics and spec (primary test btc_mean_abs_return_comparison)
  - T0007: supported=False equals the conjunction of 2 criteria; holm_adjusted_btc_p_below_0.05=False (adjusted p 1.0); btc_effect_ratio_at_least_1.15=False (effect_ratio 1.0000634084216993 >= 1.15)
- **[NOTE]** `power_note` (T0007): MDE annotation from the 2B audit (2 entries)
  - E0017 (BTC expiry windows): mean comparison n=280/1845, MDE Cohen's d=0.1796826332574515, observed=5.595043106510809e-05 (below MDE)
  - E0018 (ETH expiry windows): mean comparison n=280/1845, MDE Cohen's d=0.1796826332574515, observed=-0.0422406835494709 (below MDE)
- **[PASS]** `hypothesis_state` (H0005 v1): lifecycle state rejected matches the trial verdict
  - options-expiry-004 H0005 v1: supported=False, state=rejected
- **[PASS]** `hypothesis_state` (H0006 v1): lifecycle state rejected matches the trial verdict
  - options-expiry-004 H0006 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (options-expiry-004): 8/8 report row(s) verified against the ledger
  - T0005 daily_btc_eth_interaction: 8 column(s) match
  - T0005 daily_btc_eth_interaction_no_factor: 7 column(s) match
  - T0005 daily_btc_eth_window: 8 column(s) match
  - T0005 daily_btc_eth_window_no_factor: 7 column(s) match
  - T0005 hourly_btc_eth_interaction: 8 column(s) match
  - T0005 hourly_btc_eth_interaction_no_factor: 7 column(s) match
  - T0007 btc_mean_abs_return_comparison: 10 column(s) match
  - T0007 eth_mean_abs_return_comparison: 10 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (options-expiry-004): no PIT parquet retained locally for this study
  - options-expiry-004: data/cache/options-expiry-004/ holds no *.parquet batches

## fomc-event-study-005

- Report: `docs/studies/fomc-event-study-005.md`
- Checks: 12 pass, 0 fail, 2 unverified, 2 note

- **[PASS]** `ledger_chain` (research/fomc-event-study-005/trials.jsonl): hash chain intact (3 record(s))
  - research/fomc-event-study-005/trials.jsonl: 3 record(s), latest record hash c82c6182f15f...
- **[UNVERIFIED]** `ledger_anchor` (research/fomc-event-study-005/trials.jsonl): no anchor file; truncation undetectable
  - research/fomc-event-study-005/trials.jsonl: trials.jsonl.anchor absent, the chain verifies tampering only
- **[PASS]** `registry_events` (research/fomc-event-study-005/hypotheses): event chain intact (6 event(s))
  - research/fomc-event-study-005/hypotheses: 6 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0008): bound to H0007 v1 (fingerprint, plan, spec hash)
  - T0008: fingerprint c9a278bf1371..., spec hash db5714f3739a...
- **[PASS]** `prereg_binding` (T0010): bound to H0007 v1 (fingerprint, plan, spec hash)
  - T0010: fingerprint c9a278bf1371..., spec hash ea138869f539...
- **[PASS]** `multiple_testing` (T0010): holm adjustment recomputes (5 test(s), family size matches plan)
  - T0010: 5 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0010): verdict re-derives from metrics and spec (primary test vix_car)
  - T0010: supported=False equals the conjunction of 2 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 0.1599620103450956); primary_standardized_mean_car_at_most_minus_0.3=False (standardized_mean_car -0.15068455311467216 <= -0.3)
- **[NOTE]** `power_note` (T0010): MDE annotation from the 2B audit (2 entries)
  - E0019: event-study n=135, MDE std. mean CAR=0.21400168279054138, observed=-0.15068455311467216 (below MDE)
  - E0023: event-study n=135, MDE std. mean CAR=0.21400168279054138, observed=-0.4828971210838664 (above MDE)
- **[PASS]** `prereg_binding` (T0009): bound to H0008 v1 (fingerprint, plan, spec hash)
  - T0009: fingerprint f76d5b607567..., spec hash 60f19ad9e0f1...
- **[PASS]** `multiple_testing` (T0009): holm adjustment recomputes (3 test(s), family size matches plan)
  - T0009: 3 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0009): verdict re-derives from metrics and spec (primary test spx_on_dgs10)
  - T0009: supported=False equals the conjunction of 3 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 0.7262425610107872); primary_r_squared_at_least_0.05=False (r_squared 0.005714659904412223 >= 0.05)
- **[NOTE]** `power_note` (T0009): MDE annotation from the 2B audit (1 entry)
  - E0024: cross-section n=135, MDE R²=0.054945336280868076, observed=0.005714659904412223 (below MDE)
- **[PASS]** `hypothesis_state` (H0007 v1): lifecycle state rejected matches the trial verdict
  - fomc-event-study-005 H0007 v1: supported=False, state=rejected
- **[PASS]** `hypothesis_state` (H0008 v1): lifecycle state rejected matches the trial verdict
  - fomc-event-study-005 H0008 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (fomc-event-study-005): 8/8 report row(s) verified against the ledger
  - T0010 vix_car: 6 column(s) match
  - T0010 spx_car: 6 column(s) match
  - T0010 dgs10_car: 6 column(s) match
  - T0010 baa10y_car: 6 column(s) match
  - T0010 tyvix_car: 6 column(s) match
  - T0009 spx_on_dgs10: 6 column(s) match
  - T0009 vix_on_dgs10: 6 column(s) match
  - T0009 baa10y_on_dgs10: 6 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (fomc-event-study-005): no PIT parquet retained locally for this study
  - fomc-event-study-005: data/cache/fomc-event-study-005/ holds no *.parquet batches

## macro-windows-006

- Report: `docs/studies/macro-windows-006.md`
- Checks: 12 pass, 0 fail, 1 unverified, 2 note

- **[PASS]** `ledger_chain` (research/macro-windows-006/trials.jsonl): hash chain intact (2 record(s))
  - research/macro-windows-006/trials.jsonl: 2 record(s), latest record hash 4b0dd1cce4fb...
- **[PASS]** `ledger_anchor` (research/macro-windows-006/trials.jsonl): ledger matches its anchor (2 record(s))
  - research/macro-windows-006/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/macro-windows-006/hypotheses): event chain intact (6 event(s))
  - research/macro-windows-006/hypotheses: 6 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0011): bound to H0009 v1 (fingerprint, plan, spec hash)
  - T0011: fingerprint 0e1ec3d3768c..., spec hash be51ddfdbd2e...
- **[PASS]** `multiple_testing` (T0011): holm adjustment recomputes (3 test(s), family size matches plan)
  - T0011: 3 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0011): verdict re-derives from metrics and spec (primary test daily_btc_eth_interaction)
  - T0011: supported=False equals the conjunction of 4 criteria; holm_adjusted_a_p_below_0.05=False (adjusted p 1.0); a_partial_r_squared_at_least_0.005=False (partial_r_squared 3.081259166245943e-09 >= 0.005)
- **[NOTE]** `power_note` (T0011): MDE annotation from the 2B audit (1 entry)
  - E0027: lead-lag n=2124, MDE partial R²=0.003681724257737793, observed=3.081259166245943e-09 (below MDE)
- **[PASS]** `prereg_binding` (T0012): bound to H0010 v1 (fingerprint, plan, spec hash)
  - T0012: fingerprint a10ddda95531..., spec hash 7402b579b289...
- **[PASS]** `multiple_testing` (T0012): holm adjustment recomputes (2 test(s), family size matches plan)
  - T0012: 2 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0012): verdict re-derives from metrics and spec (primary test btc_mean_abs_return_comparison)
  - T0012: supported=True equals the conjunction of 2 criteria; holm_adjusted_btc_p_below_0.05=True (adjusted p 0.009817680267895559); btc_effect_ratio_at_least_1.15=True (effect_ratio 1.250433717580785 >= 1.15)
- **[NOTE]** `power_note` (T0012): MDE annotation from the 2B audit (2 entries)
  - E0030 (BTC macro windows): mean comparison n=116/2009, MDE Cohen's d=0.26752498076303577, observed=0.24657437445164904 (below MDE)
  - E0031 (ETH macro windows): mean comparison n=116/2009, MDE Cohen's d=0.26752498076303577, observed=0.28438819212767746 (above MDE)
- **[PASS]** `hypothesis_state` (H0009 v1): lifecycle state rejected matches the trial verdict
  - macro-windows-006 H0009 v1: supported=False, state=rejected
- **[PASS]** `hypothesis_state` (H0010 v1): lifecycle state supported matches the trial verdict
  - macro-windows-006 H0010 v1: supported=True, state=supported
- **[PASS]** `report_ledger` (macro-windows-006): 8/8 report row(s) verified against the ledger
  - T0011 daily_btc_eth_interaction: 8 column(s) match
  - T0011 daily_btc_eth_interaction_no_factor: 7 column(s) match
  - T0011 daily_btc_eth_window: 8 column(s) match
  - T0011 daily_btc_eth_window_no_factor: 7 column(s) match
  - T0011 hourly_btc_eth_interaction: 8 column(s) match
  - T0011 hourly_btc_eth_interaction_no_factor: 7 column(s) match
  - T0012 btc_mean_abs_return_comparison: 10 column(s) match
  - T0012 eth_mean_abs_return_comparison: 10 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (macro-windows-006): no PIT parquet retained locally for this study
  - macro-windows-006: data/cache/macro-windows-006/ holds no *.parquet batches

## publication-lag-007

- Report: `docs/studies/publication-lag-007.md`
- Checks: 13 pass, 0 fail, 1 unverified, 2 note

- **[PASS]** `ledger_chain` (research/publication-lag-007/trials.jsonl): hash chain intact (3 record(s))
  - research/publication-lag-007/trials.jsonl: 3 record(s), latest record hash 6d757217ecab...
- **[PASS]** `ledger_anchor` (research/publication-lag-007/trials.jsonl): ledger matches its anchor (3 record(s))
  - research/publication-lag-007/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/publication-lag-007/hypotheses): event chain intact (6 event(s))
  - research/publication-lag-007/hypotheses: 6 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0013): bound to H0011 v1 (fingerprint, plan, spec hash)
  - T0013: fingerprint b1d626ddffb3..., spec hash 2c1fcb4eced0...
- **[PASS]** `multiple_testing` (T0013): holm adjustment recomputes (5 test(s), family size matches plan)
  - T0013: 5 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0013): verdict re-derives from metrics and spec (primary test tyvix_lagged_car)
  - T0013: supported=True equals the conjunction of 2 criteria; holm_adjusted_primary_p_below_0.05=True (adjusted p 5.201439834401356e-09); primary_standardized_mean_car_at_most_minus_0.3=True (standardized_mean_car -0.5156565761431623 <= -0.3)
- **[NOTE]** `power_note` (T0013): MDE annotation from the 2B audit (2 entries)
  - E0032: event-study n=135, MDE std. mean CAR=0.21400168279054138, observed=-0.5156565761431623 (above MDE)
  - E0033: event-study n=135, MDE std. mean CAR=0.21400168279054138, observed=-0.25609922433859056 (above MDE)
- **[PASS]** `prereg_binding` (T0014): bound to H0012 v1 (fingerprint, plan, spec hash)
  - T0014: fingerprint 8526ef1ce9d5..., spec hash 383e2e869acf...
- **[PASS]** `prereg_binding` (T0015): bound to H0012 v1 (fingerprint, plan, spec hash)
  - T0015: fingerprint 8526ef1ce9d5..., spec hash b022f1203379...
- **[PASS]** `multiple_testing` (T0015): holm adjustment recomputes (3 test(s), family size matches plan)
  - T0015: 3 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0015): verdict re-derives from metrics and spec (primary test spx_daily)
  - T0015: supported=False equals the conjunction of 3 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 0.7548740391336041); primary_partial_r_squared_at_least_0.005=False (partial_r_squared 0.00010223875705747534 >= 0.005)
- **[NOTE]** `power_note` (T0015): MDE annotation from the 2B audit (1 entry)
  - E0037: lead-lag n=1468, MDE partial R²=0.0053182137020437205, observed=0.00010223875705747534 (below MDE)
- **[PASS]** `hypothesis_state` (H0011 v1): lifecycle state supported matches the trial verdict
  - publication-lag-007 H0011 v1: supported=True, state=supported
- **[PASS]** `hypothesis_state` (H0012 v1): lifecycle state rejected matches the trial verdict
  - publication-lag-007 H0012 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (publication-lag-007): 8/8 report row(s) verified against the ledger
  - T0013 tyvix_lagged_car: 6 column(s) match
  - T0013 vix_lagged_car: 6 column(s) match
  - T0013 dgs10_lagged_car: 6 column(s) match
  - T0013 baa10y_lagged_car: 6 column(s) match
  - T0013 spx_car: 6 column(s) match
  - T0015 spx_daily: 7 column(s) match
  - T0015 spx_release_day: 7 column(s) match
  - T0015 btc_daily: 7 column(s) match
- **[UNVERIFIED]** `pit_spot_check` (publication-lag-007): no PIT parquet retained locally for this study
  - publication-lag-007: data/cache/publication-lag-007/ holds no *.parquet batches

## credit-spread-spx-008

- Report: `docs/studies/credit-spread-spx-008.md`
- Checks: 9 pass, 0 fail, 0 unverified, 1 note

- **[PASS]** `ledger_chain` (research/credit-spread-spx-008/trials.jsonl): hash chain intact (1 record(s))
  - research/credit-spread-spx-008/trials.jsonl: 1 record(s), latest record hash 5e2ca06ab5c3...
- **[PASS]** `ledger_anchor` (research/credit-spread-spx-008/trials.jsonl): ledger matches its anchor (1 record(s))
  - research/credit-spread-spx-008/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/credit-spread-spx-008/hypotheses): event chain intact (3 event(s))
  - research/credit-spread-spx-008/hypotheses: 3 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0016): bound to H0013 v1 (fingerprint, plan, spec hash)
  - T0016: fingerprint e7f98ea75dd4..., spec hash 1f1916a0b0fb...
- **[PASS]** `multiple_testing` (T0016): holm adjustment recomputes (1 test(s), family size matches plan)
  - T0016: 1 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0016): verdict re-derives from metrics and spec (primary test daily_baa10y_spx)
  - T0016: supported=False equals the conjunction of 4 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 0.8935170696924368); primary_partial_r_squared_at_least_0.005=False (partial_r_squared 2.1926421937872296e-05 >= 0.005)
- **[NOTE]** `power_note` (T0016): MDE annotation from the 2B audit (1 entry)
  - E0040: lead-lag n=5957, MDE partial R²=0.0013158555887334818, observed=2.1926421937872296e-05 (below MDE)
- **[PASS]** `hypothesis_state` (H0013 v1): lifecycle state rejected matches the trial verdict
  - credit-spread-spx-008 H0013 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (credit-spread-spx-008): 4/4 report row(s) verified against the ledger
  - T0016 daily_baa10y_spx: 8 column(s) match
  - T0016 daily_baa10y_spx_no_factor: 7 column(s) match
  - T0016 daily_baa10y_spx_naive: 7 column(s) match
  - T0016 daily_spx_baa10y_reverse: 7 column(s) match
- **[PASS]** `pit_spot_check` (credit-spread-spx-008): available_at >= event_time for all 18018 retained observation(s)
  - credit-spread-spx-008: 18018 observation(s) in 3 batch(es)

## credit-spread-tyvix-009

- Report: `docs/studies/credit-spread-tyvix-009.md`
- Checks: 9 pass, 0 fail, 0 unverified, 1 note

- **[PASS]** `ledger_chain` (research/credit-spread-tyvix-009/trials.jsonl): hash chain intact (1 record(s))
  - research/credit-spread-tyvix-009/trials.jsonl: 1 record(s), latest record hash 4daa54ed5167...
- **[PASS]** `ledger_anchor` (research/credit-spread-tyvix-009/trials.jsonl): ledger matches its anchor (1 record(s))
  - research/credit-spread-tyvix-009/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/credit-spread-tyvix-009/hypotheses): event chain intact (3 event(s))
  - research/credit-spread-tyvix-009/hypotheses: 3 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0017): bound to H0014 v1 (fingerprint, plan, spec hash)
  - T0017: fingerprint 435ae25855fd..., spec hash 084ef3bfc1e7...
- **[PASS]** `multiple_testing` (T0017): holm adjustment recomputes (1 test(s), family size matches plan)
  - T0017: 1 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0017): verdict re-derives from metrics and spec (primary test daily_baa10y_tyvix)
  - T0017: supported=False equals the conjunction of 3 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 0.7539842282666138); primary_partial_r_squared_at_least_0.005=False (partial_r_squared 6.1003316440060284e-05 >= 0.005)
- **[NOTE]** `power_note` (T0017): MDE annotation from the 2B audit (1 entry)
  - E0041: lead-lag n=4327, MDE partial R²=0.0018106466804513129, observed=6.1003316440060284e-05 (below MDE)
- **[PASS]** `hypothesis_state` (H0014 v1): lifecycle state rejected matches the trial verdict
  - credit-spread-tyvix-009 H0014 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (credit-spread-tyvix-009): 4/4 report row(s) verified against the ledger
  - T0017 daily_baa10y_tyvix: 8 column(s) match
  - T0017 daily_baa10y_tyvix_no_factor: 7 column(s) match
  - T0017 daily_baa10y_tyvix_naive: 7 column(s) match
  - T0017 daily_tyvix_baa10y_reverse: 7 column(s) match
- **[PASS]** `pit_spot_check` (credit-spread-tyvix-009): available_at >= event_time for all 13083 retained observation(s)
  - credit-spread-tyvix-009: 13083 observation(s) in 3 batch(es)

## credit-spread-vix-010

- Report: `docs/studies/credit-spread-vix-010.md`
- Checks: 9 pass, 0 fail, 0 unverified, 1 note

- **[PASS]** `ledger_chain` (research/credit-spread-vix-010/trials.jsonl): hash chain intact (1 record(s))
  - research/credit-spread-vix-010/trials.jsonl: 1 record(s), latest record hash f97982756713...
- **[PASS]** `ledger_anchor` (research/credit-spread-vix-010/trials.jsonl): ledger matches its anchor (1 record(s))
  - research/credit-spread-vix-010/trials.jsonl: anchor record count and latest hash agree
- **[PASS]** `registry_events` (research/credit-spread-vix-010/hypotheses): event chain intact (3 event(s))
  - research/credit-spread-vix-010/hypotheses: 3 lifecycle event(s), all transitions legal
- **[PASS]** `prereg_binding` (T0018): bound to H0015 v1 (fingerprint, plan, spec hash)
  - T0018: fingerprint eb8b21955fcf..., spec hash 4714145a404b...
- **[PASS]** `multiple_testing` (T0018): holm adjustment recomputes (1 test(s), family size matches plan)
  - T0018: 1 adjusted p-value(s) and reject flag(s) agree
- **[PASS]** `verdict_consistency` (T0018): verdict re-derives from metrics and spec (primary test daily_baa10y_vix)
  - T0018: supported=False equals the conjunction of 3 criteria; holm_adjusted_primary_p_below_0.05=False (adjusted p 0.8896402464379096); primary_partial_r_squared_at_least_0.005=False (partial_r_squared 6.552628668666667e-06 >= 0.005)
- **[NOTE]** `power_note` (T0018): MDE annotation from the 2B audit (1 entry)
  - E0042: lead-lag n=5957, MDE partial R²=0.0013158555887334818, observed=6.552628668666667e-06 (below MDE)
- **[PASS]** `hypothesis_state` (H0015 v1): lifecycle state rejected matches the trial verdict
  - credit-spread-vix-010 H0015 v1: supported=False, state=rejected
- **[PASS]** `report_ledger` (credit-spread-vix-010): 4/4 report row(s) verified against the ledger
  - T0018 daily_baa10y_vix: 8 column(s) match
  - T0018 daily_baa10y_vix_no_factor: 7 column(s) match
  - T0018 daily_baa10y_vix_naive: 7 column(s) match
  - T0018 daily_vix_baa10y_reverse: 7 column(s) match
- **[PASS]** `pit_spot_check` (credit-spread-vix-010): available_at >= event_time for all 18019 retained observation(s)
  - credit-spread-vix-010: 18019 observation(s) in 3 batch(es)

## Lab-wide checks

- **[PASS]** `trial_sequence` (lab): sequence T0001..T0018 complete (17 trial(s), T0003 reserved, 3 failed trial(s) recorded)
  - lab: 17 trial(s); reserved: T0003; failed: T0006, T0008, T0014

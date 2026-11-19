# Lab-wide statistical audit (Stage 2B)

> **Scope.** This is a post-hoc second-layer analysis of the lab's completed studies. It does NOT change any preregistered verdict: each study's within-family Holm correction remains its formal conclusion. The audit answers a different question — what is the lab's overall false-discovery posture when all tested edges are viewed as one family? — and it reports calibration, power and overfitting diagnostics for the lab's methods. Language throughout is descriptive: "under lab-wide family correction, X of the 6 supported edges remain significant", never "edge Y is actually not significant".

Provenance: registry content hash `65a4b04639537b99f3beaffef2e5ab84a4cbdbfeff2ec91a8c78358967664b28`; generated deterministically by `research/statistical-audit-2b/audit.py` (no timestamps in the output; re-running reproduces this file byte-identically). All numbers are computed from the trial ledgers and the registry or from fixed-seed simulations; none are hand-copied.

## 1. Lab-wide multiple-testing audit

The lab-wide family is all 37 tested edges (status supported or rejected) across the seven completed studies, each contributing the raw p-value of its Holm-family test as recorded in its trial ledger (cross-checked against the registry at generation time). Two corrections are applied to the whole family at alpha = 0.05:

- **Holm** (controls the family-wise error rate under arbitrary dependence — the conservative reading, and the valid one here, because the lab's tests reuse the same data);
- **Benjamini–Hochberg** (controls the false-discovery rate under independence or positive dependence — indicative only, because the lab's tests are not independent).

The family mixes one-sided p-values (the directional event-study legs) and two-sided ones; each is a valid p-value under its own null, and the corrections treat them uniformly. That heterogeneity is a limitation of the pooled reading, disclosed here rather than hidden.

### 1.1 The six supported edges under lab-wide correction

| Edge | Hypothesis | Trial | Raw p | Holm adj. p | BH adj. p | Holm sig. | BH sig. |
|------|------------|-------|-------|-------------|-----------|-----------|---------|
| E0023 | H0007 | T0010 | 1.007e-08 | 3.626e-07 | 1.863e-07 | yes | yes |
| E0026 | H0008 | T0009 | 0.000169 | 0.005914 | 0.002084 | yes | yes |
| E0030 | H0010 | T0012 | 0.009818 | 0.3142 | 0.06054 | no | no |
| E0031 | H0010 | T0012 | 0.0029 | 0.09569 | 0.02146 | no | yes |
| E0032 | H0011 | T0013 | 1.04e-09 | 3.849e-08 | 3.849e-08 | yes | yes |
| E0033 | H0011 | T0013 | 0.001462 | 0.04971 | 0.01352 | yes | yes |

**Headline.** Under lab-wide Holm correction, **4 of 6** supported edges remain significant; under lab-wide BH correction, **5 of 6**. These counts describe the lab-wide family reading only; the within-study verdicts stand unchanged.

- **E0026 caveat.** Partly mechanical: BAA10Y is defined as the BAA yield minus the 10-year Treasury yield (DGS10), so the cross-sectional slope is (beta_BAA - 1) by construction, not a clean transmission estimate. See docs/studies/fomc-event-study-005.md.
- **E0030 caveat.** Bootstrap-marginal: the HAC test is significant, but the block-bootstrap 95% CI for the mean difference just includes zero. The ETH leg (E0031) is significant by both methods. (block-bootstrap 95% CI for the mean difference: [-0.00022, 0.01036], which just includes zero)

### 1.2 Expected false discoveries

At the uncorrected 5% level, the family of 37 tests would be expected to produce **1.9** false positives under the global null; the observed count of raw p-values at or below 0.05 is **8**. The Storey pi0 estimate (lambda = 0.5) is **1.000**, meaning the p-value distribution is consistent with most of the family being null — which is expected: 31 of the 37 tested edges were rejected in their own studies. Across all 37 edges, lab-wide Holm rejects 4 and lab-wide BH rejects 5; the BH rejection set carries an expected-false-discovery upper bound of 0.25 (alpha x rejections, under BH's independence assumption).

### 1.3 Per-study breakdown

| Study | Tested | Supported | Holm survivors | BH survivors | Max Holm adj. p (supported) |
|-------|--------|-----------|---------------|--------------|-----------------------------|
| btc-eth-001 | 3 | 0 | 0 | 0 | — |
| credit-spread-spx-008 | 1 | 0 | 0 | 0 | — |
| fomc-event-study-005 | 8 | 2 | 2 | 2 | 0.005914 |
| lowvol-002 | 4 | 0 | 0 | 0 | — |
| macro-windows-006 | 5 | 2 | 0 | 1 | 0.3142 |
| move-vix-003 | 3 | 0 | 0 | 0 | — |
| options-expiry-004 | 5 | 0 | 0 | 0 | — |
| publication-lag-007 | 8 | 2 | 2 | 2 | 0.04971 |

The most fragile study under the lab-wide reading is **macro-windows-006** (0 of 2 supported edges survive Holm): E0030 (does not survive Holm, does not survive BH); E0031 (does not survive Holm, survives BH). The most fragile single survivor is E0033 (H0011, study publication-lag-007), whose lab-wide Holm adjusted p-value of 0.04971 sits just below 0.05. Again: fragility under a post-hoc pooled correction is a statement about the lab-wide family, not a re-judgement of the study's own verdict.

## 2. Calibration

Each procedure was run on data simulated under a known null, with the nominal level and the Monte Carlo standard error (MC SE) reported alongside the measured rate, so a deviation can be judged against simulation noise.

| Procedure | Setting | Nominal | Measured | MC SE | Reps |
|-----------|---------|---------|----------|-------|------|
| HAC t-test size | iid null, n=1414, lag 5 | 0.05 | 0.052 | 0.011 | 400 |
| HAC t-test size | AR(1) phi=0.3, n=1414, lag 5 | 0.05 | 0.058 | 0.012 | 400 |
| Block-bootstrap CI coverage | iid, n=2125, block 10 | 0.95 | 0.960 | 0.016 | 150 |
| Block-bootstrap CI coverage | AR(1) phi=0.3, n=2125, block 10 | 0.95 | 0.933 | 0.020 | 150 |
| Holm FWER | independent nulls, m=36 | 0.05 | 0.0504 | 0.0031 | 5000 |
| Holm FWER | equicorrelated (rho=0.3) nulls, m=36 | 0.05 | 0.0396 | 0.0028 | 5000 |

Reading: the HAC test holds its nominal size (within two Monte Carlo SEs) at the lab's daily sample size under both iid and AR(1) nulls; Holm controls the family-wise error rate at or below the nominal level under both independent and correlated nulls (conservative under correlation, as theory predicts); and the block-bootstrap interval is approximately calibrated (within two Monte Carlo SEs of 0.95 in both variants). Any shortfall from 0.95 in the AR(1) case is the known block-length sensitivity of the method, and it is one reason the lab reports bootstrap intervals alongside HAC inference rather than in place of it.

## 3. Power: minimum detectable effects

Minimum detectable effects (MDE) at 80% power, alpha = 0.05, computed analytically (normal approximation; see `docs/statistical-kernel.md` for the formulas) at each design's actual sample size, juxtaposed with the observed primary effects. An MDE is a design property: an observed effect below the MDE means the design was underpowered for an effect of that size, not that the effect does not exist.

### 3.1 Lead-lag OLS: partial R^2

| Trial | Hypothesis | n | MDE partial R^2 | Observed partial R^2 | MDE coef. | Observed coef. |
|-------|------------|---|------------------|----------------------|-----------|---------------|
| T0001 | H0001 | 1414 | 0.00552 | 0.00011 | 0.1952 | 0.0252 |
| T0002 | H0002 | 1133 | 0.00688 | 0.00376 | 0.3438 | 0.2217 |
| T0004 | H0004 | 4327 | 0.00181 | 0.00003 | 0.0919 | -0.0093 |
| T0005 | H0005 | 2124 | 0.00368 | 0.00008 | 0.2550 | -0.0358 |
| T0011 | H0009 | 2124 | 0.00368 | 0.00000 | 0.3625 | 0.0003 |
| T0015 | H0012 | 1468 | 0.00532 | 0.00010 | 0.3356 | -0.0374 |
| T0016 | H0013 | 5957 | 0.00132 | 0.00002 | 0.0004 | 0.0000 |

Note the first row: at n = 1,414 the partial-R^2 MDE is 0.00552, essentially the lab's preregistered 0.005 effect-size threshold. The threshold was chosen as a minimum interesting effect; the design can reliably detect only effects at least that large. 7 of the 7 observed lead-lag partial R^2 values sit below their MDE — the null results are consistent with 'no effect' and also with 'an effect too small for this design to see'. The two readings are not distinguished by these studies.

Cross-section (T0009, H0008, n = 135): the single-predictor R^2 MDE is 0.0549 (same formula as partial R^2 for one added regressor), against an observed R^2 of 0.0057 — again far below the detection limit, and the preregistered 0.05 threshold sits just below the MDE.

### 3.2 Event-study CAR: standardized mean CAR

| Edge | Trial | Role | n | MDE (one-sided) | Observed std. mean CAR |
|------|-------|------|---|-----------------|------------------------|
| E0019 | T0010 | primary | 135 | 0.2140 | -0.1507 |
| E0023 | T0010 | secondary | 135 | 0.2140 | -0.4829 |
| E0032 | T0013 | primary | 135 | 0.2140 | -0.5157 |
| E0033 | T0013 | secondary | 135 | 0.2140 | -0.2561 |

Legs below the MDE in magnitude: E0019; legs above it: E0023, E0032, E0033. The equity-vol response (E0019, E0033) is at the edge of what 135 events can resolve, while the rates-vol response (E0023, E0032) is large enough for this design to detect reliably.

### 3.3 Mean comparison: Cohen's d and effect ratio

| Edge | Trial | Comparison | n1/n2 | MDE d | Observed d | MDE ratio | Observed ratio |
|------|-------|------------|-------|-------|------------|-----------|---------------|
| E0017 | T0007 | BTC expiry windows | 280/1845 | 0.1797 | 0.0001 | 1.2036 | 1.0001 |
| E0018 | T0007 | ETH expiry windows | 280/1845 | 0.1797 | -0.0422 | 1.1744 | 0.9590 |
| E0030 | T0012 | BTC macro windows | 116/2009 | 0.2675 | 0.2466 | 1.2717 | 1.2504 |
| E0031 | T0012 | ETH macro windows | 116/2009 | 0.2675 | 0.2844 | 1.2799 | 1.2976 |

The H0010 BTC leg (E0030) is the instructive case: its observed ratio sits just below the ratio MDE and its observed d just below the d MDE, yet the HAC test rejected — because the significance threshold (t = 1.96) sits below the 80%-power threshold (t = 2.80). A significant result below the MDE is possible; it means the study was underpowered for an effect of that size, which is consistent with the bootstrap CI just including zero and with the usual warning that significant estimates from underpowered designs tend to exaggerate the true effect. The ETH leg (E0031) sits above both MDEs.

Simulation check of the analytic MDE: at beta = 0.0745 (the MDE coefficient for the unit-variance lead-lag design at n = 1414), the lead-lag test's empirical power over 200 replications is **0.790** (MC SE 0.029), against the claimed 0.80 — the normal approximation is doing its job at this sample size.

## 4. Overfitting diagnostics (PBO / DSR)

**Applicability.** The lab has no stored per-day strategy-return series: the seven studies are hypothesis tests, not strategy backtests, and the cost gates keep aggregate statistics only. No lab-real-data PBO or DSR is therefore computed, and none is forced. What follows validates the two kernel methods on synthetic data with known ground truth, so they are ready to use when the lab does have strategy-return series to feed them. Neither diagnostic proves the absence of overfitting; each answers a narrower question under stated assumptions (see `docs/statistical-kernel.md`).

### 4.1 Deflated Sharpe Ratio: illustrative reference table

DSR for a daily Sharpe ratio, Gaussian moments, by trial count N. Read down a column to see the selection penalty grow with N; read across to see it shrink with sample length.

| Daily Sharpe (annualized) | T | DSR, N=1 | DSR, N=10 | DSR, N=100 |
|---------------|---|----------|-----------|------------|
| 0.03 (0.48) | 252 | 0.683 | 0.136 | 0.020 |
| 0.03 (0.48) | 1000 | 0.828 | 0.266 | 0.057 |
| 0.06 (0.95) | 252 | 0.829 | 0.266 | 0.057 |
| 0.06 (0.95) | 1000 | 0.971 | 0.626 | 0.263 |
| 0.10 (1.59) | 252 | 0.943 | 0.504 | 0.173 |
| 0.10 (1.59) | 1000 | 0.999 | 0.943 | 0.735 |

The table's message: a daily Sharpe of 0.03 (about 0.48 annualized) never comes close to the 0.95 skill threshold (best case 0.828, with no selection at T = 1000), while a daily Sharpe of 0.10 (about 1.59 annualized) clears it only at T = 1000 with no selection (0.999); after 10 trials at T = 252 it falls to 0.504. The DSR's bite is on marginal Sharpe ratios, which is where selection bias does its damage.

### 4.2 PBO: synthetic scenario validation

| Scenario | Ground truth | PBO | Mean relative rank | Splits |
|----------|--------------|-----|--------------------|--------|
| Persistent edge | one strategy has a real edge | 0.000 | 0.941 | 70 |
| Pure noise | no strategy has an edge | 0.534 | 0.457 | 12870 |
| Sign-flipping edges | edges reverse between in/out-of-sample | 1.000 | 0.117 | 70 |

The method behaves as theory requires: PBO near 0 when the in-sample-optimal strategy has a genuine persistent edge, near 0.5 under pure noise (the in-sample winner's out-of-sample rank is uniform), and near 1 when in-sample edges systematically reverse out-of-sample.

## 5. Interpretation and limitations

1. **The lab-wide reading is harsher than the within-study reading, as it should be.** Pooling 37 tests into one family raises the bar; 4 of 6 supported edges clear the Holm bar and 5 of 6 clear the BH bar. The 2 that do not clear Holm (E0030, E0031) are the legs of one hypothesis (H0010), and the hypothesis-level verdict was decided by its own preregistered family, which stands.
2. **The procedures are calibrated.** The HAC test holds its size, Holm controls FWER, and the bootstrap interval is approximately calibrated at the lab's sample sizes. Nothing in the calibration suggests the lab's null results come from broken machinery.
3. **The designs are powered for large effects only.** 3 of 7 lead-lag MDEs sit at or above the lab's own 0.005 partial-R^2 threshold (below it: T0004, T0005, T0011, T0016, whose larger samples push their MDEs down), and every observed lead-lag effect sits below its MDE. The lab's null results rule out large effects; they do not rule out small ones. Future studies that hunt small effects need larger samples or sharper designs, not more tests on the same data.
4. **Known caveats are restated, not resolved.** E0026's mechanicality and E0030's bootstrap marginality are properties of the underlying studies; this audit records them alongside the corrected p-values rather than letting the corrections stand alone.
5. **Dependence limits the pooled reading.** The 36 tests reuse the same data (the same FOMC events feed E0023 and E0032; the same BTC/ETH daily panel feeds several lead-lag tests), so the lab-wide family is not 36 independent draws. Holm remains valid under arbitrary dependence; BH is indicative only, and the Storey pi0 estimate assumes independence too.
6. **What this audit does not do.** It does not re-judge any verdict, does not compute a lab-real-data PBO/DSR (no strategy series exist), and does not turn the H0010/H0011 findings into trading signals — both are level/event effects on known dates, not forecasts.

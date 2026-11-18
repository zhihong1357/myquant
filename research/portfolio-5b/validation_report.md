# Stage 5b shadow-evaluation validation report

- Validated at: 2026-11-18T20:02:28.866550+00:00
- Offline and deterministic: fixed seeds, no network, no clock reads inside the scoring (scored_at is an input). Re-running reproduces this report except this timestamp line, and the ledger byte-identically.
- Synthetic grid: daily from 2026-01-01T16:00Z, 1D horizon, outcomes are log returns over [event_time, target_time].
- Seeds: {"break_after": 405, "break_before": 404, "decay_bootstrap": 505, "decay_noise": 304, "decay_outcomes": 303, "noise_outcomes": 202, "noise_predictions": 203, "oracle_outcomes": 101, "shift_bootstrap": 606}.

## Oracle stream (perfect foresight)

- Design: predictions equal realized values exactly, n = 200, outcomes N(0, 0.02). A mechanical check on the scoring machinery.
- Log-return metrics:
- log_return: n=200, MSE=0.000000, MAE=0.000000, bias=0.000000
  - correlation=1.0000
  - hit_rate=1.0000
  - zero baseline MSE=0.000461, skill_vs_zero=1.0000
  - baseline 'lag': matched=198, MSE=0.000877, skill=1.0000
- Direction metrics:
- direction: n=200, MSE=0.000000, MAE=0.000000, bias=0.000000
  - accuracy=1.0000
  - confusion: TP=95 FP=0 TN=105 FN=0 zeros_predicted=0 zeros_outcome=0
  - zero baseline MSE=1.000000, skill_vs_zero=1.0000
- Checks:
  - PASS: oracle MSE is exactly 0
  - PASS: oracle skill vs zero is exactly 1
  - PASS: oracle hit rate is exactly 1
  - PASS: oracle correlation is exactly 1
  - PASS: oracle direction accuracy is exactly 1
  - PASS: oracle stream has no unscored predictions

## Noise stream (no signal)

- Design: predictions are small-amplitude independent noise (0.1 x N(0, 0.02)), n = 500. A same-scale independent predictor would score skill near -1 against the zero baseline (pure added variance), so the null stream is deliberately weak; the check is that a signal-free stream scores near zero skill and near-chance hit rate.
- Log-return metrics:
- log_return: n=500, MSE=0.000427, MAE=0.016478, bias=0.001235
  - correlation=0.0161
  - hit_rate=0.5260
  - zero baseline MSE=0.000424, skill_vs_zero=-0.0071
  - baseline 'lag': matched=498, MSE=0.000817, skill=0.4796
- Direction metrics:
- direction: n=500, MSE=1.984000, MAE=0.992000, bias=-0.048000
  - accuracy=0.5040
  - confusion: TP=119 FP=118 TN=133 FN=130 zeros_predicted=0 zeros_outcome=0
  - zero baseline MSE=1.000000, skill_vs_zero=-0.9840
- Note: skill vs the lag baseline is 0.4796 here — the lag fixture is a weak baseline on iid returns (MSE near 2*sigma^2), so beating it says little; the zero baseline is the meaningful reference for a no-signal stream.
- Checks:
  - PASS: noise skill vs zero within +/-0.15 (got -0.0071)
  - PASS: noise hit rate within (0.45, 0.55) (got 0.5260)
  - PASS: noise direction accuracy within (0.42, 0.58) (got 0.5040)

## Decaying-signal stream

- Design: prediction = beta_t * outcome + noise, beta_t = 0.4 * 0.5**(t / 100), noise N(0, 0.2 * 0.02), n = 1000. True half-life: 100 predictions. Rolling skill uses the zero baseline with a 40-prediction window.
- Log-return metrics:
- log_return: n=1000, MSE=0.000350, MAE=0.014679, bias=-0.000043
  - correlation=0.2470
  - hit_rate=0.5680
  - zero baseline MSE=0.000372, skill_vs_zero=0.0607
  - baseline 'lag': matched=998, MSE=0.000788, skill=0.5549
- Rolling skill (window 40, 961 defined windows): first 0.444, last -0.110.
- Trend: slope -0.000400 per prediction, HAC p-value 4.024e-08 (max_lag 39).
- Decay estimate: detected=True, half-life 129.5 predictions (truth 100), 95% interval [88.3, 189.9], fit R-squared 0.846, stable=True.
- Skill flags: 15 (first at 2026-11-14T16:00:00+00:00, rolling-window index 278).
- Checks:
  - PASS: decay detected (significant negative trend, good fit)
  - PASS: estimated half-life within (50.0, 200.0) of truth 100 (got 129.5)
  - PASS: at least one skill_below_zero flag fires

## Regime-break stream

- Design: outcomes N(0, 0.02) for indices 0-249, then N(0.03, 0.04) from index 250 (break at 2026-09-08T16:00:00+00:00); n = 500; predictions are the lag fixture.
- Log-return metrics:
- log_return: n=498, MSE=0.002041, MAE=0.033592, bias=-0.000178
  - correlation=0.1316
  - hit_rate=0.5904
  - zero baseline MSE=0.001349, skill_vs_zero=-0.5131
- PSI (reference = outcomes 0-99, 100-outcome windows, 10 bins):
  - window ending 2026-04-10T16:00:00+00:00: PSI 0.000
  - window ending 2026-07-19T16:00:00+00:00: PSI 0.207
  - window ending 2026-10-27T16:00:00+00:00: PSI 1.062
  - window ending 2027-02-04T16:00:00+00:00: PSI 1.321
  - window ending 2027-05-15T16:00:00+00:00: PSI 1.168
- PSI flags: 3 (first at 2026-10-27T16:00:00+00:00, value 1.062); the break sits inside the window ending 2026-10-27T16:00:00+00:00.
- Note: the last fully pre-break window reads PSI 0.207, close to the 0.25 alarm — sampling noise at this window size (100 outcomes, 10 bins), not a missed break. The threshold's noise floor is part of why a flag is a prompt, not a conclusion.
- Window shift (reference 0-99 vs current 250-349): mean difference 0.0301 (HAC SE 0.0052, p 6.04e-09), volatility ratio 2.096 (95% interval [1.677, 2.580]).
- Checks:
  - PASS: at least one PSI flag fires after the break
  - PASS: first PSI flag at the first window containing post-break data (2026-10-27T16:00:00+00:00); break at index 250 (2026-09-08T16:00:00+00:00)
  - PASS: window shift detects the mean jump (diff 0.0301, p 6.04e-09)
  - PASS: volatility ratio near 2 (got 2.096)

## Real panel: lag-return fixture (framework check, not a strategy)

- Panel: 5a daily panel, 49 confirmed OKX 1D bars per instrument (2026-09-30T16:00Z to 2026-11-18T16:00Z); 47 fixture predictions per instrument per target, scored at 2026-11-19T16:00Z. The fixture is naive by construction (next return = last return).
- BTC-USDT-SWAP:abs_log_return:
  - abs_log_return: n=47, MSE=0.000326, MAE=0.012914, bias=-0.000036
    - zero baseline MSE=0.000413, skill_vs_zero=0.2110
- BTC-USDT-SWAP:log_return:
  - log_return: n=47, MSE=0.000848, MAE=0.021731, bias=0.000620
    - correlation=-0.1291
    - hit_rate=0.4255
    - zero baseline MSE=0.000413, skill_vs_zero=-1.0523
- ETH-USDT-SWAP:abs_log_return:
  - abs_log_return: n=47, MSE=0.000569, MAE=0.017004, bias=-0.000084
    - zero baseline MSE=0.000809, skill_vs_zero=0.2963
- ETH-USDT-SWAP:log_return:
  - log_return: n=47, MSE=0.001631, MAE=0.028670, bias=0.000318
    - correlation=-0.1161
    - hit_rate=0.4255
    - zero baseline MSE=0.000809, skill_vs_zero=-1.0157
- SOL-USDT-SWAP:abs_log_return:
  - abs_log_return: n=47, MSE=0.000844, MAE=0.022075, bias=0.000172
    - zero baseline MSE=0.000959, skill_vs_zero=0.1206
- SOL-USDT-SWAP:log_return:
  - log_return: n=47, MSE=0.002017, MAE=0.035902, bias=0.000172
    - correlation=-0.1793
    - hit_rate=0.4043
    - zero baseline MSE=0.000959, skill_vs_zero=-1.1026
- Summary: log_return skill vs zero ranges -1.10 to -1.02 across instruments (poor, as expected for near-unpredictable daily returns); abs_log_return skill vs zero ranges 0.12 to 0.30 (positive, reflecting volatility clustering in |returns|, not any trading edge). With 47 predictions over seven weeks, nothing is claimed from either.
- Checks:
  - PASS: BTC-USDT-SWAP log_return: all 47 fixture predictions scored
  - PASS: BTC-USDT-SWAP abs_log_return: all 47 fixture predictions scored
  - PASS: ETH-USDT-SWAP log_return: all 47 fixture predictions scored
  - PASS: ETH-USDT-SWAP abs_log_return: all 47 fixture predictions scored
  - PASS: SOL-USDT-SWAP log_return: all 47 fixture predictions scored
  - PASS: SOL-USDT-SWAP abs_log_return: all 47 fixture predictions scored

## Ledger

- `shadow_ledger.jsonl`: 3180 scored-prediction records across all streams (one JSON object per line, with a stream label), deterministic: re-running reproduces the file byte-identically.

## Limitations

- The synthetic streams use Gaussian returns and a daily grid; they validate the machinery, not any market behaviour.
- The decay half-life is a fragile estimate: it is reported with its bootstrap interval, fit R-squared and stability flag, and the rolling window smooths the decay (the estimate is a property of the rolling series, not of the underlying signal directly).
- PSI thresholds (0.1 / 0.25) are conventional detection cutoffs, not significance levels; a flag is a prompt to look, not a conclusion that the distribution changed.
- The real-panel check covers 47 predictions per instrument over seven weeks: far too few to say anything about the fixture, and nothing is claimed from it.
- No KS test is implemented: PSI plus the window shift cover distribution drift, and a second overlapping detector was not added.

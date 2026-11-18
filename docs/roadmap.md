# Roadmap

## Stage 0 — Bootstrap and research constitution
- [x] Create independent repository identity and safety boundary.
- [x] Define initial cross-market research thesis.
- [x] Establish typed data and hypothesis contracts.
- [x] Establish append-only experiment ledger.
- [x] Add CI and reproducible development environment.

## Stage 1 — Data and research foundations
- [x] Instrument master and market calendars.
- [x] Source registry and data licensing metadata.
- [x] Immutable raw storage with checksums.
- [x] Canonical observations and point-in-time query.
- [x] Data quality, missingness and timestamp diagnostics (batch-level; expected series must be explicit).
- [x] Experiment runner with strict JSON outputs and failure receipts.
- [x] Synthetic null, lead-lag, common-factor, regime-shift and heavy-tail-with-missing data factory.

## Stage 2A — Research governance
- [x] Immutable, versioned hypothesis preregistration.
- [x] Pre-trial amendments with reason and superseding version.
- [x] Lock hypothesis version when first trial starts.
- [x] Hash-chained, replay-validated hypothesis lifecycle events.
- [x] Bind experiment execution to exact hypothesis version and fingerprint.
- [x] Verify universe, observation cadence, target, horizon, source versions, feature versions, fixed parameters, model, benchmark, costs, primary metric, expected direction and seed.
- [x] Require a declared multiple-testing method and target error rate when multiple tests are planned.
- [x] Evidence-backed statistical decision records for supported/rejected conclusions. (15 records: 6 supported-edge + 9 rejected-hypothesis, generated from the trial ledgers, the registry and the Stage 2B audit summary by `research/decision-records/build_decision_records.py`, drift- and ledger-verified; see `research/decision-records/`.)

## Stage 2B — Statistical research kernel
- [x] Simple/log returns, realized variance and annualized volatility estimators.
- [x] Descriptive lead-lag diagnostics with explicit lag direction and synchronized-input contract.
- [x] OLS regression with full-rank and finite-input validation.
- [x] Newey-West HAC covariance, standard errors and asymptotic inference.
- [x] Common-factor controlled partial lead-lag nested-model comparison.
- [x] Circular block-bootstrap mean confidence intervals and null-mean test.
- [x] Bonferroni, Holm and Benjamini–Hochberg p-value corrections.
- [x] Event-study CAR estimator with explicit expected-return benchmark.
- [x] Overlapping event-window clustering and cluster-level descriptive inference.
- [x] Purged chronological walk-forward splits with label-overlap removal and pre-test embargo.
- [x] Paired out-of-sample forecast scoring with incremental OOS R-squared.
- [x] PBO and Deflated Sharpe Ratio. (Bailey et al. CSCV PBO and Bailey & López de Prado DSR in `src/myquant/stats/overfitting.py`, validated on synthetic scenarios — PBO 0.0 clean / ~0.5 noise / 1.0 overfit; no lab-real-data application, because the lab has no stored strategy-return series — stated, not forced; see `research/statistical-audit-2b/report.md` §4 and `docs/statistical-kernel.md` §10.)
- [x] Calibration and power analysis. (HAC size, block-bootstrap coverage and Holm FWER simulations in `src/myquant/stats/calibration.py`; analytic MDEs plus a simulation check in `src/myquant/stats/power.py`; lab-wide audit in `research/statistical-audit-2b/` — under lab-wide correction 4 of 6 supported edges remain significant (Holm) and 5 of 6 (BH), expected false positives 1.8 vs 8 raw rejections; the lead-lag partial-R² MDE at n = 1,414 is 0.0055, essentially the lab's 0.005 threshold, and every observed lead-lag effect sits below its MDE; see `docs/statistical-kernel.md` §11–12.)
- [x] Evidence-backed statistical decision records. (Same 15 records as the Stage 2A item; see `research/decision-records/`.)

## Stage 3 — Cross-market transmission research
- [x] Synchronized daily panel.
- [x] First empirical study: BTC/ETH perpetual transmission (H0001, trial T0001 — rejected, no lag-1 evidence; see `docs/studies/btc-eth-transmission-001.md`). Per the user's decision, Stage 3's first study follows the crypto-perpetual direction; MOVE/VIX/VXN remains a planned item below.
- [x] Second empirical study: low-volatility regime-conditional transmission (H0002, trial T0002 — rejected on fresh dimensions: new pair BTC→SOL daily and new frequency BTC→ETH 1H, plus a Hyperliquid cross-venue check; see `docs/studies/lowvol-transmission-002.md`).
- [ ] Forward test of the original BTC→ETH daily low-volatility hypothesis (H0003, preregistered; trial runs when 60 low-volatility forward rows exist, expected around 2027-03).
- [x] Market graph and edge registry (12 nodes; 36 tested edges, 30 rejected and 6 supported; 1 pending H0003 forward test; 2 descriptive checks; 123 untested candidate pairs; see `docs/market-graph.md` and `research/graph/registry.json`, both generated from the trial ledgers by `research/graph/build_graph.py`).
- [x] MOVE/VIX/VXN conditional repricing study (H0004, trial T0004 — rejected: lag-1 TYVIX log changes do not predict next-day VIX log changes, daily or weekly; see `docs/studies/move-vix-transmission-003.md`). MOVE has no free source, so the study uses TYVIX via FRED VXTYN (2003–2020) as the rates implied-volatility measure; the cost gate is informational (no free VIX futures series).
- [x] Rates-credit-equity-options event studies (H0007, trial T0010 — rejected: no significant VIX CAR[0,+1] after Holm, standardized −0.15 vs −0.3 threshold; H0008, trial T0009 — rejected: SPX-on-DGS10 cross-event slope positive, R² 0.0057, no split-half replication; see `docs/studies/fomc-event-study-005.md`). First real-data use of the event-study CAR estimator; the FOMC calendar is extracted from federalreserve.gov pages and cross-checked (199 scheduled meetings, 2003–2027). Trial T0008 failed on an over-strict cycle-boundary guard before any results were computed; the corrected trial re-ran as T0010.
- [x] Macro release and auction windows (H0009, trial T0011 — rejected: no macro-window transmission effect, primary interaction +0.0003, p = 0.9982, all four criteria failed; H0010, trial T0012 — supported: macro-window mean |log return| ratio 1.2504 for BTC and 1.2976 for ETH, both Holm-adjusted p < 0.01, the lab's first supported hypothesis; see `docs/studies/macro-windows-006.md`). The macro window is one OKX daily bar per FOMC statement / CPI release (CPI bar = day before release, FOMC bar = statement day; both offsets DST-independent). The CPI calendar is transcribed from BLS schedule pages by text fetch (BLS returns HTTP 403 to direct requests) and cross-checked; the Treasury auction calendar comes from the Fiscal Data API and is cross-checked against TreasuryDirect (descriptive only).
- [x] Options expiry and dealer-hedging proxy study (H0005, trial T0005 — rejected: no expiry-window transmission effect, all four criteria failed; H0006, trial T0007 — rejected: no expiry-window volatility uplift, BTC mean |log return| ratio 1.0001; see `docs/studies/options-expiry-004.md`). The expiry calendar is rule-constructed (last Friday of month, 08:00 UTC) and verified against listed contracts and Deribit documentation; the window is only a proxy for dealer-hedging intensity — public data cannot verify dealer positions or gamma.
- [x] Publication-lag-aware positioning study (H0011, trial T0013 — supported: the FOMC TYVIX event response survives a one-trading-day FRED publication lag, lagged CAR −0.0302, Holm p = 5.2e-09, standardized −0.516, the lab's second supported hypothesis; the lagged VIX leg is significant too because the day +1 rebound drops out of the lagged window; H0012, trial T0015 — rejected: the latest published CPI MoM does not predict next-day SPX returns, coef −0.0374, Holm p = 0.755, partial R² 0.00010, holdout OOS −0.00034; the naive reference-month alignment matches PIT on the daily tests and inflates only the release-day subsample; see `docs/studies/publication-lag-007.md`). FRED posts day-t values the next business day (verified by behaviour before preregistration: VIXCLS/DGS10 fetched 2026-11-18 end 2026-11-16); the CPI step predictor takes only 69 distinct values over 2021–2026. Trial T0014 failed on the skipped-release guard before any results were computed; the corrected trial re-ran as T0015.

## Stage 4 — Microstructure and execution realism
- [x] Trade and quote normalization (OKX trades/books/ticker adapter, canonical `Trade` and `BookSnapshot` records; see `docs/microstructure.md`). OKX `/market/history-trades` reaches back ~90 days (oldest retrievable trade 2026-08-20, found by bisection), but at ~40 trades/s the full window is ~3M pages and effectively unpullable; the validation dataset is two complete UTC hours (2026-11-18 05:00–07:00 UTC) plus book snapshots before and after.
- [x] Trade-based order-flow metrics (bucketed CVD, volume/count imbalance, VWAP, large-trade share, intensity at 1m/5m/1H; descriptive only, no signals; see `docs/microstructure.md` and `research/microstructure-4a/validation_report.md`).
- [ ] L2 order-book reconstruction where licensed data permits. Snapshot parsing is done in 4a; continuous reconstruction needs a WebSocket stream and a forward recorder (design only in `docs/microstructure.md`), pending a later decision — no recorder, cron or background process is built in this PR.
- [x] Conservative paper fill model (paper orders with decision/available/arrival clocks, resting-limit fills on opposite-aggressor prints at or through the limit with a last-in-queue rule, crossed-at-arrival taker fills capped at the limit, market fills at the book or first-print fallback, explicit missed-fill accounting; see `docs/execution.md` and `src/myquant/execution/`).
- [x] Fees, spread, slippage, impact and financing (OKX futures Standard Group fee table verified from OKX's own fee notice, effective 2026-09-09, read 2026-11-18 — Regular 0.02% maker / 0.05% taker; half-spread crossing vs arrival mid; configurable adverse slippage, default 1 bp; linear impact vs top-5 depth, default coefficient 5 bps, uncalibrated; 8-hour funding on the 00:00/08:00/16:00 UTC grid with the rate as an input parameter — no funding-rate series pulled, a documented data gap; the gap was closed in Stage 5a by the historical funding-rate series, see the Stage 5 items below).
- [x] Latency and stale-data stress tests (order latency scanned 0/100ms/500ms/1s with explicit missed-fill accounting; snapshots usable only within a configurable max age, default 5 s — stale books are unknown, never held; queue-ahead fallback scanned 0/100/1,000 contracts; see `research/microstructure-4b/stress_report.md`).

## Stage 5 — Portfolio and paper research
- [x] Historical funding-rate series (closes the Stage 4b data gap: OKX `/public/funding-rate-history`, ~93 days, 280 settled rates per instrument for BTC/ETH/SOL, complete grid; `compute_funding_from_series` prices funding at historical rates, no interpolation — see `research/funding-history/funding_report.md` and `docs/portfolio.md`).
- [x] Unified prediction contract across horizons. (Typed contract with target definitions, horizon, event/available clocks with PIT enforcement and a strict query that refuses not-yet-available predictions, plus a labelled lag-return fixture generator — see `src/myquant/portfolio/predictions.py` and `docs/portfolio.md`.)
- [x] Risk model and exposure aggregation. (Long/short net/gross notional, concentration, leverage; sample covariance + Ledoit–Wolf shrinkage toward a scaled identity; portfolio volatility; historical-simulation VaR/ES — all descriptive, not predictive; see `src/myquant/portfolio/risk.py` and `docs/portfolio.md`.)
- [x] Paper portfolio and reconciliation. (Perpetuals cash model, average-cost basis, maker/taker fee split, funding tracked separately, event-sampled equity curve; three-way reconciliation with an independent fill-cash-flow cross-check — residuals at 1e-11..1e-13 USDT on two daily fixtures and a simulator end-to-end tape check; see `src/myquant/portfolio/portfolio.py`, `research/portfolio-5a/validation_report.md` and `docs/portfolio.md`.)
- [x] Forward shadow evaluation. (Forward-only scoring of prediction streams against a caller-provided outcome provider: scoring strictly after target_time, missing outcomes recorded as unscored, optional half-open fit window whose predictions are refused scoring; per-target metrics with MSE/MAE/bias, correlation and hit rate for log returns, accuracy and confusion counts for direction; every score against the zero baseline and named baselines matched like-for-like, skill = 1 − MSE/MSE_baseline; deterministic scored-predictions ledger — see `src/myquant/portfolio/shadow.py`, `research/portfolio-5b/validation_report.md` and `docs/portfolio.md`.)
- [x] Drift and alpha-decay monitoring. (Rolling/expanding performance with None for incomplete windows; PSI on equal-frequency reference bins with an epsilon floor for empty bins; window shift with a HAC mean difference and a block-bootstrap volatility-ratio interval; linear trend fits with HAC standard errors; exponential-decay estimation that reports "not detected" on a non-significant trend or a poor fit and otherwise a half-life with a bootstrap interval, R-squared and stability flag; configurable alert rules emitting flags, not conclusions — see `src/myquant/portfolio/drift.py`, `research/portfolio-5b/validation_report.md` and `docs/portfolio.md`.)

Stage 5 is complete: prediction contract, risk model, paper portfolio, funding history, shadow evaluation and drift monitoring are all in place. The lab still has no real strategy to run through them.

## Stage 6 — AI research intelligence
- [x] Hypothesis planner — ranks the 123 untested candidate pairs by explicit criteria (supported-edge adjacency, verified data availability, MDE power feasibility) with a hard anti-retest guard and preregistration draft templates (99 ranked, 24 unrankable, top-10 a 34-way tie at 1.00, weight-invariant); see `docs/research-intelligence.md` §1 and `research/planner-6a/validation_report.md`.
- [ ] Evidence and source analyst.
- [ ] Experiment/code assistant.
- [ ] Adversarial reviewer.
- [ ] Research librarian and report generator.

Live trading is explicitly out of scope.

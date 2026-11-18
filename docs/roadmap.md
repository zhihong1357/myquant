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
- [ ] Evidence-backed statistical decision records for supported/rejected conclusions.

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
- [ ] PBO and Deflated Sharpe Ratio.
- [ ] Calibration and power analysis.
- [ ] Evidence-backed statistical decision records.

## Stage 3 — Cross-market transmission research
- [x] Synchronized daily panel.
- [x] First empirical study: BTC/ETH perpetual transmission (H0001, trial T0001 — rejected, no lag-1 evidence; see `docs/studies/btc-eth-transmission-001.md`). Per the user's decision, Stage 3's first study follows the crypto-perpetual direction; MOVE/VIX/VXN remains a planned item below.
- [x] Second empirical study: low-volatility regime-conditional transmission (H0002, trial T0002 — rejected on fresh dimensions: new pair BTC→SOL daily and new frequency BTC→ETH 1H, plus a Hyperliquid cross-venue check; see `docs/studies/lowvol-transmission-002.md`).
- [ ] Forward test of the original BTC→ETH daily low-volatility hypothesis (H0003, preregistered; trial runs when 60 low-volatility forward rows exist, expected around 2027-03).
- [x] Market graph and edge registry (11 nodes; 28 tested edges, 24 rejected and 4 supported; 1 pending H0003 forward test; 2 descriptive checks; 103 untested candidate pairs; see `docs/market-graph.md` and `research/graph/registry.json`, both generated from the trial ledgers by `research/graph/build_graph.py`).
- [x] MOVE/VIX/VXN conditional repricing study (H0004, trial T0004 — rejected: lag-1 TYVIX log changes do not predict next-day VIX log changes, daily or weekly; see `docs/studies/move-vix-transmission-003.md`). MOVE has no free source, so the study uses TYVIX via FRED VXTYN (2003–2020) as the rates implied-volatility measure; the cost gate is informational (no free VIX futures series).
- [x] Rates-credit-equity-options event studies (H0007, trial T0010 — rejected: no significant VIX CAR[0,+1] after Holm, standardized −0.15 vs −0.3 threshold; H0008, trial T0009 — rejected: SPX-on-DGS10 cross-event slope positive, R² 0.0057, no split-half replication; see `docs/studies/fomc-event-study-005.md`). First real-data use of the event-study CAR estimator; the FOMC calendar is extracted from federalreserve.gov pages and cross-checked (199 scheduled meetings, 2003–2027). Trial T0008 failed on an over-strict cycle-boundary guard before any results were computed; the corrected trial re-ran as T0010.
- [x] Macro release and auction windows (H0009, trial T0011 — rejected: no macro-window transmission effect, primary interaction +0.0003, p = 0.9982, all four criteria failed; H0010, trial T0012 — supported: macro-window mean |log return| ratio 1.2504 for BTC and 1.2976 for ETH, both Holm-adjusted p < 0.01, the lab's first supported hypothesis; see `docs/studies/macro-windows-006.md`). The macro window is one OKX daily bar per FOMC statement / CPI release (CPI bar = day before release, FOMC bar = statement day; both offsets DST-independent). The CPI calendar is transcribed from BLS schedule pages by text fetch (BLS returns HTTP 403 to direct requests) and cross-checked; the Treasury auction calendar comes from the Fiscal Data API and is cross-checked against TreasuryDirect (descriptive only).
- [x] Options expiry and dealer-hedging proxy study (H0005, trial T0005 — rejected: no expiry-window transmission effect, all four criteria failed; H0006, trial T0007 — rejected: no expiry-window volatility uplift, BTC mean |log return| ratio 1.0001; see `docs/studies/options-expiry-004.md`). The expiry calendar is rule-constructed (last Friday of month, 08:00 UTC) and verified against listed contracts and Deribit documentation; the window is only a proxy for dealer-hedging intensity — public data cannot verify dealer positions or gamma.
- [ ] Publication-lag-aware positioning study.

## Stage 4 — Microstructure and execution realism
- [ ] Trade and quote normalization.
- [ ] Trade-based order-flow metrics.
- [ ] L2 order-book reconstruction where licensed data permits.
- [ ] Conservative paper fill model.
- [ ] Fees, spread, slippage, impact and financing.
- [ ] Latency and stale-data stress tests.

## Stage 5 — Portfolio and paper research
- [ ] Unified prediction contract across horizons.
- [ ] Risk model and exposure aggregation.
- [ ] Paper portfolio and reconciliation.
- [ ] Forward shadow evaluation.
- [ ] Drift and alpha-decay monitoring.

## Stage 6 — AI research intelligence
- [ ] Hypothesis planner.
- [ ] Evidence and source analyst.
- [ ] Experiment/code assistant.
- [ ] Adversarial reviewer.
- [ ] Research librarian and report generator.

Live trading is explicitly out of scope.

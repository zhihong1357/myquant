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
- [ ] Market graph and edge registry.
- [ ] MOVE/VIX/VXN conditional repricing study.
- [ ] Rates-credit-equity-options event studies.
- [ ] Macro release and auction windows.
- [ ] Options expiry and dealer-hedging proxy study.
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

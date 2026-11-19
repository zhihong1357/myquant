# MyQuant — Personal Alpha Intelligence Lab

MyQuant is an independent, research-first quantitative market intelligence system.

Its first research thesis is **cross-market expectation transmission**: whether information is incorporated into related markets at different speeds, whether those delays are measurable out of sample, and whether any resulting opportunity survives realistic execution costs.

## Operating principles

1. Research before trading.
2. Paper-only: no live brokerage or exchange order execution.
3. Hypotheses are not facts; every market mechanism must be tested.
4. Point-in-time correctness is mandatory.
5. A signal is not an edge until it survives out-of-sample validation and costs.
6. Failed experiments are retained.
7. AI may propose and critique research; deterministic code owns calculations and acceptance gates.

## Initial research scope

- Rates and government bonds
- Credit markets
- Equity index and single-name options
- Equity indices and ETFs
- Crypto spot, perpetuals and options
- FX and commodities
- Cross-market relationships

The system is designed for multiple horizons: sub-hourly, intraday, daily and multi-day. Data onboarding is staged; "all markets" is an architectural goal, not a claim that every market is already covered.

## Current foundation

- Provider-neutral instruments and timezone-aware trading calendars
- Versioned data-source registry with explicit research-use permission metadata
- Immutable content-addressed raw payloads and provenance manifests
- Immutable Parquet observations with point-in-time revision queries
- Batch-level data-quality and coverage diagnostics
- Deterministic synthetic scenarios: null, lead-lag, common-factor, regime-shift and heavy-tail-with-missing stress
- Reproducible experiment runner with append-only hash-chained results
- Immutable hypothesis preregistration with chronological splits, purge gaps and multiple-testing plans
- Trial enforcement against exact hypothesis versions, data-source versions, feature versions and fixed model parameters
- OLS regression, Newey-West HAC inference and common-factor controlled partial lead-lag diagnostics
- Purged chronological walk-forward splits, auditable embargo/purge indices and paired out-of-sample forecast scoring
- OKX and Hyperliquid public REST source adapters (standard library only) and synchronized multi-instrument panels; first real-data study (BTC/ETH perpetual transmission, H0001) completed and rejected — see `docs/studies/btc-eth-transmission-001.md`; second study (low-volatility regime-conditional transmission, H0002) completed and rejected — see `docs/studies/lowvol-transmission-002.md`
- FRED public CSV and Yahoo Finance chart adapters (standard library only); third real-data study (MOVE/VIX/VXN conditional repricing, H0004, using TYVIX via FRED VXTYN as the rates-volatility measure) completed and rejected — see `docs/studies/move-vix-transmission-003.md`
- Deribit public REST adapter (standard library only) and a rule-constructed options-expiry calendar (last Friday of month, 08:00 UTC, verified against listed contracts and Deribit documentation); fourth real-data study (options-expiry window volatility and transmission, H0005/H0006) completed and rejected — see `docs/studies/options-expiry-004.md`
- FOMC meeting calendar parser for federalreserve.gov pages (standard library only) with cross-checked schedule extraction, constant-mean event-study helpers and diff-then-join level changes for rate legs; fifth real-data study (FOMC event study: rates-credit-equity-options, H0007/H0008) completed and rejected — see `docs/studies/fomc-event-study-005.md`
- Macro release calendar module (FOMC statement / CPI release window mapping with DST-independent day offsets, locked by tests on known dates), BLS CPI calendar transcribed from schedule pages by text fetch and cross-checked, and a Treasury auction calendar from the Fiscal Data API cross-checked against TreasuryDirect; sixth real-data study (macro release and auction windows, H0009/H0010) completed — H0009 rejected (no macro-window transmission), H0010 supported (macro-window volatility uplift, the lab's first supported hypothesis) — see `docs/studies/macro-windows-006.md`
- Publication-lag alignment module (per-series FRED lag shifts on own dates, CPI step functions in release-day and reference-month alignment) and a verified one-trading-day FRED posting lag; seventh real-data study (publication-lag-aware positioning, H0011/H0012) completed — H0011 supported (the FOMC TYVIX event response survives the lag, the lab's second supported hypothesis), H0012 rejected (the latest published CPI MoM does not predict next-day SPX returns) — see `docs/studies/publication-lag-007.md`
- Eighth real-data study (credit-spread transmission, H0013) completed and rejected — the latest available BAA10Y spread change (lagged 2 trading days by the verified publication lag) does not predict next-day SPX returns (coef +1.80e-05 per bp, p = 0.89, partial R² 2.19e-05, n = 5,957); the naive lookahead alignment is also null, and the reverse placebo (SPX→BAA10Y) is nominally significant but descriptive only — see `docs/studies/credit-spread-spx-008.md`. First real use of the 6c scaffold; seven gaps found and fixed by hand (see the report's scaffold-feedback section).
- Ninth real-data study (credit-spread transmission to Treasury volatility, H0014) completed and rejected — the latest available BAA10Y spread change (lagged 2 trading days by the verified publication lag) does not predict the next-day TYVIX log change (coef −0.000126 per bp, wrong sign vs the preregistered positive expectation, p = 0.75, partial R² 6.10e-05, n = 4,327); the naive lookahead alignment is also null, the reverse placebo (TYVIX→BAA10Y) is not significant, and the holdout OOS incremental R² is −0.000983 — see `docs/studies/credit-spread-tyvix-009.md`. Second real use of the 6c scaffold; no new gaps (the bar_seconds fix from study 008 verified).
- Market graph and edge registry generated from the trial ledgers (12 nodes, 38 tested edges — 32 rejected, 6 supported — plus 1 pending forward test, 2 descriptive checks and 121 untested candidate pairs) — see `docs/market-graph.md` and `research/graph/registry.json`
- Microstructure foundation (Stage 4a): OKX trades/books/ticker adapter with paginated history-trades fetch, canonical `Trade` and `BookSnapshot` records with counted rejection handling, and bucketed trade-based order-flow metrics (CVD, imbalances, VWAP, large-trade share, intensity) — descriptive only, no signals; OKX history-trades verified to reach back ~90 days — see `docs/microstructure.md`
- Execution realism (Stage 4b): conservative paper fill model (resting-limit fills on opposite-aggressor prints with a last-in-queue rule, crossed-at-arrival taker fills, market fills at the book or first-print fallback, explicit missed-fill accounting), OKX futures fee schedule verified from OKX's own notice (Regular 0.02% maker / 0.05% taker), and cost models for spread crossing, slippage, impact and 8-hour funding, with latency and stale-data stress tests — see `docs/execution.md`
- Statistical closeout (Stage 2B): PBO and Deflated Sharpe Ratio diagnostics, calibration simulations (HAC size, block-bootstrap coverage, Holm FWER) and minimum-detectable-effect power analysis — see `docs/statistical-kernel.md` §10–12; lab-wide multiple-testing audit over all 38 tested edges (under lab-wide correction 3 of 6 supported edges remain significant by Holm, 5 of 6 by BH — E0033 dropped out of the Holm set when the family grew to 38) — see `research/statistical-audit-2b/report.md`; 17 evidence-backed statistical decision records (6 supported-edge, 11 rejected-hypothesis) generated from the ledgers and drift- and ledger-verified — see `research/decision-records/`
- Paper portfolio (Stage 5a): historical funding-rate series closing the 4b data gap (OKX, ~93 days, BTC/ETH/SOL), a typed prediction contract with point-in-time enforcement, a descriptive risk model (exposure aggregation, Ledoit–Wolf covariance, historical VaR/ES), and a paper portfolio with three-way reconciliation (residuals at 1e-11..1e-13 USDT on daily fixtures and a simulator end-to-end tape check) — see `docs/portfolio.md`
- Forward shadow evaluation and drift monitoring (Stage 5b): forward-only scoring of prediction streams with hard discipline (scoring strictly after target_time, missing outcomes unscored, in-sample fit window refused), per-target metrics against zero and named baselines with skill scores, and drift monitoring (rolling performance, PSI, HAC window shift, exponential-decay half-life with bootstrap interval and stability flag, configurable alert flags) — validated on four synthetic streams with known ground truth (oracle MSE exactly 0; decaying signal half-life 129.5 vs truth 100) and the lag fixture on the real panel — see `docs/portfolio.md` and `research/portfolio-5b/validation_report.md`
- Hypothesis planner (Stage 6a): deterministic ranking of the 120 untested candidate pairs by supported-edge adjacency, verified data availability and MDE power feasibility, with a hard anti-retest guard and preregistration draft templates — 108 ranked, 12 unrankable (TYVIX pre-2021 panel only; VXN re-fetched 2026-11-19), top-10 a 32-way tie at 1.00 — see `docs/research-intelligence.md`
- Experiment/code assistant (Stage 6c): deterministic study scaffold generator (StudySpec + planner-draft input) that writes the standard 13-file study directory — README, design, preregister/fetch/run_trial skeletons with TODO-marked design sections, contract stubs, a parked planner draft and a report template — with guards that refuse unknown sources and existing targets; the scaffold wires structure and never designs or starts a study — see `docs/research-intelligence.md` §3 and `research/scaffold-6c/validation_report.md`. First real use: study 008 (H0013/T0016), generated from the planner's BAA10Y→SPX template; seven gaps found and fixed by hand — see `docs/studies/credit-spread-spx-008.md` § Scaffold feedback. Second real use: study 009 (H0014/T0017), generated from the planner's BAA10Y→TYVIX template; no new gaps, and the bar_seconds fix verified (`BAR_SECONDS = None` in the generated file). Third real use: study 010 (H0015/T0018), generated from the planner's BAA10Y→VIX template; no new gaps, the bar_seconds fix verified again, and no real-ID placeholder specs in the generated files.
- Adversarial reviewer (Stage 6d): read-only study auditor (ledger chain and anchor verification, preregistration binding, multiple-testing recomputation, verdict re-derivation, trial-ID sequence, report–ledger table comparison, PIT spot-checks) with UNVERIFIED as a distinct verdict, never a pass — full-lab review 124 checks: 102 pass, 0 fail (its first run found 3 genuine report–ledger discrepancies in studies 003/004/007, confirmed and fixed in the same delivery), 8 unverified (7 PIT caches not retained, study 005's missing anchor), 14 MDE notes; all 6 adversarial fixtures caught — see `docs/research-intelligence.md` §4 and `research/review-6d/validation_report.md`
- Research librarian and report generator (Stage 6e): read-only unified catalog of the lab's records (10 studies, 15 hypotheses, 17 trial records, 42 edges, 18 decision records, 120 candidates, 8 sources, 12 panels) with 11 cross-reference integrity checks — 0 broken links on the real lab, 1 missing optional file (study 005's anchor) — plus a generated lab status report; every number derived by reading a record, deterministic builds with a drift test — see `docs/research-intelligence.md` §5 and `research/library-6e/validation_report.md`

The current implementation is a research foundation, not a live market data service or a proven trading system. Statistical validation and evidence-backed strategy decisions remain future work.

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy src
```

## Project status

No profitability claim is made. Live execution is explicitly out of scope.

License: Proprietary — the repository is public for reading; reuse requires permission.

See [architecture](docs/architecture.md), [research thesis](docs/research-thesis.md), [statistical kernel](docs/statistical-kernel.md), and [roadmap](docs/roadmap.md).

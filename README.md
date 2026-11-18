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
- Market graph and edge registry generated from the trial ledgers (12 nodes, 36 tested edges — 30 rejected, 6 supported — plus 1 pending forward test, 2 descriptive checks and 123 untested candidate pairs) — see `docs/market-graph.md` and `research/graph/registry.json`
- Microstructure foundation (Stage 4a): OKX trades/books/ticker adapter with paginated history-trades fetch, canonical `Trade` and `BookSnapshot` records with counted rejection handling, and bucketed trade-based order-flow metrics (CVD, imbalances, VWAP, large-trade share, intensity) — descriptive only, no signals; OKX history-trades verified to reach back ~90 days — see `docs/microstructure.md`

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

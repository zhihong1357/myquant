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

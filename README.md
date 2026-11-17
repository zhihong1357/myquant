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
- Deterministic synthetic scenarios: null, lead-lag, common-factor and regime-shift
- Reproducible experiment runner with append-only hash-chained results
- Immutable hypothesis preregistration with time-split, purge-gap and multiple-testing declarations
- Trial enforcement against the exact preregistered hypothesis version and fingerprint

The current implementation is a research foundation, not a live market data service or a proven trading system. Statistical validation and strategy acceptance remain future work.

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

See [architecture](docs/architecture.md), [research thesis](docs/research-thesis.md), and [roadmap](docs/roadmap.md).

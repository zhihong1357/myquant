# Architecture

## Design objective
MyQuant is an independent research platform for discovering and validating cross-market and within-market pricing relationships. It is not an execution bot.

## Logical layers

1. **Source adapters** — market data, reference data, calendars, macro releases and news timestamps.
2. **Immutable raw store** — original payloads, source metadata, retrieval time, checksum and revision identity.
3. **Canonical observations** — normalized instruments, units, calendars and timestamps.
4. **Point-in-time (PIT) query layer** — exposes only information available at the decision timestamp.
5. **Feature and event layer** — returns, volatility, spreads, order flow, implied volatility, rates and event windows.
6. **Research layer** — registered hypotheses, lag studies, event studies, statistical inference and robustness checks.
7. **Portfolio and simulation layer** — paper-only positions, conservative fills, fees, financing and risk.
8. **Research intelligence layer** — reports, experiment comparison, model monitoring and AI-assisted critique.

## Core time semantics

- `event_time`: when the event occurred in the source market.
- `available_at`: when the information became available to the strategy.
- `ingested_at`: when MyQuant received and persisted it.
- `decision_time`: timestamp at which a model is allowed to make a decision.

PIT eligibility is governed by `available_at <= decision_time`, not merely by event time. Corrections and revisions must not overwrite what was known historically; they create new versioned observations.

## Cross-market transmission model

Represent markets as nodes and candidate transmission channels as directed, time-varying edges. An edge is a hypothesis, not a hard-coded causal chain.

For each candidate edge, measure:
- source and target market timestamps and calendars;
- source information availability;
- target response time and response magnitude;
- lead/lag stability across regimes;
- common-factor and confounder controls;
- tradability after latency, spread, fees, market impact and financing;
- out-of-sample incremental value over simple baselines.

The system must allow feedback loops and simultaneous adjustment. Do not assume a universal sequence such as rates -> credit -> single-name options -> index options.

## Initial market graph

Candidate nodes:
- sovereign rates and government bonds;
- credit indices, CDS and corporate bonds;
- equity single-name options;
- equity index options;
- cash equities and ETFs;
- FX and commodities;
- crypto spot, perpetuals and options;
- volatility indices and realized volatility.

## Research horizons

Every study declares its own horizon. Initial buckets:
- seconds to minutes (only where source timestamps and data granularity support it);
- 5m to 1h;
- 4h to 1d;
- 1d to 5d;
- weekly/monthly allocation and positioning.

Do not compare raw returns or hit rates across different horizons without normalization and explicit utility definitions.

## Safety boundary
The initial and foreseeable system is paper-only. No live order-routing module is permitted. The simulator is a research model and must disclose its fill assumptions.

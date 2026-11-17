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

- `event_time`: when the event occurred in the source market, or the event the observation refers to.
- `available_at`: when the information became publicly/operationally available to the strategy.
- `ingested_at`: when MyQuant received and persisted it.
- `decision_time`: timestamp at which a model is allowed to make a decision.

PIT eligibility is governed by `available_at <= decision_time`, not merely by event time. Corrections and revisions must not overwrite what was known historically; they create new versioned observations. Historical records preserve their source definition version. `available_at` is not the date MyQuant later downloaded an archive; it must represent the original information availability time when that can be established.

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

## Stage 1 data and experiment foundations

- **Instrument master:** canonical provider-neutral instrument IDs. Exchange/provider symbols are separate mappings and must never define the identity of an instrument.
- **Market calendars:** IANA timezone, weekdays, local session boundaries, holidays, early closes, and trading-date offsets. This supports Sunday-evening futures sessions assigned to Monday trade dates. Ambiguous or nonexistent DST wall-clock boundaries are rejected rather than silently guessed.
- **Source registry:** provider, timestamp meaning, nominal delay, attribution and explicit license state. Unknown/restricted/prohibited sources are not approved for research use by default. An approved entry requires a documented permission basis; this is an explicit registry assertion, not an automatic legal determination.
- **Raw store:** byte-preserving, content-addressed blobs plus distinct immutable provenance manifests. A checksum is verified on read; different providers may point to the same payload bytes without losing source identity.
- **PIT observation store:** immutable Parquet batches. A query at decision time first hides rows with `available_at` later than the decision, then selects the latest revision independently per instrument/venue/field/event/source-version. Conflicting providers remain separate and ambiguous same-revision collisions are rejected.
- **Quality diagnostics:** summarize coverage against caller-supplied expected series, duplicates, revision collisions, event/availability ordering and ingestion latency. The system does not infer missing bars from absent rows until expected cadence and market calendar are defined.
- **Synthetic factory:** deterministic null, direct lead-lag, common-factor and regime-shift panels. Ground-truth columns exist only to verify research code; they must never be used as model predictors.
- **Experiment runner:** records a unique trial ID, hypothesis ID, seed, code revision, data/config fingerprints, metrics or failure details, and an append-only hash-chain receipt. It does not imply that a trial is statistically valid.

## Stage 2A hypothesis preregistration

A hypothesis must be registered before any experiment can run. The immutable specification includes:

- research question, mechanism, alternative and null hypotheses;
- instrument universe, exact source versions, versioned feature set and prediction target;
- observation frequency, horizon, model definition, fixed parameters, benchmark and cost assumptions;
- chronological train, validation and holdout windows;
- a purge gap no shorter than the forward prediction horizon;
- minimum observations per split, primary metric, expected direction and minimum effect size;
- target error rate, planned test count, multiple-testing family and correction method;
- missing-data policy, confounders, exclusions and random seed;
- explicit acceptance and rejection criteria.

### Multiple-testing threshold semantics

The preregistered `target_error_rate` has meaning determined by the selected correction method:

- **Bonferroni / Holm:** it is the target family-wise error rate (FWER, the chance of at least one false positive within the declared test family).
- **Benjamini–Hochberg:** it is the target false discovery rate (FDR, the expected proportion of false discoveries among rejected hypotheses).
- **No correction:** allowed only when the preregistered family contains exactly one planned test.

The registry records the intended method and threshold. It does not itself calculate adjusted p-values; the statistical kernel must implement the declared method and report it in the evidence record. Merely declaring a correction method does not mean that the correction has been applied.

The registration receives a canonical fingerprint and immutable versioned snapshot. A pre-trial amendment creates a new version with a reason and supersedes the former version. Once the first trial starts, the version is locked; changing the research design requires a new hypothesis ID.

Each trial carries the hypothesis ID, version and fingerprint. Before the callback executes, the runner checks that the trial's universe, observation frequency, target, horizon, source versions, feature versions, model, benchmark, cost model, primary metric, expected direction, random seed and named parameters exactly match the preregistered specification. Trial parameters are scalar, sorted and immutable. The runner changes the hypothesis state from REGISTERED to TESTING before invoking the experiment callback. Failed experiments remain in the trial ledger.

The lifecycle event stream is hash-chained and replay-validated against legal state transitions. The runner does not automatically mark hypotheses SUPPORTED or REJECTED. Those decisions must follow a separate statistical evidence and review step; a state label is not proof of predictive value.

### Timestamp interpretation

`event_time` is the timestamp the observation refers to; it is not necessarily the time the observation became knowable. A forecast or scheduled-event estimate can be published before its future event time. PIT eligibility is determined by `available_at`, while `ingested_at` records when MyQuant received the information. The difference `ingested_at - available_at` measures our ingestion delay, not how quickly the market repriced.

### Initial implementation limits

The initial Parquet PIT query scans the immutable batch files and resolves revisions in Python. This is correct for small research datasets but is not yet a scalable query engine. Partition pruning, compaction, catalog statistics and concurrent-writer coordination are future work. The local immutable file writer, hypothesis registry and trial ledger are single-writer research components, not distributed transaction protocols. Calendar rules are explicit primitives, not a replacement for official historical exchange calendars and exceptional session notices.

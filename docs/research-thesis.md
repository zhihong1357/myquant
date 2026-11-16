# Research Thesis 001 — Cross-Market Expectation Transmission

## Core question
When information or risk is repriced in one market, do related markets adjust at measurably different times, and can a trader observe and act on the residual repricing before it disappears?

## Hypothesis families

### H1 — Asynchronous repricing
Related markets do not always incorporate the same information simultaneously because of different trading hours, participant mandates, liquidity, hedging constraints, access and reporting frequency.

### H2 — Volatility repricing gap
A large standardized move in one volatility/risk market may precede a move in another related market. Candidate example: MOVE versus VIX/VXN. The relationship may be conditional, unstable or absent.

### H3 — Options hedging transmission
Changes in option-implied risk, dealer inventory proxies, expiry concentration or hedging demand may coincide with changes in underlying/index liquidity and realized volatility.

### H4 — Slow institutional allocation
Some public positioning and fund-flow datasets are published with delays and may describe slow-moving allocation rather than actionable real-time positioning. Publication time must be distinguished from observation period.

### H5 — Event-window liquidity changes
Liquidity, spreads and price impact may change around scheduled macro releases, auctions, option expiries, index rebalances and month/quarter-end flows.

## User-provided claims to test, not assume

- A proposed transmission path: government bonds/rates -> credit -> single-name options -> index options.
- A proposed MOVE percentile near the 99th percentile while VXN is near the 34th percentile.
- A proposed 400ms HFT text-to-market reaction time.
- A proposed 70% reduction in dealer hedging after a particular option expiry.
- Participant response horizons ranging from milliseconds to monthly/quarterly allocation cycles.

No threshold, percentile gap, latency, or hedging-volume statistic becomes a production rule until its source, definition, sample, timestamp convention and independent replication are verified.

## Key identification problem
Observed lead-lag correlation is not proof of causal transmission. A common macro factor, asynchronous market hours, stale marks, different sampling frequencies, index construction, or publication delays can create apparent leads.

Every study must compare:
1. naive lead-lag correlation;
2. synchronized observations on common trading intervals;
3. controls for common drivers and volatility regimes;
4. alternative sampling frequencies and timestamp conventions;
5. genuinely out-of-sample stability;
6. executable net value under conservative costs.

## First empirical study
Build a timestamp-aware event/lead-lag panel for a small, well-defined initial set:
- US Treasury yield or liquid Treasury futures proxy;
- MOVE (subject to licensing and history availability);
- VIX and VXN;
- liquid equity index futures/ETF proxy;
- selected credit spread/index proxy.

Begin with daily data to establish definitions and coverage. Intraday research is a separate gate requiring reliable intraday timestamps and synchronized calendars.

## Null hypotheses and rejection
- H0: source-market information does not improve target-market forecasts beyond target's own history and common-factor controls.
- Reject the research hypothesis if the effect is unstable, disappears after synchronization/controls, fails holdout validation, or is smaller than conservative execution and financing costs.

## Evidence policy
Every reported statistic must include source, definition, sample period, timestamp convention, transformation, missing-data policy, and reproducible code reference.

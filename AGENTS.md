# MyQuant Agent Rules

## Mission
Build an independent, research-first, multi-market quantitative research system. Paper-only. No live trading or real order execution.

## Non-negotiable rules
- Do not import, copy, or depend on the finance-research repository. It is a reference only.
- Do not present a hypothesis, mechanism, threshold, or market narrative as an established fact without evidence.
- Every observation and feature must preserve event time, public/usable time, ingestion time, source, and revision/version where applicable.
- A feature is usable only after all of its inputs are usable.
- Never use future information in features, labels, model selection, execution simulation, or reports.
- Keep raw observations immutable; derived datasets must be reproducible from versioned inputs.
- Record every experiment, including failed and abandoned trials.
- Separate hypothesis generation, statistical testing, economic-cost evaluation, and paper simulation.
- AI-generated code and research claims require deterministic tests and independent review.
- Never add live exchange/broker order placement, credential handling, or real-money execution.

## Engineering workflow
1. Inspect the current repository before editing.
2. Make small, reviewable changes with tests.
3. Prefer explicit contracts and simple composable modules over premature frameworks.
4. Do not add dependencies without a concrete need.
5. Do not silently change schemas or experiment definitions; version breaking changes.
6. Run tests and lint before claiming success.
7. Update docs when behavior or contracts change.

## Research discipline
- Register hypotheses before examining holdout results.
- Define target, horizon, universe, sample period, benchmark, costs, and rejection criteria.
- Use chronological validation, purging/embargo where labels overlap, and multiple-testing controls.
- Report effect sizes and uncertainty, not just p-values or win rates.
- Distinguish data latency from market response latency.
- Never infer participant identity or intent from public order-book behavior alone.

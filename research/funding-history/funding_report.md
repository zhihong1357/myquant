# Funding-rate history (Stage 5a)

Settled funding rates from OKX `/public/funding-rate-history` (public, no key), pulled by `research/funding-history/fetch_data.py`. This closes the Stage 4b data gap: funding is no longer only an input parameter — see `src/myquant/execution/funding.py` for the series and its use in the cost model.

## BTC-USDT-SWAP

- Rows: **280** settled rates, 4 pages (4 cached, all checksums verified).
- Range: **2026-08-17T16:00:00+00:00** to **2026-11-18T16:00:00+00:00** (93.0 days of history).
- Grid completeness: 280 rows vs 280 expected grid slots; missing: **none** — every 8-hour settlement in range is present.
- Methods: current_period; formula types: withRate; rows where fundingRate != realizedRate: 0.
- Rate distribution (per 8-hour interval): mean 0.00005397, min -0.00006420, max 0.00010000; 250 positive / 30 negative / 0 zero rows.
- Live cross-check (fetch started 2026-11-18T18:57:47.469474+00:00): the live endpoint's settled rate 0.00006348 at 2026-11-18T16:00:00+00:00 **matches the history row exactly**.
- Live cap/floor at fetch time: [-0.00375000, 0.00375000] per interval; interest-rate component 0.00010000, premium -0.00049205.
- Note: the maximum observed rate over the window equals the interest-rate component exactly (0.0001 per interval). No mechanism is claimed for this; the premium index was negative at fetch time, and the funding formula is not re-derived here.

## ETH-USDT-SWAP

- Rows: **280** settled rates, 4 pages (4 cached, all checksums verified).
- Range: **2026-08-17T16:00:00+00:00** to **2026-11-18T16:00:00+00:00** (93.0 days of history).
- Grid completeness: 280 rows vs 280 expected grid slots; missing: **none** — every 8-hour settlement in range is present.
- Methods: current_period; formula types: withRate; rows where fundingRate != realizedRate: 0.
- Rate distribution (per 8-hour interval): mean 0.00003930, min -0.00010923, max 0.00010000; 233 positive / 47 negative / 0 zero rows.
- Live cross-check (fetch started 2026-11-18T18:57:47.469474+00:00): the live endpoint's settled rate -0.00003481 at 2026-11-18T16:00:00+00:00 **matches the history row exactly**.
- Live cap/floor at fetch time: [-0.00750000, 0.00750000] per interval; interest-rate component 0.00010000, premium -0.00044029.
- Note: the maximum observed rate over the window equals the interest-rate component exactly (0.0001 per interval). No mechanism is claimed for this; the premium index was negative at fetch time, and the funding formula is not re-derived here.

## SOL-USDT-SWAP

- Rows: **280** settled rates, 4 pages (4 cached, all checksums verified).
- Range: **2026-08-17T16:00:00+00:00** to **2026-11-18T16:00:00+00:00** (93.0 days of history).
- Grid completeness: 280 rows vs 280 expected grid slots; missing: **none** — every 8-hour settlement in range is present.
- Methods: current_period; formula types: withRate; rows where fundingRate != realizedRate: 0.
- Rate distribution (per 8-hour interval): mean 0.00003014, min -0.00025376, max 0.00010000; 195 positive / 85 negative / 0 zero rows.
- Live cross-check (fetch started 2026-11-18T18:57:47.469474+00:00): the live endpoint's settled rate 0.00003759 at 2026-11-18T16:00:00+00:00 **matches the history row exactly**.
- Live cap/floor at fetch time: [-0.00750000, 0.00750000] per interval; interest-rate component 0.00010000, premium -0.00040595.
- Note: the maximum observed rate over the window equals the interest-rate component exactly (0.0001 per interval). No mechanism is claimed for this; the premium index was negative at fetch time, and the funding formula is not re-derived here.

## Depth and limits

The endpoint retains about **93 days** of funding history as of 2026-11-19 (oldest row 2026-08-17T16:00:00Z, 280 rows per instrument, complete grid). The exact retention rule is unknown, but the floor moves: a probe minutes before this fetch showed a 281st row (2026-08-17T08:00:00Z) for BTC and SOL that was gone by fetch time, consistent with a rolling retention window. Treat the floor as approximate and re-establish it on every pull. Anything needing funding rates before 2026-08-17 has no data here: the series must not be extended by interpolation or extrapolation, and `compute_funding_from_series` skips settlements with no rate rather than inventing one.

Pagination note: on this endpoint `after=<ms>` pages backwards (rows strictly older than the cursor, newest first); `before` acts as a lower bound and is never used — see `src/myquant/adapters/okx_funding.py`. The first probe of this endpoint paged with `before` and looped over a shrinking subset of the recent window; the corrected probe with `after` reaches the floor in 4–5 pages per instrument.

## Stage 4b cross-reference

Stage 4b recorded a live funding rate of 0.00002150 per interval, read 2026-11-18T08:10:00+00:00 (mid-interval, for the interval ending 2026-11-18T16:00:00+00:00). The settled rate for that interval (history row at 2026-11-18T16:00:00+00:00) is **0.00006348**.

The two numbers differ, as they should: the live rate is a mid-interval estimate that moves with the premium index, while the settled rate is the final rate fixed at settlement. They are different quantities; the 4b figure was never a settled rate and must not be compared to history rows as if it were. No settlement was crossed in either 4b replay window, so the 4b funding total (zero) is unaffected.

## Sign convention

A positive rate means longs pay shorts at settlement. Funding for a signed position held across a settlement is `position x price x contract_value x rate` (positive = paid). See `src/myquant/execution/funding.py` and `docs/portfolio.md`.

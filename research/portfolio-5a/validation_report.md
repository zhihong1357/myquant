# Stage 5a portfolio validation report

- Validated at: 2026-11-18T19:14:48.844930+00:00
- Panel: 49 confirmed OKX 1D bars per instrument (BTC/ETH/SOL-USDT-SWAP), first bar opens 2026-09-30T16:00:00+00:00, last bar closes 2026-11-18T16:00:00+00:00 (2026-10-01 to 2026-11-18 in UTC+8).
- Contract values (from the live `/public/instruments` spec, recorded in the panel manifest): BTC-USDT-SWAP 0.01, ETH-USDT-SWAP 0.1, SOL-USDT-SWAP 1.0.
- Funding: historical settled rates from `research/funding-history` (280 rows per instrument, complete grid, covering the whole window); reference price is the last completed daily bar close at or before each settlement (PIT-clean; 0/8/16 h stale by settlement hour — see the script header).
- Fill convention: bar-close price +/- 1 bp adverse slippage, taker fee 0.05% (OKX Regular) on executed notional; quantities rounded to 0.01 contracts. This is a stated close-fill convention, not tick-level simulation.
- Initial cash: 100,000 USDT per fixture. These fixtures are framework validation, not strategy backtests: no performance claim, no alpha, no Sharpe is made or implied.

## Reconciliation

Three-way reconciliation per fixture (see `docs/portfolio.md`): equity identity + an independent PnL cross-check from raw fill cash flows and position values at mark. Residuals are exact floats; the pass tolerance is 1e-9 USDT (floating-point only).

| Fixture | Residual (equity) | Residual (PnL) | Passed |
| --- | ---: | ---: | ---: |
| A (buy-and-hold) | 0.000000e+00 USDT | -5.456968e-12 USDT | **yes** |
| B (weekly rebalance) | 2.910383e-11 USDT | 3.637979e-12 USDT | **yes** |
| 2h tape end-to-end | 4.365575e-11 USDT | 1.048051e-13 USDT | **yes** |

## Fixture results (framework correctness only)

| Fixture | Final equity | Realized | Unrealized | Maker fees | Taker fees | Funding paid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A (buy-and-hold) | 84160.92 | 0.00 | -15457.55 | 0.00 | 27.99 | 353.5383 |
| B (weekly rebalance) | 77274.97 | -11.16 | -22360.46 | 0.00 | 38.18 | 315.2229 |

Funding settlements applied per fixture/instrument (skipped: none — the series covers the whole window):

| Fixture | Instrument | Settlements | Funding paid (USDT) |
| --- | --- | ---: | ---: |
| A (buy-and-hold) | BTC-USDT-SWAP | 144 | 300.8174 |
| A (buy-and-hold) | ETH-USDT-SWAP | 144 | 28.2274 |
| A (buy-and-hold) | SOL-USDT-SWAP | 144 | 24.4936 |
| B (weekly rebalance) | BTC-USDT-SWAP | 144 | 149.0289 |
| B (weekly rebalance) | ETH-USDT-SWAP | 144 | 75.3727 |
| B (weekly rebalance) | SOL-USDT-SWAP | 144 | 90.8213 |

## Hand-checks

Each check recomputes one number from the raw inputs, outside the portfolio's own code path:

### A (buy-and-hold)

- First BTC fee: close 84132.70 -> fill price 84141.1133 (recorded 84141.1133); hand-computed fee 21.035278 vs recorded 21.035278; difference 0.000000e+00 USDT.
- First BTC funding settlement (2026-10-02T00:00:00+00:00): position 50.0 contracts, rate 0.00000322, reference price 84132.70; hand-computed amount 0.135375 vs recorded 0.135375; difference 0.000000e+00 USDT.
- Independent final equity: 84160.92 vs portfolio 84160.92; difference 0.000000e+00 USDT.

### B (weekly rebalance)

- First BTC fee: close 84132.70 -> fill price 84141.1133 (recorded 84141.1133); hand-computed fee 10.000171 vs recorded 10.000171; difference 0.000000e+00 USDT.
- First BTC funding settlement (2026-10-02T00:00:00+00:00): position 23.77 contracts, rate 0.00000322, reference price 84132.70; hand-computed amount 0.064357 vs recorded 0.064357; difference 0.000000e+00 USDT.
- Independent final equity: 77274.97 vs portfolio 77274.97; difference 4.365575e-11 USDT.

## Exposure and risk (descriptive only)

Risk metrics describe the window's realized co-movement; they do not predict anything. Covariance is estimated on the 48 daily log returns (diff-then-join on the shared daily grid); VaR/ES are historical-simulation at 95% on each fixture's daily equity log returns.

| Fixture | Gross notional | Leverage | Max single share | Daily vol (sample) | Daily vol (Ledoit-Wolf) | LW delta | VaR 95% (daily) | ES 95% (daily) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A (buy-and-hold) | 40524.21 | 0.482 | 0.779 | 0.0209 | 0.0207 | 0.0225 | 0.0235 | 0.0291 |
| B (weekly rebalance) | 53193.05 | 0.688 | 0.338 | 0.0244 | 0.0240 | 0.0225 | 0.0385 | 0.0412 |

## Simulator end-to-end check (4a two-hour tape)

- Window: 2026-11-18T05:00:00+00:00 to 2026-11-18T07:00:00+00:00 (BTC-USDT-SWAP).
- Orders: 16 market orders (buy/sell 1.0 contract every 15 minutes); fills: 16 (16 book-unknown — the 2h tape has no in-window snapshots, so market fills use the first-print fallback, as in 4b).
- Final mark: last print 64579.1 USDT; final equity 99993.80 USDT; fees 5.1690 USDT (all taker); funding settlements crossed: 0 (none — funding is zero by construction here; the funding path is exercised by the daily fixtures above).
- Reconciliation: residual (equity) 4.365575e-11 USDT, residual (PnL) 1.048051e-13 USDT, passed: **yes**.

## Limitations

- Daily fixtures use a close-fill convention, not tick-level simulation: no intraday price path, no queue, no book. Slippage is a fixed 1 bp assumption, not a measurement.
- Funding reference prices are daily closes (last completed bar at or before each settlement), stale by up to 16 h. Settlement-time prices would need the trade tape, which exists only for 2026-11-18.
- The 2h tape check is one instrument on one morning; its fills are book-unknown by design (no in-window snapshots).
- The fixtures hold fixed contracts / fixed notionals; they are not strategies, and their equity paths say nothing about any trading idea.
- VaR/ES and covariance describe 48 daily observations; with so few points the estimates are noisy, and the Ledoit-Wolf shrinkage intensity reflects that.

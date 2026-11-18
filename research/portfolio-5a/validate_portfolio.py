"""Stage 5a portfolio validation: fixtures + simulator end-to-end check.

Run from the repo root (after ``fetch_panel.py`` and the
funding-history fetch):

    .venv/bin/python research/portfolio-5a/validate_portfolio.py

Offline: re-reads the cached panel and funding series through their
RawStores (checksums verified on read), re-parses them, runs two
mechanical fixture portfolios over the 49-bar daily window
(2026-09-30T16:00Z to 2026-11-18T16:00Z), and runs a
simulator-to-portfolio end-to-end check on the 4a two-hour tape.
Writes ``research/portfolio-5a/validation_report.md``.

The fixtures are framework validation, not strategy backtests: no
performance claim, no alpha, no Sharpe is made or implied anywhere
in the output. What is validated is framework correctness —
reconciliation residuals zero, fee/funding splits matching
hand-computed values, and the simulator-to-portfolio path working.

Fill convention (daily fixtures): fills execute at the bar close
price plus 1 bp adverse slippage, taker fee at the verified OKX
Regular rate (0.05%) on the executed notional. This is a stated
close-fill convention, NOT tick-level simulation — no tick tape
exists for this window, and fabricating one from daily bars would
be dishonest. Quantities round to 0.01 contracts (the OKX lot size
for all three swaps); minimum-size and tick-rounding effects beyond
that are not modelled.

Funding reference price: the close of the last daily bar completed
at or before the settlement (PIT-clean — the price was knowable at
settlement). Staleness: 0 h for 16:00 UTC settlements, 8 h for
00:00, 16 h for 08:00. This is a documented daily-granularity
approximation, not a settlement-time price.
"""

from __future__ import annotations

import bisect
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "research" / "microstructure-4b"))

from load_dataset import load_dataset  # noqa: E402

from myquant.adapters.okx import OKXCandle, parse_candles_response  # noqa: E402
from myquant.adapters.okx_funding import parse_funding_history_response  # noqa: E402
from myquant.execution import (  # noqa: E402
    CostConfig,
    PaperOrder,
    SimulationConfig,
    simulate_orders,
)
from myquant.execution.costs import bps_cost, funding_settlements_between  # noqa: E402
from myquant.execution.fees import OKX_FUTURES_FEES, REGULAR_TIER  # noqa: E402
from myquant.execution.funding import (  # noqa: E402
    FundingRateSeries,
    compute_funding_from_series,
)
from myquant.execution.orders import Fill  # noqa: E402
from myquant.portfolio.portfolio import PaperPortfolio  # noqa: E402
from myquant.portfolio.risk import (  # noqa: E402
    historical_var_es,
    ledoit_wolf_covariance,
    portfolio_volatility,
    sample_covariance,
)
from myquant.raw import RawStore  # noqa: E402

PANEL_CACHE = REPO_ROOT / "data" / "cache" / "portfolio-5a"
FUNDING_ROOT = REPO_ROOT / "research" / "funding-history"
FUNDING_CACHE = REPO_ROOT / "data" / "cache" / "funding-history"
DATASET_4A = (
    REPO_ROOT / "research" / "microstructure-4a" / "manifest.json",
    REPO_ROOT / "data" / "cache" / "microstructure-4a",
)

INSTRUMENTS = {
    "BTC-USDT-SWAP": "crypto:btc-usdt-perp",
    "ETH-USDT-SWAP": "crypto:eth-usdt-perp",
    "SOL-USDT-SWAP": "crypto:sol-usdt-perp",
}
WINDOW_START = datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
INITIAL_CASH = 100_000.0
SLIPPAGE_BPS = 1.0
FIXTURE_A_QTY = {"BTC-USDT-SWAP": 50.0, "ETH-USDT-SWAP": 30.0, "SOL-USDT-SWAP": 50.0}
FIXTURE_B_TARGET_NOTIONAL = 20_000.0
FIXTURE_B_REBALANCE_EVERY_BARS = 7
TAPE_ORDER_SIZE = 1.0


def _load_panel() -> tuple[dict[str, tuple[OKXCandle, ...]], dict[str, float], dict]:
    """Re-read the panel from the manifest + RawStore (checksums verified)."""
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    raw_store = RawStore(PANEL_CACHE / "raw")
    panels: dict[str, tuple[OKXCandle, ...]] = {}
    contract_values: dict[str, float] = {}
    for inst_id, entry in sorted(manifest["instruments"].items()):
        # Raw pages can overshoot the window (the fetch pages
        # backwards until the start is covered); apply the same
        # [start, end) + confirmed filter fetch_history used.
        collected: dict[datetime, OKXCandle] = {}
        for page in entry["candle_pages"]:
            payload = raw_store.read_payload(page["record_id"])
            for candle in parse_candles_response(payload, inst_id=inst_id, bar="1D"):
                if candle.confirmed and WINDOW_START <= candle.open_time < WINDOW_END:
                    collected[candle.open_time] = candle
        candles = [collected[key] for key in sorted(collected)]
        if len(candles) != entry["candle_count"]:
            raise RuntimeError(
                f"{inst_id}: manifest says {entry['candle_count']} bars, "
                f"re-parsed {len(candles)}"
            )
        if candles[0].open_time.isoformat() != entry["first_open"]:
            raise RuntimeError(f"{inst_id}: first bar does not match manifest")
        panels[inst_id] = tuple(candles)
        contract_values[inst_id] = float(entry["contract_value"])
    return panels, contract_values, manifest


def _load_funding() -> dict[str, FundingRateSeries]:
    """Rebuild the funding series from the funding-history cache."""
    manifest = json.loads(
        (FUNDING_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    raw_store = RawStore(FUNDING_CACHE / "raw")
    series: dict[str, FundingRateSeries] = {}
    for inst_id, entry in sorted(manifest["instruments"].items()):
        rows = []
        for page in entry["pages"]:
            payload = raw_store.read_payload(page["record_id"])
            rows.extend(
                parse_funding_history_response(payload, inst_id=inst_id)
            )
        series[inst_id] = FundingRateSeries.from_okx_rows(inst_id, rows)
    return series


def _close_fill(
    order_id: str,
    side: str,
    quantity: float,
    close_price: float,
    at: datetime,
    contract_value: float,
) -> Fill:
    """A close-convention fill: close price +/- 1 bp, taker fee."""
    fill_price = (
        close_price * (1.0 + SLIPPAGE_BPS / 10_000.0)
        if side == "buy"
        else close_price * (1.0 - SLIPPAGE_BPS / 10_000.0)
    )
    notional = fill_price * quantity * contract_value
    fee = OKX_FUTURES_FEES.fee_for(REGULAR_TIER, maker=False, notional=notional)
    return Fill(
        order_id=order_id,
        side=side,  # type: ignore[arg-type]
        fill_time=at,
        price=fill_price,
        quantity=quantity,
        is_maker=False,
        fee=fee,
        crossing_cost=None,
        slippage_cost=bps_cost(close_price, quantity, SLIPPAGE_BPS, contract_value),
        impact_cost=0.0,
        book_unknown=True,  # no book at daily granularity
    )


def _price_at_factory(
    candles: tuple[OKXCandle, ...],
):
    """Last completed bar close at or before a time (PIT-clean)."""
    close_times = [c.close_time for c in candles]
    closes = [c.close for c in candles]

    def price_at(when: datetime) -> float | None:
        index = bisect.bisect_right(close_times, when) - 1
        return closes[index] if index >= 0 else None

    return price_at


def _run_fixture(
    label: str,
    fills_by_instrument: dict[str, list[Fill]],
    panels: dict[str, tuple[OKXCandle, ...]],
    contract_values: dict[str, float],
    funding: dict[str, FundingRateSeries],
) -> dict:
    """Run one fixture portfolio: merge events, apply, reconcile."""
    portfolio = PaperPortfolio(
        INITIAL_CASH,
        {
            INSTRUMENTS[inst_id]: contract_values[inst_id]
            for inst_id in INSTRUMENTS
        },
        start_time=WINDOW_START,
    )
    events: list[tuple[datetime, int, str, object]] = []
    funding_results: dict[str, object] = {}
    for inst_id, fills in fills_by_instrument.items():
        result = compute_funding_from_series(
            fills,
            funding[inst_id],
            start=WINDOW_START,
            end=WINDOW_END,
            price_at=_price_at_factory(panels[inst_id]),
            contract_value=contract_values[inst_id],
        )
        funding_results[inst_id] = result
        for settlement in result.settlements:
            events.append((settlement.settlement_time, 0, "funding", settlement))
        for fill in fills:
            events.append((fill.fill_time, 1, "fill", (inst_id, fill)))
    closes_by_time: dict[datetime, dict[str, float]] = {}
    for inst_id, candles in panels.items():
        for candle in candles:
            closes_by_time.setdefault(candle.close_time, {})[
                INSTRUMENTS[inst_id]
            ] = candle.close
    for close_time, prices in closes_by_time.items():
        events.append((close_time, 2, "mark", prices))
    events.sort(key=lambda event: (event[0], event[1]))
    equity_at_marks: list[tuple[datetime, float]] = []
    for event_time, _, kind, payload in events:
        if kind == "funding":
            portfolio.apply_funding(payload)  # type: ignore[arg-type]
        elif kind == "fill":
            inst_id, fill = payload  # type: ignore[misc]
            portfolio.apply_fill(INSTRUMENTS[inst_id], fill)
        else:
            portfolio.mark(payload, event_time)  # type: ignore[arg-type]
            equity_at_marks.append((event_time, portfolio.equity))
    reconciliation = portfolio.reconcile()
    if not reconciliation.passed:
        raise RuntimeError(
            f"{label}: reconciliation FAILED: "
            f"residual_equity={reconciliation.residual_equity!r}, "
            f"residual_pnl={reconciliation.residual_pnl!r}"
        )
    return {
        "label": label,
        "portfolio": portfolio,
        "reconciliation": reconciliation,
        "funding_results": funding_results,
        "equity_at_marks": equity_at_marks,
        "fills_by_instrument": fills_by_instrument,
    }


def _hand_check_fee(fixture: dict, panels, contract_values) -> dict:
    """Recompute the first BTC fee by hand from the raw close price."""
    fills = fixture["fills_by_instrument"]["BTC-USDT-SWAP"]
    first = fills[0]
    close = panels["BTC-USDT-SWAP"][0].close
    fill_price = close * (1.0 + SLIPPAGE_BPS / 10_000.0)
    expected_fee = fill_price * first.quantity * contract_values["BTC-USDT-SWAP"] * 0.0005
    return {
        "close": close,
        "fill_price_hand": fill_price,
        "fill_price_recorded": first.price,
        "expected_fee": expected_fee,
        "recorded_fee": first.fee,
        "difference": first.fee - expected_fee,
    }


def _hand_check_funding(fixture: dict, funding, panels, contract_values) -> dict:
    """Recompute the first BTC funding settlement by hand."""
    result = fixture["funding_results"]["BTC-USDT-SWAP"]
    first = result.settlements[0]
    series = funding["BTC-USDT-SWAP"]
    rate = series.rate_at(first.settlement_time)
    price = _price_at_factory(panels["BTC-USDT-SWAP"])(first.settlement_time)
    # Position recomputed from the fills, not taken from the settlement.
    position = sum(
        fill.quantity if fill.side == "buy" else -fill.quantity
        for fill in fixture["fills_by_instrument"]["BTC-USDT-SWAP"]
        if fill.fill_time < first.settlement_time
    )
    assert rate is not None and price is not None
    expected = position * price * contract_values["BTC-USDT-SWAP"] * rate
    return {
        "settlement_time": first.settlement_time.isoformat(),
        "position": position,
        "rate": rate,
        "price": price,
        "expected_amount": expected,
        "recorded_amount": first.amount,
        "difference": first.amount - expected,
    }


def _independent_equity(fixture: dict, panels, contract_values) -> dict:
    """Final equity recomputed from the script's own data (not the portfolio)."""
    portfolio = fixture["portfolio"]
    flows = 0.0
    fees = 0.0
    for inst_id, fills in fixture["fills_by_instrument"].items():
        cv = contract_values[inst_id]
        for fill in fills:
            sign = -1.0 if fill.side == "buy" else 1.0
            flows += sign * fill.price * fill.quantity * cv
            fees += fill.fee
    position_values = 0.0
    for inst_id, fills in fixture["fills_by_instrument"].items():
        cv = contract_values[inst_id]
        qty = sum(
            fill.quantity if fill.side == "buy" else -fill.quantity
            for fill in fills
        )
        last_close = panels[inst_id][-1].close
        position_values += qty * last_close * cv
    funding_total = sum(
        result.total_amount
        for result in fixture["funding_results"].values()
    )
    expected = INITIAL_CASH + flows + position_values - fees - funding_total
    return {
        "expected_equity": expected,
        "portfolio_equity": portfolio.equity,
        "difference": portfolio.equity - expected,
    }


def _risk_metrics(fixture: dict, panels) -> dict:
    """Descriptive-only risk metrics on the daily panel (not predictive)."""
    closes = {
        inst_id: np.array([c.close for c in candles], dtype=float)
        for inst_id, candles in panels.items()
    }
    log_returns = np.column_stack(
        [np.diff(np.log(closes[inst_id])) for inst_id in INSTRUMENTS]
    )
    sample = sample_covariance(log_returns)
    lw = ledoit_wolf_covariance(log_returns)
    portfolio = fixture["portfolio"]
    exposure = portfolio.exposure()
    weights = np.array(
        [
            (
                portfolio.positions[INSTRUMENTS[inst_id]].notional
                / exposure.gross_notional
                if exposure.gross_notional > 0
                else 0.0
            )
            for inst_id in INSTRUMENTS
        ]
    )
    equity = np.array([value for _, value in fixture["equity_at_marks"]])
    equity_returns = np.diff(np.log(equity))
    var_es = historical_var_es(equity_returns, confidence=0.95)
    return {
        "observations": int(log_returns.shape[0]),
        "sample_covariance": sample,
        "lw_shrinkage": lw.shrinkage,
        "portfolio_vol_daily_sample": portfolio_volatility(weights, sample),
        "portfolio_vol_daily_lw": portfolio_volatility(weights, lw.covariance),
        "var_95": var_es.var,
        "es_95": var_es.expected_shortfall,
    }


def _run_tape_check() -> dict:
    """Simulator -> portfolio end-to-end check on the 4a two-hour tape."""
    dataset = load_dataset(*DATASET_4A)
    window_start = datetime.fromisoformat(dataset.manifest["window"]["start"])
    window_end = datetime.fromisoformat(dataset.manifest["window"]["end"])
    decisions = [window_start + timedelta(minutes=15 * k + 5) for k in range(8)]
    orders: list[PaperOrder] = []
    for index, decision in enumerate(decisions):
        for side in ("buy", "sell"):
            orders.append(
                PaperOrder(
                    order_id=f"tape-mkt-{index:02d}-{side}",
                    instrument_id="crypto:btc-usdt-perp",
                    venue="okx",
                    side=side,  # type: ignore[arg-type]
                    order_type="market",
                    quantity=TAPE_ORDER_SIZE,
                    decision_time=decision,
                    available_at=decision,
                )
            )
    result = simulate_orders(
        orders, dataset.trades, dataset.snapshots, config=SimulationConfig()
    )
    portfolio = PaperPortfolio(
        INITIAL_CASH,
        {"crypto:btc-usdt-perp": CostConfig().contract_value},
        start_time=window_start,
    )
    all_fills = [
        (fill.fill_time, fill.order_id, fill)
        for order_result in result.order_results
        for fill in order_result.fills
    ]
    all_fills.sort(key=lambda item: (item[0], item[1]))
    for _, _, fill in all_fills:
        portfolio.apply_fill("crypto:btc-usdt-perp", fill)
    last_price = dataset.trades[-1].price
    portfolio.mark({"crypto:btc-usdt-perp": last_price}, window_end)
    reconciliation = portfolio.reconcile()
    if not reconciliation.passed:
        raise RuntimeError(
            "tape check: reconciliation FAILED: "
            f"residual_equity={reconciliation.residual_equity!r}, "
            f"residual_pnl={reconciliation.residual_pnl!r}"
        )
    settlements = funding_settlements_between(window_start, window_end)
    return {
        "orders": len(orders),
        "fills": len(all_fills),
        "fills_book_unknown": result.fills_book_unknown,
        "portfolio": portfolio,
        "reconciliation": reconciliation,
        "last_price": last_price,
        "settlements_crossed": len(settlements),
        "window": (window_start, window_end),
    }


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def main() -> None:
    ran_at = datetime.now(UTC)
    panels, contract_values, panel_manifest = _load_panel()
    funding = _load_funding()
    for inst_id, series in funding.items():
        coverage = series.coverage()
        if coverage.missing_settlements:
            raise RuntimeError(
                f"{inst_id}: funding series has missing settlements; "
                "refusing to validate against an incomplete series"
            )
        if not (
            coverage.first_settlement <= WINDOW_START
            and coverage.last_settlement >= WINDOW_END
        ):
            raise RuntimeError(f"{inst_id}: funding series does not cover the window")

    # --- fixture A: buy-and-hold fixed contracts ----------------------
    first_close_time = panels["BTC-USDT-SWAP"][0].close_time
    fills_a: dict[str, list[Fill]] = {}
    for inst_id, qty in FIXTURE_A_QTY.items():
        close = panels[inst_id][0].close
        fills_a[inst_id] = [
            _close_fill(
                "A-open",
                "buy",
                qty,
                close,
                first_close_time,
                contract_values[inst_id],
            )
        ]
    fixture_a = _run_fixture("A (buy-and-hold)", fills_a, panels, contract_values, funding)

    # --- fixture B: weekly rebalance to fixed notional ----------------
    fills_b: dict[str, list[Fill]] = {inst_id: [] for inst_id in INSTRUMENTS}
    current_qty: dict[str, float] = {inst_id: 0.0 for inst_id in INSTRUMENTS}
    for bar_index, candle in enumerate(panels["BTC-USDT-SWAP"]):
        if bar_index % FIXTURE_B_REBALANCE_EVERY_BARS != 0:
            continue
        for inst_id in INSTRUMENTS:
            close = panels[inst_id][bar_index].close
            cv = contract_values[inst_id]
            target_qty = round(FIXTURE_B_TARGET_NOTIONAL / (close * cv), 2)
            delta = round(target_qty - current_qty[inst_id], 2)
            if delta == 0:
                continue
            fills_b[inst_id].append(
                _close_fill(
                    f"B-reb-{bar_index:02d}",
                    "buy" if delta > 0 else "sell",
                    abs(delta),
                    close,
                    candle.close_time,
                    cv,
                )
            )
            current_qty[inst_id] += delta
    fixture_b = _run_fixture(
        "B (weekly rebalance)", fills_b, panels, contract_values, funding
    )

    tape = _run_tape_check()

    # --- report -------------------------------------------------------
    lines: list[str] = [
        "# Stage 5a portfolio validation report",
        "",
        f"- Validated at: {ran_at.isoformat()}",
        "- Panel: 49 confirmed OKX 1D bars per instrument "
        "(BTC/ETH/SOL-USDT-SWAP), first bar opens "
        f"{WINDOW_START.isoformat()}, last bar closes "
        f"{WINDOW_END.isoformat()} (2026-10-01 to 2026-11-18 in UTC+8).",
        "- Contract values (from the live `/public/instruments` spec, "
        "recorded in the panel manifest): "
        + ", ".join(
            f"{inst_id} {contract_values[inst_id]}"
            for inst_id in INSTRUMENTS
        )
        + ".",
        "- Funding: historical settled rates from "
        "`research/funding-history` (280 rows per instrument, complete "
        "grid, covering the whole window); reference price is the last "
        "completed daily bar close at or before each settlement "
        "(PIT-clean; 0/8/16 h stale by settlement hour — see the "
        "script header).",
        "- Fill convention: bar-close price +/- 1 bp adverse slippage, "
        "taker fee 0.05% (OKX Regular) on executed notional; quantities "
        "rounded to 0.01 contracts. This is a stated close-fill "
        "convention, not tick-level simulation.",
        "- Initial cash: 100,000 USDT per fixture. These fixtures are "
        "framework validation, not strategy backtests: no performance "
        "claim, no alpha, no Sharpe is made or implied.",
        "",
        "## Reconciliation",
        "",
        "Three-way reconciliation per fixture (see `docs/portfolio.md`): "
        "equity identity + an independent PnL cross-check from raw fill "
        "cash flows and position values at mark. Residuals are exact "
        "floats; the pass tolerance is 1e-9 USDT (floating-point only).",
        "",
        "| Fixture | Residual (equity) | Residual (PnL) | Passed |",
        "| --- | ---: | ---: | ---: |",
    ]
    for fixture in (fixture_a, fixture_b):
        rec = fixture["reconciliation"]
        lines.append(
            f"| {fixture['label']} | {rec.residual_equity:.6e} USDT | "
            f"{rec.residual_pnl:.6e} USDT | **{'yes' if rec.passed else 'NO'}** |"
        )
    tape_rec = tape["reconciliation"]
    lines.append(
        f"| 2h tape end-to-end | {tape_rec.residual_equity:.6e} USDT | "
        f"{tape_rec.residual_pnl:.6e} USDT | "
        f"**{'yes' if tape_rec.passed else 'NO'}** |"
    )
    lines += [
        "",
        "## Fixture results (framework correctness only)",
        "",
        "| Fixture | Final equity | Realized | Unrealized | "
        "Maker fees | Taker fees | Funding paid |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for fixture in (fixture_a, fixture_b):
        p = fixture["portfolio"]
        lines.append(
            f"| {fixture['label']} | {_fmt(p.equity)} | {_fmt(p.realized_pnl)} | "
            f"{_fmt(p.unrealized_pnl)} | {_fmt(p.maker_fees)} | "
            f"{_fmt(p.taker_fees)} | {_fmt(p.funding_paid, 4)} |"
        )
    lines += [
        "",
        "Funding settlements applied per fixture/instrument "
        "(skipped: none — the series covers the whole window):",
        "",
        "| Fixture | Instrument | Settlements | Funding paid (USDT) |",
        "| --- | --- | ---: | ---: |",
    ]
    for fixture in (fixture_a, fixture_b):
        for inst_id in INSTRUMENTS:
            result = fixture["funding_results"][inst_id]
            lines.append(
                f"| {fixture['label']} | {inst_id} | "
                f"{len(result.settlements)} | {_fmt(result.total_amount, 4)} |"
            )
    lines += [
        "",
        "## Hand-checks",
        "",
        "Each check recomputes one number from the raw inputs, outside "
        "the portfolio's own code path:",
        "",
    ]
    for fixture in (fixture_a, fixture_b):
        fee_check = _hand_check_fee(fixture, panels, contract_values)
        funding_check = _hand_check_funding(fixture, funding, panels, contract_values)
        equity_check = _independent_equity(fixture, panels, contract_values)
        lines += [
            f"### {fixture['label']}",
            "",
            f"- First BTC fee: close {_fmt(fee_check['close'], 2)} -> "
            f"fill price {_fmt(fee_check['fill_price_hand'], 4)} "
            f"(recorded {_fmt(fee_check['fill_price_recorded'], 4)}); "
            f"hand-computed fee {_fmt(fee_check['expected_fee'], 6)} vs "
            f"recorded {_fmt(fee_check['recorded_fee'], 6)}; "
            f"difference {fee_check['difference']:.6e} USDT.",
            f"- First BTC funding settlement "
            f"({funding_check['settlement_time']}): position "
            f"{funding_check['position']} contracts, rate "
            f"{funding_check['rate']:.8f}, reference price "
            f"{_fmt(funding_check['price'], 2)}; hand-computed amount "
            f"{_fmt(funding_check['expected_amount'], 6)} vs recorded "
            f"{_fmt(funding_check['recorded_amount'], 6)}; "
            f"difference {funding_check['difference']:.6e} USDT.",
            f"- Independent final equity: {_fmt(equity_check['expected_equity'])} "
            f"vs portfolio {_fmt(equity_check['portfolio_equity'])}; "
            f"difference {equity_check['difference']:.6e} USDT.",
            "",
        ]
    lines += [
        "## Exposure and risk (descriptive only)",
        "",
        "Risk metrics describe the window's realized co-movement; they "
        "do not predict anything. Covariance is estimated on the 48 "
        "daily log returns (diff-then-join on the shared daily grid); "
        "VaR/ES are historical-simulation at 95% on each fixture's "
        "daily equity log returns.",
        "",
        "| Fixture | Gross notional | Leverage | Max single share | "
        "Daily vol (sample) | Daily vol (Ledoit-Wolf) | LW delta | "
        "VaR 95% (daily) | ES 95% (daily) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for fixture in (fixture_a, fixture_b):
        metrics = _risk_metrics(fixture, panels)
        exposure = fixture["portfolio"].exposure()
        leverage = (
            f"{exposure.leverage:.3f}"
            if exposure.leverage is not None
            else "n/a"
        )
        lines.append(
            f"| {fixture['label']} | {_fmt(exposure.gross_notional)} | "
            f"{leverage} | {exposure.max_single_share:.3f} | "
            f"{metrics['portfolio_vol_daily_sample']:.4f} | "
            f"{metrics['portfolio_vol_daily_lw']:.4f} | "
            f"{metrics['lw_shrinkage']:.4f} | "
            f"{metrics['var_95']:.4f} | {metrics['es_95']:.4f} |"
        )
    lines += [
        "",
        "## Simulator end-to-end check (4a two-hour tape)",
        "",
        f"- Window: {tape['window'][0].isoformat()} to "
        f"{tape['window'][1].isoformat()} (BTC-USDT-SWAP).",
        f"- Orders: {tape['orders']} market orders (buy/sell 1.0 contract "
        f"every 15 minutes); fills: {tape['fills']} "
        f"({tape['fills_book_unknown']} book-unknown — the 2h tape has "
        f"no in-window snapshots, so market fills use the first-print "
        f"fallback, as in 4b).",
        f"- Final mark: last print {_fmt(tape['last_price'], 1)} USDT; "
        f"final equity {_fmt(tape['portfolio'].equity)} USDT; fees "
        f"{_fmt(tape['portfolio'].total_fees, 4)} USDT "
        f"(all taker); funding settlements crossed: "
        f"{tape['settlements_crossed']} (none — funding is zero by "
        f"construction here; the funding path is exercised by the "
        f"daily fixtures above).",
        f"- Reconciliation: residual (equity) "
        f"{tape_rec.residual_equity:.6e} USDT, residual (PnL) "
        f"{tape_rec.residual_pnl:.6e} USDT, "
        f"passed: **{'yes' if tape_rec.passed else 'NO'}**.",
        "",
        "## Limitations",
        "",
        "- Daily fixtures use a close-fill convention, not tick-level "
        "simulation: no intraday price path, no queue, no book. "
        "Slippage is a fixed 1 bp assumption, not a measurement.",
        "- Funding reference prices are daily closes (last completed "
        "bar at or before each settlement), stale by up to 16 h. "
        "Settlement-time prices would need the trade tape, which "
        "exists only for 2026-11-18.",
        "- The 2h tape check is one instrument on one morning; its "
        "fills are book-unknown by design (no in-window snapshots).",
        "- The fixtures hold fixed contracts / fixed notionals; they "
        "are not strategies, and their equity paths say nothing about "
        "any trading idea.",
        "- VaR/ES and covariance describe 48 daily observations; with "
        "so few points the estimates are noisy, and the Ledoit-Wolf "
        "shrinkage intensity reflects that.",
        "",
    ]
    report_path = ROOT / "validation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"validation report written: {report_path}")
    for fixture in (fixture_a, fixture_b):
        p = fixture["portfolio"]
        rec = fixture["reconciliation"]
        print(
            f"{fixture['label']}: equity={_fmt(p.equity)}, "
            f"fees={_fmt(p.total_fees)}, funding={_fmt(p.funding_paid, 4)}, "
            f"residuals=({rec.residual_equity:.2e}, {rec.residual_pnl:.2e}), "
            f"passed={rec.passed}"
        )
    print(
        f"tape: equity={_fmt(tape['portfolio'].equity)}, "
        f"fills={tape['fills']}, "
        f"residuals=({tape_rec.residual_equity:.2e}, "
        f"{tape_rec.residual_pnl:.2e}), passed={tape_rec.passed}"
    )


if __name__ == "__main__":
    main()

"""Stage 4b validation replay: run a fixed paper order set on both datasets.

Run from the repo root, after ``fetch_snapshots.py`` has produced the
dense dataset:

    .venv/bin/python research/microstructure-4b/replay.py

Replays a fixed, documented order set against:

1. the 4a two-hour tape (2026-11-18 05:00-07:00 UTC, 153,971 trades;
   its two snapshots sit outside the window, so every fill there is
   book-unknown by design — the replay measures the limit-fill and
   latency paths, not crossing), and
2. the 4b dense window (~10 minutes of live snapshots at ~1 s
   cadence plus the same window's trades), where market fills have
   real books and crossing/slippage/impact are measured.

The order set (identical in structure on both datasets):

- Market orders: one buy and one sell of 1.0 contract at each
  decision time (2h tape: every 15 minutes from 05:05; dense window:
  every 60 s from window start + 60 s).
- Limit grid: at each decision time, buy limits at the reference
  price minus 0.05% / 0.10% / 0.20% and sell limits at the reference
  plus 0.05% / 0.10% / 0.20%, 1.0 contract each, cancelled after
  15 minutes (2h tape) or 60 s (dense window). The reference price
  is the last print before the decision time; limit prices are
  rounded to the 0.1 USDT tick.
- At-market limits: at each decision time, one buy limit and one
  sell limit at the reference price itself. These exercise the
  fast-fill and crossed-at-arrival paths, and — under latency —
  the missed-fill path, since prints at the reference price are
  common within a second of a decision.

This is descriptive validation of the simulator's mechanics, not a
strategy backtest and not evidence about any trading idea: the order
set is synthetic, the fills are modelled, and no conclusion about
alpha is drawn or implied.

Writes ``validation_report.md`` in this directory.
"""

from __future__ import annotations

import bisect
from datetime import UTC, datetime, timedelta
from pathlib import Path

from load_dataset import (
    INSTRUMENT_ID,
    VENUE,
    LoadedDataset,
    load_dataset,
)

from myquant.execution import (
    CostConfig,
    PaperOrder,
    SimulationConfig,
    SimulationResult,
    compute_funding,
    funding_settlements_between,
    simulate_orders,
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
DATASET_4A = (
    REPO_ROOT / "research" / "microstructure-4a" / "manifest.json",
    REPO_ROOT / "data" / "cache" / "microstructure-4a",
)
DATASET_4B = (
    ROOT / "manifest.json",
    REPO_ROOT / "data" / "cache" / "microstructure-4b",
)

TICK_SIZE = 0.1
ORDER_SIZE = 1.0
LIMIT_OFFSETS = (-0.002, -0.001, -0.0005, 0.0005, 0.001, 0.002)

#: Funding rate read live from OKX /api/v5/public/funding-rate on
#: 2026-11-18 (~08:10 UTC). An input, not a series: no settlement is
#: crossed in either replay window, so funding is zero regardless of
#: this value; it is recorded here so the input is explicit.
FUNDING_RATE_OBSERVED = 0.0000214958653344


def _round_tick(price: float) -> float:
    return round(price / TICK_SIZE) * TICK_SIZE


def build_order_set(
    dataset: LoadedDataset,
    decision_times: list[datetime],
    *,
    cancel_after: timedelta,
    prefix: str,
) -> list[PaperOrder]:
    """Build the fixed order set for one dataset (see module docstring)."""
    trade_times = [trade.event_time for trade in dataset.trades]
    orders: list[PaperOrder] = []
    counter = 0
    for decision in decision_times:
        index = bisect.bisect_left(trade_times, decision) - 1
        if index < 0:
            continue
        reference = dataset.trades[index].price
        for side in ("buy", "sell"):
            counter += 1
            orders.append(
                PaperOrder(
                    order_id=f"{prefix}-mkt-{counter:03d}-{side}",
                    instrument_id=INSTRUMENT_ID,
                    venue=VENUE,
                    side=side,  # type: ignore[arg-type]
                    order_type="market",
                    quantity=ORDER_SIZE,
                    decision_time=decision,
                    available_at=decision,
                )
            )
        for offset in LIMIT_OFFSETS:
            counter += 1
            side = "buy" if offset < 0 else "sell"
            limit_price = _round_tick(reference * (1.0 + offset))
            orders.append(
                PaperOrder(
                    order_id=f"{prefix}-lim-{counter:03d}-{side}-{abs(offset):.4f}",
                    instrument_id=INSTRUMENT_ID,
                    venue=VENUE,
                    side=side,  # type: ignore[arg-type]
                    order_type="limit",
                    quantity=ORDER_SIZE,
                    limit_price=limit_price,
                    decision_time=decision,
                    available_at=decision,
                    cancel_time=decision + cancel_after,
                )
            )
        for side in ("buy", "sell"):
            counter += 1
            orders.append(
                PaperOrder(
                    order_id=f"{prefix}-atm-{counter:03d}-{side}",
                    instrument_id=INSTRUMENT_ID,
                    venue=VENUE,
                    side=side,  # type: ignore[arg-type]
                    order_type="limit",
                    quantity=ORDER_SIZE,
                    limit_price=_round_tick(reference),
                    decision_time=decision,
                    available_at=decision,
                    cancel_time=decision + cancel_after,
                )
            )
    return orders


def _summarize(
    label: str,
    result: SimulationResult,
    orders: list[PaperOrder],
    dataset: LoadedDataset,
) -> dict:
    """Aggregate one replay into reportable numbers."""
    by_type: dict[str, dict] = {}
    for order_type in ("market", "limit"):
        typed = [
            r for r in result.order_results if r.order.order_type == order_type
        ]
        filled_qty = sum(r.filled_quantity for r in typed)
        total_qty = sum(r.order.quantity for r in typed)
        filled_notional = sum(
            fill.price * fill.quantity * CostConfig().contract_value
            for r in typed
            for fill in r.fills
        )
        by_type[order_type] = {
            "orders": len(typed),
            "filled": sum(1 for r in typed if r.status == "filled"),
            "partial": sum(1 for r in typed if r.status == "partial"),
            "unfilled": sum(1 for r in typed if r.status == "unfilled"),
            "cancelled": sum(1 for r in typed if r.status == "cancelled"),
            "fill_rate_qty": filled_qty / total_qty if total_qty else 0.0,
            "fee": sum(r.total_fee for r in typed),
            "crossing": (
                sum(r.total_crossing_cost for r in typed)
                if all(not r.crossing_unknown for r in typed)
                else None
            ),
            "crossing_unknown_orders": sum(
                1 for r in typed if r.crossing_unknown
            ),
            "slippage": sum(r.total_slippage_cost for r in typed),
            "impact": sum(r.total_impact_cost for r in typed),
            "missed_fills": sum(len(r.missed_fills) for r in typed),
            "missed_qty": sum(
                missed.quantity for r in typed for missed in r.missed_fills
            ),
            "filled_notional": filled_notional,
        }
    all_fills = [fill for r in result.order_results for fill in r.fills]
    trade_times = [trade.event_time for trade in dataset.trades]

    def price_at(when: datetime) -> float | None:
        index = bisect.bisect_right(trade_times, when) - 1
        return dataset.trades[index].price if index >= 0 else None

    window_start = datetime.fromisoformat(dataset.manifest["window"]["start"])
    window_end = datetime.fromisoformat(dataset.manifest["window"]["end"])
    settlements = funding_settlements_between(window_start, window_end)
    funding = compute_funding(
        tuple(all_fills),
        settlements=settlements,
        price_at=price_at,
        funding_rate=FUNDING_RATE_OBSERVED,
        contract_value=CostConfig().contract_value,
    )
    return {
        "label": label,
        "orders": len(orders),
        "by_type": by_type,
        "fills_book_unknown": result.fills_book_unknown,
        "fills_queue_unknown": result.fills_queue_unknown,
        "fills_total": len(all_fills),
        "settlements_crossed": len(settlements),
        "funding_total": sum(s.amount for s in funding),
    }


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def _render_section(summary: dict) -> list[str]:
    lines = [
        f"## {summary['label']}",
        "",
        f"- Orders replayed: {summary['orders']}",
        f"- Fills: {summary['fills_total']} "
        f"({summary['fills_book_unknown']} book-unknown, "
        f"{summary['fills_queue_unknown']} queue-unknown)",
        f"- Funding settlements crossed: {summary['settlements_crossed']}; "
        f"funding paid: {_fmt(summary['funding_total'], 6)} USDT "
        f"(rate input {FUNDING_RATE_OBSERVED:.8f} per interval, read live "
        f"2026-11-18; no settlement crossed in either window, so funding "
        f"is zero by construction)",
        "",
        "| Type | Orders | Filled | Partial | Unfilled | Cancelled | "
        "Fill rate (qty) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for order_type in ("market", "limit"):
        row = summary["by_type"][order_type]
        lines.append(
            f"| {order_type} | {row['orders']} | {row['filled']} | "
            f"{row['partial']} | {row['unfilled']} | {row['cancelled']} | "
            f"{100 * row['fill_rate_qty']:.1f}% |"
        )
    lines += [
        "",
        "| Type | Fees (USDT) | Crossing (USDT) | Slippage (USDT) | "
        "Impact (USDT) | Missed fills (count / qty) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for order_type in ("market", "limit"):
        row = summary["by_type"][order_type]
        crossing = (
            _fmt(row["crossing"])
            if row["crossing"] is not None
            else f"unknown ({row['crossing_unknown_orders']} orders lack a book)"
        )
        lines.append(
            f"| {order_type} | {_fmt(row['fee'])} | {crossing} | "
            f"{_fmt(row['slippage'])} | {_fmt(row['impact'])} | "
            f"{row['missed_fills']} / {_fmt(row['missed_qty'], 2)} |"
        )
    lines += [
        "",
        "Cost per filled notional (fees + slippage + impact, crossing "
        "excluded where unknown):",
        "",
    ]
    for order_type in ("market", "limit"):
        row = summary["by_type"][order_type]
        known = row["fee"] + row["slippage"] + row["impact"]
        bps = (
            10_000 * known / row["filled_notional"]
            if row["filled_notional"]
            else 0.0
        )
        lines.append(
            f"- {order_type}: {_fmt(known)} USDT on "
            f"{_fmt(row['filled_notional'], 2)} USDT filled notional = "
            f"{_fmt(bps, 2)} bps"
        )
    lines.append("")
    return lines


def main() -> None:
    config = SimulationConfig()  # defaults: 100 ms latency, 5 s max age
    ran_at = datetime.now(UTC)
    sections: list[str] = [
        "# Stage 4b validation replay report",
        "",
        f"- Replayed at: {ran_at.isoformat()}",
        "- Configuration (defaults): latency 100 ms, snapshot max age 5 s, "
        "market slippage 1 bp, impact coefficient 5 bps over top-5 depth, "
        "queue-ahead fallback 0.0, fee tier Regular (VIP 0), contract "
        "value 0.01 BTC",
        "- Order set: see `replay.py` (market buy/sell + 6-offset limit "
        "grid + at-market buy/sell limits per decision time, 1.0 "
        "contract each)",
        "",
    ]

    # --- 2h tape ------------------------------------------------------
    dataset_4a = load_dataset(*DATASET_4A)
    window_start = datetime.fromisoformat(dataset_4a.manifest["window"]["start"])
    decisions_4a = [
        window_start + timedelta(minutes=15 * k + 5) for k in range(8)
    ]
    orders_4a = build_order_set(
        dataset_4a, decisions_4a, cancel_after=timedelta(minutes=15), prefix="2h"
    )
    result_4a = simulate_orders(
        orders_4a, dataset_4a.trades, dataset_4a.snapshots, config=config
    )
    sections += _render_section(
        _summarize(
            "Two-hour tape (2026-11-18 05:00-07:00 UTC, 153,971 trades)",
            result_4a,
            orders_4a,
            dataset_4a,
        )
    )
    print(
        f"2h tape: {len(orders_4a)} orders, "
        f"{result_4a.orders_filled} filled, {result_4a.orders_partial} partial, "
        f"{result_4a.orders_unfilled} unfilled, "
        f"{result_4a.orders_cancelled} cancelled"
    )

    # --- dense window ---------------------------------------------------
    dataset_4b = load_dataset(*DATASET_4B)
    dense_start = datetime.fromisoformat(dataset_4b.manifest["window"]["start"])
    dense_end = datetime.fromisoformat(dataset_4b.manifest["window"]["end"])
    decisions_4b: list[datetime] = []
    cursor = dense_start + timedelta(seconds=60)
    while cursor + timedelta(seconds=60) <= dense_end:
        decisions_4b.append(cursor)
        cursor += timedelta(seconds=60)
    orders_4b = build_order_set(
        dataset_4b, decisions_4b, cancel_after=timedelta(seconds=60), prefix="dense"
    )
    result_4b = simulate_orders(
        orders_4b, dataset_4b.trades, dataset_4b.snapshots, config=config
    )
    sections += _render_section(
        _summarize(
            f"Dense window ({dense_start.isoformat()} to "
            f"{dense_end.isoformat()}, {len(dataset_4b.trades)} trades, "
            f"{len(dataset_4b.snapshots)} snapshots)",
            result_4b,
            orders_4b,
            dataset_4b,
        )
    )
    print(
        f"dense window: {len(orders_4b)} orders, "
        f"{result_4b.orders_filled} filled, {result_4b.orders_partial} partial, "
        f"{result_4b.orders_unfilled} unfilled, "
        f"{result_4b.orders_cancelled} cancelled"
    )

    sections += [
        "## Limitations of this validation",
        "",
        "- The order set is synthetic and fixed; fill rates describe the "
        "simulator's mechanics on these two windows, not any strategy.",
        "- The 2h tape has no in-window snapshots, so all of its market "
        "fills are book-unknown (first-print fallback) and all of its "
        "limit fills use the queue-ahead fallback of 0.0 (flagged); "
        "crossing costs there are unknown, not zero.",
        "- The dense window is ~10 minutes on one day for one instrument; "
        "nothing here generalizes beyond that.",
        "- Funding is zero because neither window crosses a settlement; "
        "the funding calculation itself is covered by unit tests.",
        "- Paper orders are replayed independently and do not consume "
        "tape volume for each other (see `docs/execution.md`).",
        "",
    ]
    report_path = ROOT / "validation_report.md"
    report_path.write_text("\n".join(sections), encoding="utf-8")
    print(f"validation report written: {report_path}")


if __name__ == "__main__":
    main()

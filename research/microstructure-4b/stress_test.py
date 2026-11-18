"""Stage 4b latency and stale-data stress tests.

Run from the repo root, after ``fetch_snapshots.py`` and ``replay.py``:

    .venv/bin/python research/microstructure-4b/stress_test.py

Replays the same fixed order set as ``replay.py`` under a grid of
assumptions, one dimension at a time around the defaults (latency
100 ms, snapshot max age 5 s, market slippage 1 bp):

- latency: 0 / 100 ms / 500 ms / 1 s (dense window)
- snapshot max age: 1 s / 5 s / 30 s (dense window)
- market slippage: 0 / 1 / 5 bps (dense window)
- queue-ahead fallback: 0 / 100 / 1,000 contracts (2h tape, limit
  orders only)
- sparse book: the dense snapshots subsampled to every 7th (~7 s
  gaps, phase-offset from the decision times) with max age 1 s /
  5 s / 30 s, to show the staleness rule biting — on the full dense
  series the snapshots are ~1 s apart, so max age 1–30 s makes no
  difference

The point is sensitivity, not optimization: no configuration is
"best", and the report shows how much each answer moves when an
assumption moves. Missed fills are reported explicitly in every run.

Writes ``stress_report.md`` in this directory.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from load_dataset import load_dataset
from replay import DATASET_4A, DATASET_4B, build_order_set

from myquant.execution import (
    CostConfig,
    SimulationConfig,
    SimulationResult,
    simulate_orders,
)

ROOT = Path(__file__).resolve().parent


def _row(label: str, result: SimulationResult) -> dict:
    """One result row: fill rates, costs, missed fills, unknown books."""
    market = [r for r in result.order_results if r.order.order_type == "market"]
    limit = [r for r in result.order_results if r.order.order_type == "limit"]

    def fill_rate(rows) -> float | None:
        total = sum(r.order.quantity for r in rows)
        if total == 0:
            return None
        filled = sum(r.filled_quantity for r in rows)
        return filled / total

    return {
        "label": label,
        "market_fill_rate": fill_rate(market),
        "limit_fill_rate": fill_rate(limit),
        "fee": result.total_fee,
        "slippage": result.total_slippage_cost,
        "impact": result.total_impact_cost,
        "missed_fills": result.missed_fills,
        "fills_book_unknown": result.fills_book_unknown,
        "fills_queue_unknown": result.fills_queue_unknown,
    }


def _pct(rate: float | None) -> str:
    return f"{100 * rate:.1f}%" if rate is not None else "n/a"


def _render_table(title: str, rows: list[dict]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Configuration | Market fill rate | Limit fill rate | Fees (USDT) | "
        "Slippage (USDT) | Impact (USDT) | Missed fills | "
        "Book-unknown fills | Queue-unknown fills |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {_pct(row['market_fill_rate'])} | "
            f"{_pct(row['limit_fill_rate'])} | {row['fee']:.4f} | "
            f"{row['slippage']:.4f} | {row['impact']:.4f} | "
            f"{row['missed_fills']} | {row['fills_book_unknown']} | "
            f"{row['fills_queue_unknown']} |"
        )
    lines.append("")
    return lines


def main() -> None:
    ran_at = datetime.now(UTC)
    lines = [
        "# Stage 4b latency and stale-data stress report",
        "",
        f"- Run at: {ran_at.isoformat()}",
        "- Defaults: latency 100 ms, snapshot max age 5 s, market "
        "slippage 1 bp, impact coefficient 5 bps, queue-ahead fallback "
        "0.0, fee tier Regular (VIP 0)",
        "- Order set: the same fixed set as `replay.py`",
        "",
    ]

    # --- dense window scans -------------------------------------------
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
    print(f"dense order set: {len(orders_4b)} orders")

    def run_dense(config: SimulationConfig) -> SimulationResult:
        return simulate_orders(
            orders_4b, dataset_4b.trades, dataset_4b.snapshots, config=config
        )

    latency_rows = []
    for latency_ms in (0, 100, 500, 1000):
        config = SimulationConfig(
            cost=CostConfig(snapshot_max_age=timedelta(seconds=5))
        )
        orders = [
            order.model_copy(
                update={"latency": timedelta(milliseconds=latency_ms)}
            )
            for order in orders_4b
        ]
        result = simulate_orders(
            orders, dataset_4b.trades, dataset_4b.snapshots, config=config
        )
        latency_rows.append(_row(f"latency {latency_ms} ms", result))
    lines += _render_table("Latency scan (dense window)", latency_rows)

    max_age_rows = []
    for max_age_seconds in (1, 5, 30):
        config = SimulationConfig(
            cost=CostConfig(snapshot_max_age=timedelta(seconds=max_age_seconds))
        )
        max_age_rows.append(
            _row(f"max age {max_age_seconds} s", run_dense(config))
        )
    lines += _render_table("Snapshot max-age scan (dense window)", max_age_rows)

    slippage_rows = []
    for slippage_bps in (0.0, 1.0, 5.0):
        config = SimulationConfig(
            cost=CostConfig(market_slippage_bps=slippage_bps)
        )
        slippage_rows.append(
            _row(f"slippage {slippage_bps:g} bps", run_dense(config))
        )
    lines += _render_table("Market-slippage scan (dense window)", slippage_rows)

    # --- queue-ahead sensitivity on the 2h tape ------------------------
    dataset_4a = load_dataset(*DATASET_4A)
    window_start = datetime.fromisoformat(dataset_4a.manifest["window"]["start"])
    decisions_4a = [
        window_start + timedelta(minutes=15 * k + 5) for k in range(8)
    ]
    orders_4a = build_order_set(
        dataset_4a, decisions_4a, cancel_after=timedelta(minutes=15), prefix="2h"
    )
    limit_4a = [o for o in orders_4a if o.order_type == "limit"]
    print(f"2h limit order set: {len(limit_4a)} orders")
    queue_rows = []
    for fallback in (0.0, 100.0, 1000.0):
        config = SimulationConfig(
            cost=CostConfig(queue_ahead_fallback=fallback)
        )
        result = simulate_orders(
            limit_4a, dataset_4a.trades, dataset_4a.snapshots, config=config
        )
        queue_rows.append(_row(f"queue fallback {fallback:g} contracts", result))
    lines += _render_table(
        "Queue-ahead fallback scan (2h tape, limit orders only)", queue_rows
    )

    # --- sparse-book max-age scan --------------------------------------
    # Every 7th dense snapshot, offset by 3: ~7 s gaps, and the stride
    # (7) does not divide the 60 s decision spacing, so arrivals land
    # at varying phases relative to the snapshots — the staleness rule
    # has something to bite on. (A stride of 10 would align with the
    # 60 s decision grid and defeat the test.)
    sparse_snapshots = dataset_4b.snapshots[3::7]
    print(
        f"sparse book: {len(sparse_snapshots)} snapshots "
        f"(every 7th of {len(dataset_4b.snapshots)}, offset 3)"
    )
    sparse_rows = []
    for max_age_seconds in (1, 5, 30):
        config = SimulationConfig(
            cost=CostConfig(snapshot_max_age=timedelta(seconds=max_age_seconds))
        )
        result = simulate_orders(
            orders_4b, dataset_4b.trades, sparse_snapshots, config=config
        )
        sparse_rows.append(_row(f"max age {max_age_seconds} s", result))
    lines += _render_table(
        "Snapshot max-age scan (dense window, every 7th snapshot)",
        sparse_rows,
    )

    lines += [
        "## Reading this report",
        "",
        "- Latency: missed fills grow with latency (0 at 0 ms, 4 at "
        "100 ms, 148 at 500 ms, 243 at 1 s), and the limit fill rate "
        "slips from 28.2% to 26.6% at 500 ms and above — the "
        "at-market limits lose fills they would have had. The grid "
        "limits (0.05%+ away from the reference) are unaffected "
        "within 1 s: no print reaches them that fast. The impact "
        "column moves with latency only because a later arrival reads "
        "a different snapshot's depth — that is snapshot variation, "
        "not a latency effect.",
        "- Snapshot max age: on the full dense series (~1 s cadence) "
        "max age 1–30 s makes no difference — every arrival finds a "
        "fresh snapshot. The sparse-book scan (every 7th snapshot) "
        "is where the staleness rule bites: a shorter max age means "
        "more market fills fall back to the first print and more "
        "crossing costs are unknown rather than priced.",
        "- Slippage moves market-order costs only; resting limit fills "
        "pay no slippage by construction (they fill at the limit price). "
        "Fill rates do not move with slippage.",
        "- Queue fallback: on the 2h tape, where no in-window snapshot "
        "exists, even a 1,000-contract queue ahead does not change "
        "the limit fill rate — the volume printed at each limit price "
        "over a 15-minute window dwarfs the queue. The queue "
        "assumption matters only for orders whose limit price is "
        "touched briefly; on this order set it is not the binding "
        "constraint. With fallback 0.0 the model assumes no queue "
        "ahead, which may overstate fills on thinner touches.",
        "",
    ]
    report_path = ROOT / "stress_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"stress report written: {report_path}")


if __name__ == "__main__":
    main()

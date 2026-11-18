"""Check whether H0003's forward sample is large enough to run its trial.

Run from the repo root:

    .venv/bin/python research/lowvol-002/check_h0003_sample.py

Fetches the latest OKX daily candles in memory (no cache writes),
builds the BTC/ETH/SOL panel, computes the preregistered PIT-correct
regime labels, and counts forward rows: regression rows whose decision
time (bar open) is on or after 2026-11-18T16:00Z and before
2027-03-31T16:00Z. H0003's trial runs when 60 low-volatility forward
rows exist.

This script counts rows only. It computes no test statistic — no
correlation, no coefficient, no p-value — so running it cannot peek at
the forward result. It writes its counts to h0003-sample-check.json.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from myquant.adapters.okx import candles_to_observations, fetch_history
from myquant.studies.panel import build_synchronized_panel
from myquant.studies.regime import classify_low_volatility

ROOT = Path(__file__).resolve().parent

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
SOL = "crypto:sol-usdt-perp"
INSTRUMENTS = (BTC, ETH, SOL)
OKX_IDS = {
    BTC: "BTC-USDT-SWAP",
    ETH: "ETH-USDT-SWAP",
    SOL: "SOL-USDT-SWAP",
}

WINDOW_START = datetime(2023, 1, 1, 16, 0, tzinfo=UTC)
FORWARD_START = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
FORWARD_END = datetime(2027, 3, 31, 16, 0, tzinfo=UTC)
MINIMUM_LOWVOL_ROWS = 60


def main() -> None:
    fetched_at = datetime.now(UTC)
    observations = []
    for instrument_id in INSTRUMENTS:
        result = fetch_history(
            OKX_IDS[instrument_id],
            "1D",
            start=WINDOW_START,
            end=fetched_at,
            delay_seconds=0.25,
        )
        observations.extend(
            candles_to_observations(
                result.candles,
                instrument_id=instrument_id,
                venue="okx",
                source_id="okx-public",
                source_version=1,
                ingested_at=fetched_at,
            )
        )
        print(f"{instrument_id}: {len(result.candles)} confirmed daily candles")
    panel = build_synchronized_panel(
        observations,
        instruments=INSTRUMENTS,
        bar_seconds=86_400,
    )
    print(f"panel: {panel.row_count} return rows")
    regime = classify_low_volatility(
        panel.returns[ETH],
        rv_window=30,
        median_window=252,
    )
    # Regression rows: row j predicts the return over bar j+1. A forward
    # row's decision time is bar j's open.
    labels = regime.is_low_vol.reindex(panel.returns.index[:-1])
    forward_mask = (panel.returns.index[:-1] >= FORWARD_START) & (
        panel.returns.index[:-1] < FORWARD_END
    )
    forward_labels = labels[forward_mask].dropna()
    forward_rows = int(forward_labels.shape[0])
    lowvol_forward_rows = int(forward_labels.sum())
    ready = lowvol_forward_rows >= MINIMUM_LOWVOL_ROWS
    eta: str | None = None
    if not ready and forward_rows > 0:
        rate = lowvol_forward_rows / forward_rows
        if rate > 0:
            days_needed = int(
                (MINIMUM_LOWVOL_ROWS - lowvol_forward_rows) / rate
            )
            eta = (fetched_at + timedelta(days=days_needed)).date().isoformat()
    record = {
        "checked_at": fetched_at.isoformat(),
        "forward_window": [
            FORWARD_START.isoformat(),
            FORWARD_END.isoformat(),
        ],
        "forward_rows": forward_rows,
        "lowvol_forward_rows": lowvol_forward_rows,
        "minimum_lowvol_rows": MINIMUM_LOWVOL_ROWS,
        "ready": ready,
        "first_forward_bar": (
            forward_labels.index[0].isoformat() if forward_rows else None
        ),
        "last_forward_bar": (
            forward_labels.index[-1].isoformat() if forward_rows else None
        ),
        "eta_estimate": eta,
    }
    output_path = ROOT / "h0003-sample-check.json"
    output_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"forward rows: {forward_rows}")
    print(f"low-volatility forward rows: {lowvol_forward_rows} / {MINIMUM_LOWVOL_ROWS}")
    print(f"ready to run the H0003 trial: {ready}")
    if eta is not None:
        print(f"rough ETA at the observed low-volatility rate: {eta}")
    print(f"record written: {output_path}")


if __name__ == "__main__":
    main()

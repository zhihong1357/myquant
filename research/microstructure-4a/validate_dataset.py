"""Validate the Stage 4a dataset: re-parse, normalize, compute metrics.

Run from the repo root, after fetch_data.py:

    .venv/bin/python research/microstructure-4a/validate_dataset.py

Reads the raw pages back from the local RawStore cache (verifying
checksums on read), re-parses them through the adapter, normalizes
trades and book snapshots, computes order-flow metrics at 1m/5m/1H,
and writes ``validation_report.md`` in this directory.

The smoke checks are descriptive data sanity checks, not hypothesis
tests: no p-values, no claims about prediction. In particular, the
CVD-direction agreement check only asks whether the pipeline's
arithmetic is internally consistent (buy-heavy buckets usually rising
in price); agreement is expected mechanically because taker buys lift
the price, and it says nothing about whether CVD predicts anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from myquant.adapters.okx_microstructure import (
    OKXTrade,
    parse_books_response,
    parse_ticker_response,
    parse_trades_response,
)
from myquant.microstructure import (
    BucketConfig,
    compute_order_flow_metrics,
    normalize_books_snapshot,
    normalize_trades,
)
from myquant.raw import RawStore

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "microstructure-4a"

INST_ID = "BTC-USDT-SWAP"
INSTRUMENT_ID = "crypto:btc-usdt-perp"
VENUE = "okx"
SOURCE_ID = "okx-public"
SOURCE_VERSION = 1

BUCKET_WIDTHS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "1H": timedelta(hours=1),
}


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def main() -> None:
    manifest_path = ROOT / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "manifest.json not found; run research/microstructure-4a/fetch_data.py first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_store = RawStore(CACHE_ROOT / "raw")
    validated_at = datetime.now(UTC)
    window_start = datetime.fromisoformat(manifest["window"]["start"])
    window_end = datetime.fromisoformat(manifest["window"]["end"])

    # --- trades: re-read, re-parse, normalize -------------------------
    trade_pages = manifest["trades"]["pages"]
    okx_trades: list[OKXTrade] = []
    parse_rejected = 0
    for page_entry in trade_pages:
        payload = raw_store.read_payload(page_entry["record_id"])
        page = parse_trades_response(payload, inst_id=INST_ID)
        okx_trades.extend(page.trades)
        parse_rejected += len(page.rejected)
    normalized = normalize_trades(
        okx_trades,
        parse_rejected=parse_rejected,
        instrument_id=INSTRUMENT_ID,
        venue=VENUE,
        source_id=SOURCE_ID,
        source_version=SOURCE_VERSION,
        ingested_at=validated_at,
    )
    # The stored pages include the overshoot on both ends of the
    # window: trades after `end` (fetched because paging starts at the
    # live head) and trades before `start` (the last page's tail).
    # Only the window [start, end) is the dataset; everything below
    # is computed on the in-window trades only.
    all_trades = normalized.trades
    trades = [t for t in all_trades if window_start <= t.event_time < window_end]
    before_start = sum(1 for t in all_trades if t.event_time < window_start)
    after_end = sum(1 for t in all_trades if t.event_time >= window_end)
    first_trade = trades[0] if trades else None
    last_trade = trades[-1] if trades else None
    report = normalized.report

    # Trade-ID contiguity inside the window (IDs are sequential).
    id_span = (
        last_trade.trade_id - first_trade.trade_id + 1
        if first_trade is not None and last_trade is not None
        else 0
    )
    coverage_seconds = (
        (last_trade.event_time - first_trade.event_time).total_seconds()
        if first_trade is not None and last_trade is not None
        else 0.0
    )

    # --- order-flow metrics at three widths ---------------------------
    metrics_by_width = {
        label: compute_order_flow_metrics(
            trades, config=BucketConfig(bucket_width=width)
        )
        for label, width in BUCKET_WIDTHS.items()
    }

    # --- CVD direction smoke check (1m buckets, descriptive only) -----
    agree = 0
    disagree = 0
    skipped = 0
    for bucket in metrics_by_width["1m"]:
        if bucket.trade_count == 0:
            skipped += 1
            continue
        assert bucket.first_price is not None and bucket.last_price is not None
        price_move = bucket.last_price - bucket.first_price
        if bucket.cvd_delta == 0 or price_move == 0:
            skipped += 1
        elif (bucket.cvd_delta > 0) == (price_move > 0):
            agree += 1
        else:
            disagree += 1
    checked = agree + disagree

    # --- VWAP vs last price (1m buckets) ------------------------------
    vwap_devs = [
        abs(bucket.vwap - bucket.last_price) / bucket.last_price
        for bucket in metrics_by_width["1m"]
        if bucket.vwap is not None and bucket.last_price is not None
    ]
    mean_vwap_dev = sum(vwap_devs) / len(vwap_devs) if vwap_devs else 0.0
    max_vwap_dev = max(vwap_devs) if vwap_devs else 0.0

    # --- large-trade share stats (1m buckets) -------------------------
    shares = [
        bucket.large_trade_share
        for bucket in metrics_by_width["1m"]
        if bucket.large_trade_share is not None
    ]
    mean_share = sum(shares) / len(shares) if shares else 0.0
    max_share = max(shares) if shares else 0.0

    # --- book snapshots: re-read, normalize, derive -------------------
    book_sections = []
    for entry in manifest["books"]:
        payload = raw_store.read_payload(entry["book_record_id"])
        okx_snapshot = parse_books_response(payload, inst_id=INST_ID)
        normalized_book = normalize_books_snapshot(
            okx_snapshot,
            instrument_id=INSTRUMENT_ID,
            venue=VENUE,
            source_id=SOURCE_ID,
            source_version=SOURCE_VERSION,
            ingested_at=validated_at,
        )
        snap = normalized_book.snapshot
        ticker_payload = raw_store.read_payload(entry["ticker_record_id"])
        ticker = parse_ticker_response(ticker_payload, inst_id=INST_ID)
        book_sections.append(
            {
                "label": entry["label"],
                "snapshot_time": snap.snapshot_time.isoformat(),
                "seq_id": snap.seq_id,
                "best_bid": snap.best_bid,
                "best_ask": snap.best_ask,
                "mid": snap.mid,
                "spread": snap.spread,
                "spread_bps": snap.spread_bps,
                "depth_bid_5": snap.depth_bid(5),
                "depth_ask_5": snap.depth_ask(5),
                "depth_bid_20": snap.depth_bid(20),
                "depth_ask_20": snap.depth_ask(20),
                "imbalance_5": snap.imbalance(5),
                "imbalance_20": snap.imbalance(20),
                "microprice": snap.microprice,
                "quality_issues": list(normalized_book.quality_issues),
                "ticker_bid_match": entry["ticker_book_bid_match"],
                "ticker_ask_match": entry["ticker_book_ask_match"],
                "ticker_last": ticker.last_price,
            }
        )

    # --- render the report --------------------------------------------
    m1 = metrics_by_width["1m"]
    m5 = metrics_by_width["5m"]
    m1h = metrics_by_width["1H"]
    lines = [
        "# Stage 4a dataset validation report",
        "",
        f"- Validated at: {validated_at.isoformat()}",
        f"- Window: {manifest['window']['start']} to {manifest['window']['end']} "
        f"(two complete UTC hours)",
        f"- Instrument: {INST_ID} ({INSTRUMENT_ID}), venue {VENUE}",
        "",
        "## Pull",
        "",
        f"- Trades endpoint: `{manifest['trades']['endpoint']}`, "
        f"page size {manifest['trades']['page_size']}, "
        f"delay {manifest['trades']['delay_seconds']}s",
        f"- Pages fetched: {manifest['trades']['page_count']}",
        f"- Trades in window: {len(trades)}",
        f"- Rows re-parsed from cache: {len(all_trades)} "
        f"({before_start} before window start, {after_end} after window end — "
        f"page overshoot, excluded from the dataset)",
        f"- Rejected rows (adapter): {parse_rejected}",
        f"- Skipped after window end (fetch log): "
        f"{manifest['trades']['skipped_after_end']}",
        f"- Trade-ID range (in window): "
        f"{first_trade.trade_id if first_trade else None} to "
        f"{last_trade.trade_id if last_trade else None}",
        f"- Trade-ID span: {id_span} IDs, {len(trades)} accepted "
        f"({id_span - len(trades)} missing from the window pull)",
        f"- Time coverage: "
        f"{first_trade.event_time.isoformat() if first_trade else None} "
        f"to {last_trade.event_time.isoformat() if last_trade else None} "
        f"({coverage_seconds:.1f}s)",
        f"- Mean trade rate: "
        f"{len(trades) / coverage_seconds if coverage_seconds else 0:.1f} trades/s",
        "",
        "## Normalization (over all re-parsed rows, before window filter)",
        "",
        f"- Received: {report.received}, accepted: {report.accepted}",
        f"- Duplicate trade IDs: {report.duplicate_trade_ids}",
        f"- Non-monotonic event times: {report.non_monotonic}",
        "",
        "## Order-flow metrics",
        "",
        f"- 1m buckets: {len(m1)} ({sum(1 for b in m1 if b.trade_count == 0)} empty)",
        f"- 5m buckets: {len(m5)} ({sum(1 for b in m5 if b.trade_count == 0)} empty)",
        f"- 1H buckets: {len(m1h)} ({sum(1 for b in m1h if b.trade_count == 0)} empty)",
        f"- Final 1m cumulative CVD: {_fmt(m1[-1].cvd_cumulative, 2)} contracts",
        f"- Sum of 1m CVD deltas: {_fmt(sum(b.cvd_delta for b in m1), 2)} "
        f"(must equal final cumulative CVD)",
        f"- Total volume: {_fmt(sum(b.total_volume for b in m1), 2)} contracts",
        f"- Mean 1m large-trade share (>= 1.0 contracts): {_fmt(mean_share)}; "
        f"max {_fmt(max_share)}",
        "- Note: at the 1.0-contract default threshold the large-trade "
        "share is near 1, i.e. almost all BTC volume prints in trades "
        "of >= 1.0 contracts. The default threshold is therefore weakly "
        "discriminating for this instrument; a meaningful large-trade "
        "split needs a higher, empirically chosen threshold.",
        "",
        "### Smoke checks (descriptive only, not hypothesis tests)",
        "",
        f"- CVD direction vs bucket price move (1m): {agree} of {checked} "
        f"non-empty, non-zero buckets agree "
        f"({100 * agree / checked if checked else 0:.1f}%), {skipped} skipped "
        f"(empty or zero CVD/price move). Agreement is expected "
        f"mechanically — taker buys lift the price — and is reported only "
        f"as a pipeline sanity check, not as evidence that CVD predicts "
        f"price.",
        f"- Mean |VWAP - last| / last (1m): {_fmt(mean_vwap_dev, 6)}; "
        f"max {_fmt(max_vwap_dev, 6)} (VWAP tracks the bucket's traded "
        f"prices by construction).",
        "",
        "## Book snapshots",
        "",
    ]
    for book in book_sections:
        lines += [
            f"### Snapshot ({book['label']}): {book['snapshot_time']}",
            "",
            f"- seq_id: {book['seq_id']}",
            f"- Best bid/ask: {book['best_bid']} / {book['best_ask']}",
            (
                f"- Mid: {book['mid']:.4f}, spread: {book['spread']:.4f} "
                f"({book['spread_bps']:.2f} bps)"
                if book["spread_bps"] is not None
                and book["mid"] is not None
                and book["spread"] is not None
                else "- Mid/spread: n/a (empty side)"
            ),
            f"- Depth (5 levels): bid {book['depth_bid_5']:.2f} / "
            f"ask {book['depth_ask_5']:.2f} contracts",
            f"- Depth (20 levels): bid {book['depth_bid_20']:.2f} / "
            f"ask {book['depth_ask_20']:.2f} contracts",
            f"- Imbalance (5 levels): {book['imbalance_5']:.4f}"
            if book["imbalance_5"] is not None
            else "- Imbalance (5 levels): n/a",
            f"- Imbalance (20 levels): {book['imbalance_20']:.4f}"
            if book["imbalance_20"] is not None
            else "- Imbalance (20 levels): n/a",
            f"- Microprice: {book['microprice']:.4f}"
            if book["microprice"] is not None
            else "- Microprice: n/a",
            f"- Quality issues: {book['quality_issues'] or 'none'}",
            f"- Ticker best bid/ask match the snapshot: "
            f"{book['ticker_bid_match']} / {book['ticker_ask_match']} "
            f"(ticker last: {book['ticker_last']})",
            "",
        ]
    lines += [
        "## Limitations of this validation",
        "",
        "- The window is two hours on one day for one instrument; nothing "
        "here generalizes beyond that.",
        "- The book snapshots are two points in time, not a continuous "
        "book; no L2 reconstruction was attempted.",
        "- The CVD smoke check is arithmetic sanity, not a predictive "
        "claim (see above).",
        "- The dataset is reproducible only while the window stays inside "
        "OKX's ~90-day history-trades depth; re-pull after ~2027-02-16 "
        "will return fewer rows.",
        "",
    ]
    (ROOT / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"validation report written: {ROOT / 'validation_report.md'}")
    print(
        f"trades={len(trades)} pages={len(trade_pages)} "
        f"rejected={parse_rejected} duplicates={report.duplicate_trade_ids} "
        f"non_monotonic={report.non_monotonic}"
    )
    print(f"1m buckets={len(m1)} 5m={len(m5)} 1H={len(m1h)}")
    print(
        f"CVD smoke: agree={agree} disagree={disagree} skipped={skipped} "
        f"({100 * agree / checked if checked else 0:.1f}% agreement)"
    )


if __name__ == "__main__":
    main()

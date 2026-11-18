# Stage 4a dataset validation report

- Validated at: 2026-11-18T07:50:59.083308+00:00
- Window: 2026-11-18T05:00:00+00:00 to 2026-11-18T07:00:00+00:00 (two complete UTC hours)
- Instrument: BTC-USDT-SWAP (crypto:btc-usdt-perp), venue okx

## Pull

- Trades endpoint: `/market/history-trades`, page size 100, delay 0.1s
- Pages fetched: 1780
- Trades in window: 153971
- Rows re-parsed from cache: 178000 (28 before window start, 24001 after window end — page overshoot, excluded from the dataset)
- Rejected rows (adapter): 0
- Skipped after window end (fetch log): 24001
- Trade-ID range (in window): 3094107829 to 3094261799
- Trade-ID span: 153971 IDs, 153971 accepted (0 missing from the window pull)
- Time coverage: 2026-11-18T05:00:00.016000+00:00 to 2026-11-18T06:59:59.843000+00:00 (7199.8s)
- Mean trade rate: 21.4 trades/s

## Normalization (over all re-parsed rows, before window filter)

- Received: 178000, accepted: 178000
- Duplicate trade IDs: 0
- Non-monotonic event times: 0

## Order-flow metrics

- 1m buckets: 120 (0 empty)
- 5m buckets: 24 (0 empty)
- 1H buckets: 2 (0 empty)
- Final 1m cumulative CVD: -36499.84 contracts
- Sum of 1m CVD deltas: -36499.84 (must equal final cumulative CVD)
- Total volume: 491235.08 contracts
- Mean 1m large-trade share (>= 1.0 contracts): 0.9637; max 0.9953
- Note: at the 1.0-contract default threshold the large-trade share is near 1, i.e. almost all BTC volume prints in trades of >= 1.0 contracts. The default threshold is therefore weakly discriminating for this instrument; a meaningful large-trade split needs a higher, empirically chosen threshold.

### Smoke checks (descriptive only, not hypothesis tests)

- CVD direction vs bucket price move (1m): 79 of 120 non-empty, non-zero buckets agree (65.8%), 0 skipped (empty or zero CVD/price move). Agreement is expected mechanically — taker buys lift the price — and is reported only as a pipeline sanity check, not as evidence that CVD predicts price.
- Mean |VWAP - last| / last (1m): 0.000211; max 0.000914 (VWAP tracks the bucket's traded prices by construction).

## Book snapshots

### Snapshot (before): 2026-11-18T07:20:52.701000+00:00

- seq_id: 354944663528
- Best bid/ask: 64749.9 / 64750.0
- Mid: 64749.9500, spread: 0.1000 (0.02 bps)
- Depth (5 levels): bid 1457.67 / ask 75.87 contracts
- Depth (20 levels): bid 1822.38 / ask 156.02 contracts
- Imbalance (5 levels): 0.9011
- Imbalance (20 levels): 0.8423
- Microprice: 64749.9947
- Quality issues: none
- Ticker best bid/ask match the snapshot: True / True (ticker last: 64749.9)

### Snapshot (after): 2026-11-18T07:49:34.551000+00:00

- seq_id: 354948799459
- Best bid/ask: 64705.8 / 64705.9
- Mid: 64705.8500, spread: 0.1000 (0.02 bps)
- Depth (5 levels): bid 1721.35 / ask 365.51 contracts
- Depth (20 levels): bid 1982.92 / ask 381.51 contracts
- Imbalance (5 levels): 0.6497
- Imbalance (20 levels): 0.6773
- Microprice: 64705.8811
- Quality issues: none
- Ticker best bid/ask match the snapshot: True / True (ticker last: 64705.8)

## Independent recomputation (2026-11-18, plain stdlib Python, no repo imports)

All numbers above were recomputed independently from the raw cached
pages (1,780 blobs), using only the committed `manifest.json` to
locate them:

- All 1,780 page payload SHA-256s match the manifest (cache integrity).
- 178,000 rows re-parsed; 28 pre-window, 24,001 post-window, 153,971
  in-window; trade IDs 3094107829–3094261799, exactly contiguous.
- Total volume 491,235.08 and final CVD −36,499.84 match exactly; the
  sum of 1m CVD deltas equals the final CVD.
- Mean/max 1m large-trade share 0.9637/0.9953, smoke agreement 79/120
  (65.8%), mean/max |VWAP − last| / last 0.000211/0.000914 — all match.
- Both book snapshots recomputed from their raw payloads: mid, spread,
  5/20-level depths, imbalances and microprice match to 4 decimals.
- Live spot check: page 500 of the manifest was re-fetched from OKX;
  its payload SHA-256 matches the manifest and all 100 trade IDs are
  identical, so the cached copy matches the live source.

## Limitations of this validation

- The window is two hours on one day for one instrument; nothing here generalizes beyond that.
- The book snapshots are two points in time, not a continuous book; no L2 reconstruction was attempted.
- The CVD smoke check is arithmetic sanity, not a predictive claim (see above).
- The dataset is reproducible only while the window stays inside OKX's ~90-day history-trades depth; re-pull after ~2027-02-16 will return fewer rows.

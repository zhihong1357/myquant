# Stage 4b latency and stale-data stress report

- Run at: 2026-11-18T08:28:48.709689+00:00
- Defaults: latency 100 ms, snapshot max age 5 s, market slippage 1 bp, impact coefficient 5 bps, queue-ahead fallback 0.0, fee tier Regular (VIP 0)
- Order set: the same fixed set as `replay.py`

## Latency scan (dense window)

| Configuration | Market fill rate | Limit fill rate | Fees (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills | Book-unknown fills | Queue-unknown fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| latency 0 ms | 100.0% | 28.2% | 8.4635 | 1.0334 | 0.0575 | 0 | 0 | 0 |
| latency 100 ms | 100.0% | 28.2% | 8.4635 | 1.0334 | 0.0575 | 4 | 0 | 0 |
| latency 500 ms | 100.0% | 26.6% | 8.3342 | 1.1588 | 0.0437 | 148 | 0 | 0 |
| latency 1000 ms | 100.0% | 26.6% | 8.7193 | 1.2444 | 0.0120 | 243 | 0 | 0 |

## Snapshot max-age scan (dense window)

| Configuration | Market fill rate | Limit fill rate | Fees (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills | Book-unknown fills | Queue-unknown fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| max age 1 s | 100.0% | 28.2% | 8.4635 | 1.0334 | 0.0575 | 4 | 0 | 0 |
| max age 5 s | 100.0% | 28.2% | 8.4635 | 1.0334 | 0.0575 | 4 | 0 | 0 |
| max age 30 s | 100.0% | 28.2% | 8.4635 | 1.0334 | 0.0575 | 4 | 0 | 0 |

## Market-slippage scan (dense window)

| Configuration | Market fill rate | Limit fill rate | Fees (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills | Book-unknown fills | Queue-unknown fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| slippage 0 bps | 100.0% | 28.2% | 8.4635 | 0.0000 | 0.0575 | 4 | 0 | 0 |
| slippage 1 bps | 100.0% | 28.2% | 8.4635 | 1.0334 | 0.0575 | 4 | 0 | 0 |
| slippage 5 bps | 100.0% | 28.2% | 8.4635 | 5.1670 | 0.0575 | 4 | 0 | 0 |

## Queue-ahead fallback scan (2h tape, limit orders only)

| Configuration | Market fill rate | Limit fill rate | Fees (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills | Book-unknown fills | Queue-unknown fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| queue fallback 0 contracts | n/a | 59.4% | 4.9111 | 0.0000 | 0.0000 | 3 | 347 | 347 |
| queue fallback 100 contracts | n/a | 59.4% | 4.9111 | 0.0000 | 0.0000 | 3 | 347 | 347 |
| queue fallback 1000 contracts | n/a | 59.4% | 4.9111 | 0.0000 | 0.0000 | 3 | 377 | 377 |

## Snapshot max-age scan (dense window, every 7th snapshot)

| Configuration | Market fill rate | Limit fill rate | Fees (USDT) | Slippage (USDT) | Impact (USDT) | Missed fills | Book-unknown fills | Queue-unknown fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| max age 1 s | 100.0% | 26.6% | 7.5595 | 1.0334 | 0.0012 | 4 | 130 | 116 |
| max age 5 s | 100.0% | 29.7% | 8.5900 | 1.2163 | 0.0107 | 4 | 53 | 49 |
| max age 30 s | 100.0% | 29.7% | 8.9774 | 1.2809 | 0.0127 | 4 | 0 | 0 |

## Reading this report

- Latency: missed fills grow with latency (0 at 0 ms, 4 at 100 ms, 148 at 500 ms, 243 at 1 s), and the limit fill rate slips from 28.2% to 26.6% at 500 ms and above — the at-market limits lose fills they would have had. The grid limits (0.05%+ away from the reference) are unaffected within 1 s: no print reaches them that fast. The impact column moves with latency only because a later arrival reads a different snapshot's depth — that is snapshot variation, not a latency effect.
- Snapshot max age: on the full dense series (~1 s cadence) max age 1–30 s makes no difference — every arrival finds a fresh snapshot. The sparse-book scan (every 7th snapshot) is where the staleness rule bites: a shorter max age means more market fills fall back to the first print and more crossing costs are unknown rather than priced.
- Slippage moves market-order costs only; resting limit fills pay no slippage by construction (they fill at the limit price). Fill rates do not move with slippage.
- Queue fallback: on the 2h tape, where no in-window snapshot exists, even a 1,000-contract queue ahead does not change the limit fill rate — the volume printed at each limit price over a 15-minute window dwarfs the queue. The queue assumption matters only for orders whose limit price is touched briefly; on this order set it is not the binding constraint. With fallback 0.0 the model assumes no queue ahead, which may overstate fills on thinner touches.

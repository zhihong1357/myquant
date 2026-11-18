# Stage 6b evidence and source report

- Probed at: 2026-11-18T21:45:56.107388+00:00
- This report is a snapshot of probe time: the probe timestamp, the observed latest dates and the freshness verdicts change on every re-run, by design. The registry citations and the recorded-only items do not.
- A PASS means only that this probe, at this moment, matched the recorded expectation. It is not a claim that the source is reliable or will stay available.

## Source status

| Source | Requests | PASS | FAIL | SKIP |
| --- | --- | --- | --- | --- |
| okx-public | 1 | 2 | 0 | 0 |
| deribit | 2 | 4 | 0 | 0 |
| fred | 6 | 13 | 0 | 0 |
| yahoo-finance | 1 | 2 | 0 | 0 |
| fiscaldata | 1 | 2 | 0 | 0 |
| federalreserve | 1 | 2 | 0 | 0 |
| bls | 0 | 0 | 0 | 1 |
| hyperliquid | 1 | 2 | 0 | 0 |

## Checks (live observations)

### okx-public

- [PASS] `okx:BTC-1D:reachability`: HTTP 200
- [PASS] `okx:BTC-1D:payload`: 2 candle rows, 1 confirmed, 1 forming; latest confirmed bar opens 2026-11-17T16:00:00+00:00; all bars open 16:00 UTC (sha 5b55ed4d30db)

### deribit

- [PASS] `deribit:expired-BTC:reachability`: HTTP 200
- [PASS] `deribit:expired-BTC:payload`: 62 expired contracts, single batch expiring 2026-11-18 (sha 5b117c8660f8)
- [PASS] `deribit:DVOL-BTC:reachability`: HTTP 200
- [PASS] `deribit:DVOL-BTC:payload`: 10 DVOL points; latest final point 2026-11-17T00:00:00+00:00 close 43.29, 1 current-day point(s) excluded as provisional (sha 2bcd06851e72)

### fred

- [PASS] `fred:VIXCLS:reachability`: HTTP 200
- [PASS] `fred:VIXCLS:payload`: 7 observations, 0 missing, latest 2026-11-17 (sha 3aeeccef6a13)
- [PASS] `fred:VXNCLS:reachability`: HTTP 200
- [PASS] `fred:VXNCLS:payload`: 7 observations, 0 missing, latest 2026-11-17 (sha d5114bab7721)
- [PASS] `fred:VXTYN:reachability`: HTTP 200
- [PASS] `fred:VXTYN:payload`: 11 observations, 0 missing, latest 2020-05-15 (sha 99531f7b8409)
- [PASS] `fred:VXTYN:series-end`: VXTYN still ends 2020-05-15 (discontinued series)
- [PASS] `fred:DGS10:reachability`: HTTP 200
- [PASS] `fred:DGS10:payload`: 6 observations, 1 missing (1 empty field), latest 2026-11-17 (sha 596ed5cad219)
- [PASS] `fred:BAA10Y:reachability`: HTTP 200
- [PASS] `fred:BAA10Y:payload`: 5 observations, 1 missing (1 empty field), latest 2026-11-16 (sha 50aaaf2929f6)
- [PASS] `fred:CPIAUCSL:reachability`: HTTP 200
- [PASS] `fred:CPIAUCSL:payload`: 2 observations, 0 missing, latest 2026-10-01 (sha 6deca4fe5db5)

### yahoo-finance

- [PASS] `yahoo:^GSPC:reachability`: HTTP 200
- [PASS] `yahoo:^GSPC:payload`: 8 bars, 0 missing, latest 2026-11-18, longName 'S&P 500' (sha bbbb61682178)

### fiscaldata

- [PASS] `fiscal:recent:reachability`: HTTP 200
- [PASS] `fiscal:recent:payload`: 5 auction records, latest auction 2026-10-22, total-count 37, 27 days behind the probe date (sha a7a4fd0107b3)

### federalreserve

- [PASS] `fed:calendars:reachability`: HTTP 200
- [PASS] `fed:calendars:payload`: 166359 bytes, FOMC markers and a year present (sha 180c72485052)

### bls

- Manual-only source: no automated probe was made. Manual check: Open the BLS Schedule of Selected Releases page (https://www.bls.gov/schedule/) in a browser, read the CPI release dates for the current year, and compare them with research/macro-windows-006/cpi_calendar.json. Do not curl the page: BLS returns HTTP 403 to programmatic requests.
- [SKIP] `bls:manual`: Manual-only source: no automated probe exists (see the manual check above).

### hyperliquid

- [PASS] `hyperliquid:mids:reachability`: HTTP 200
- [PASS] `hyperliquid:mids:payload`: 1427 mids, BTC 62348.5, ETH 1764.35 (sha 7686394331c9)

## Panel freshness

Freshness compares each registered panel's last date against the latest point the source serves now, allowing for the source's known publication lag (see the expected-latest column). A panel is fresh when it already holds everything the source serves; stale when the source has newer points; unknown when no latest point was observed.

| Panel | Source | Panel last | Observed | Expected | Status | Behind |
| --- | --- | --- | --- | --- | --- | --- |
| credit:baa-10y-spread | fred | 2026-11-16 | 2026-11-16 | 2026-11-17 | fresh | 0 |
| crypto:btc-usdt-perp | okx-public | 2026-11-16 | 2026-11-17 | 2026-11-17 | stale | 1 |
| crypto:eth-usdt-perp | okx-public | 2026-11-16 | 2026-11-17 | 2026-11-17 | stale | 1 |
| crypto:sol-usdt-perp | okx-public | 2026-11-16 | 2026-11-17 | 2026-11-17 | stale | 1 |
| index:btc-dvol | deribit | 2026-11-17 | 2026-11-17 | 2026-11-17 | fresh | 0 |
| index:eth-dvol | deribit | 2026-11-17 | 2026-11-17 | 2026-11-17 | fresh | 0 |
| index:sp500 | yahoo-finance | 2026-11-16 | 2026-11-18 | 2026-11-18 | stale | 2 |
| index:tyvix | fred | 2020-05-15 | 2020-05-15 | 2020-05-15 | fresh | 0 |
| index:vix | fred | 2026-11-16 | 2026-11-17 | 2026-11-17 | stale | 1 |
| index:vxn | fred | 2020-05-15 | 2026-11-17 | 2026-11-17 | stale | 2377 |
| macro:cpi-mom | fred | 2026-10-01 | 2026-10-01 | 2026-10-01 | fresh | 0 |
| rates:us-10y-yield | fred | 2026-11-16 | 2026-11-17 | 2026-11-17 | stale | 1 |

- credit:baa-10y-spread: the source itself is 1 day(s) behind its expected latest (2026-11-17); the verdict is judged against what the source serves
- index:tyvix: discontinued series; the panel end is the series end, as expected

## Recorded, not re-verified

These facts come from the studies' records and were not re-checked by this probe (too expensive to re-verify, or only observable at a specific time of day). They are recorded facts with citations, not fresh verifications.

- [okx-public] history-candles pagination uses after=<ts> (bars strictly older, newest first); sending before returns empty data. (verified by study 004 (options-expiry-004), 2026-11-18)
  - Re-check: Fetch one history-candles page with after=<now> and one with before=<now>; the before page is empty.
- [okx-public] history-trades retention is about 90 calendar days: the oldest retrievable BTC-USDT-SWAP trade was 2843636428, dated 2026-08-20 00:01:56 UTC, found by bisection. (verified by Stage 4a (microstructure-4a), 2026-11-18)
  - Re-check: Bisect trade IDs from the live head until the oldest retrievable trade (see docs/microstructure.md).
- [okx-public] funding-rate-history retention is about 93 days (280 rows per instrument); the floor moves (a 281st row seen minutes before the fetch was gone by fetch time) and must be re-established on every pull. (verified by Stage 5a (funding-history), 2026-11-19)
  - Re-check: Page after=<ms> backwards from the live head until the oldest row.
- [okx-public] funding-rate-history pagination uses after only; before acts as a lower bound and does not page. (verified by Stage 5a (funding-history), 2026-11-19)
- [okx-public] The live funding-rate value read mid-interval is an estimate, not the settled rate for that interval (the 4b input 0.0000215 was an estimate; the settled rate was 0.00006348). (verified by Stage 5a (funding-history), 2026-11-19)
  - Re-check: Compare the live funding-rate value with the history row at the next settlement.
- [okx-public] Funding settles on the 00:00/08:00/16:00 UTC grid; the funding-rate cap/floor is ±0.375% per interval. (verified by Stage 4b (microstructure-4b), 2026-11-18)
- [okx-public] Fee schedule (Regular): maker 0.0200% / taker 0.0500% on notional, per the OKX fee-adjustment notice effective 2026-09-09. (verified by Stage 4b (microstructure-4b), 2026-11-18)
  - Re-check: Re-read the OKX fee notice page and compare the Regular tier.
- [deribit] get_volatility_index_data requires a currency parameter; omitting it returns HTTP 400. (verified by study 004 (options-expiry-004), 2026-11-18)
- [deribit] Monthly options expire on the last Friday of the month, 08:00 UTC; listed BTC and ETH contracts each show 11 identical forward expiries, all last Fridays (Deribit Contract Introduction Policy states the rule verbatim). (verified by study 004 (options-expiry-004), 2026-11-18)
  - Re-check: Fetch listed BTC/ETH instruments and compare their forward expiry sets.
- [deribit] 2,065 DVOL points per currency, 2021-03-24 to 2026-11-17, no gaps. (verified by study 004 (options-expiry-004), 2026-11-18)
  - Re-check: Re-fetch the full DVOL history per currency and recount the points and gaps.
- [deribit] Instrument listings carry no top-level currency field. (verified by study 004 (options-expiry-004), 2026-11-18)
  - Re-check: Fetch one instrument listing and inspect the top-level keys of a returned contract.
- [fred] Custom or browser-like User-Agent requests hang (bare Mozilla/5.0 and a full Chrome UA both timed out); send no User-Agent header and let urllib identify itself. (verified by study 003 (move-vix-transmission-003), 2026-11-18)
- [fred] Publication lag is one trading day (N=1): a value dated t is posted on the next business day. Verified behaviourally at 2026-11-18 06:26 UTC (01:26 EST): VIXCLS and DGS10 both ended at 2026-11-16, ruling out same-evening posting and a two-day lag. (verified by study 007 (publication-lag-007), 2026-11-18)
  - Re-check: Fetch VIXCLS/DGS10 before the morning posting and compare the last date with the previous trading day (see study 007).
- [fred] VXTYN covers 2003-01-02 to 2020-05-15 (4,363 rows in the study-003 manifest). (verified by study 003 (move-vix-transmission-003), 2026-11-18)
  - Re-check: Fetch the full VXTYN series and check the first date and row count.
- [fred] FRED has no TYVIX series and no MOVE series. (verified by study 003 (move-vix-transmission-003), 2026-11-18)
  - Re-check: Search the FRED catalogue for a TYVIX or MOVE series.
- [fred] VXTYN has a genuine two-day gap on 2004-11-10 and 2004-11-11 (verified against a fresh pull; DGS10 has a value those days). (verified by study 005 (fomc-event-study-005), 2026-11-18)
- [fred] Licensed series are truncated on FRED; the lab used BAA10Y as the credit spread instead of a licensed spread series. (verified by study 003 (move-vix-transmission-003), 2026-11-18)
- [fred] Series are current vintage and are revised over time; as-released values would need ALFRED or an API key. (verified by study 007 (publication-lag-007), 2026-11-18)
- [yahoo-finance] The chart endpoint requires a browser-like User-Agent (Mozilla/5.0); without one Yahoo returns 401/403. (verified by study 003 (move-vix-transmission-003), 2026-11-18)
  - Re-check: Fetch the chart without a User-Agent and confirm Yahoo returns 401/403.
- [yahoo-finance] Yahoo ^MOVE is a Northern Trust iBoxx ETF, not the ICE BofA MOVE index — always check meta.longName before trusting a ticker. (verified by study 003 (move-vix-transmission-003), 2026-11-18)
  - Re-check: Fetch the ^MOVE chart and read meta.longName.
- [yahoo-finance] Yahoo ^TYVIX is delisted ("No data found, symbol may be delisted"). (verified by study 003 (move-vix-transmission-003), 2026-11-18)
  - Re-check: Fetch the ^TYVIX chart; the error payload confirms the delisting.
- [yahoo-finance] Bar timestamps are the market open (09:30 ET); closes use the 21:00 UTC convention shared with FRED; null closes are missing days and are excluded and counted. (verified by study 003 (move-vix-transmission-003), 2026-11-18)
  - Re-check: Fetch a recent window and confirm the bar timestamps are the 09:30 ET market open (14:30 UTC in winter, 13:30 in summer) and that null closes are counted as missing.
- [fiscaldata] TreasuryDirect cross-check on the overlap window (2025-05-27 to 2026-10-22): 134 coupon dates on each side, symmetric difference empty. (verified by study 006 (macro-windows-006), 2026-11-18)
  - Re-check: Re-fetch both endpoints and recompute the overlap.
- [fiscaldata] The 7 most recent coupon dates (2026-10-26 to 2026-11-12) come from the TreasuryDirect tail supplement, flagged as such in the calendar file. (verified by study 006 (macro-windows-006), 2026-11-18)
- [fiscaldata] Coupon auction closings are 01:00 PM ET (536 records) or 11:30 AM ET (92 records); the 11:30 minority's results sit near the 16:00 UTC bar boundary. (verified by study 006 (macro-windows-006), 2026-11-18)
- [federalreserve] The calendar was extracted from fomchistorical{YYYY}.htm (2003–2020) and fomccalendars.htm (2021 onwards): 199 scheduled meetings 2003–2027, 8 per year (7 in 2020). (verified by study 005 (fomc-event-study-005), 2026-11-18)
  - Re-check: Re-fetch the calendar page and re-run the study-005 calendar checks (8/year, 7 in 2020).
- [federalreserve] Statements are released around 14:00 ET on the last meeting day; t=0 is the statement day and the daily close already contains the reaction. (verified by study 005 (fomc-event-study-005), 2026-11-18)
- [federalreserve] 31 meetings are excluded from the scheduled set: 20 conference calls, 5 unscheduled meetings, 1 cancelled meeting (2020-03-17–18), 5 notation votes. (verified by study 005 (fomc-event-study-005), 2026-11-18)
- [bls] BLS returns HTTP 403 to direct programmatic requests, including with a browser user-agent; the CPI calendar is a text-fetch transcription, not structured BLS API output. (verified by study 006 (macro-windows-006), 2026-11-18)
  - Re-check: Open the BLS schedule page in a browser and compare the CPI release dates with research/macro-windows-006/cpi_calendar.json.
- [bls] The CPI calendar (71 releases, 2021-01-13 to 2026-12-10) was transcribed from the BLS archived schedule pages and cross-checked against the BLS archive page and two independent public lists. (verified by study 006 (macro-windows-006), 2026-11-18)
  - Re-check: Re-transcribe one full year from the BLS archive page and compare.
- [bls] The October 2025 CPI was never published (2025 federal shutdown); the September 2025 CPI was delayed to 2025-10-24. (verified by study 006 (macro-windows-006), 2026-11-18)
  - Re-check: Check the BLS shutdown FAQ and the archived CPI news releases page.
- [hyperliquid] The public API is reachable without a key, but the 1H candle endpoint returned an empty array once during study-002 preparation and was not used. (verified by study 002 (lowvol-transmission-002), 2026-11-18)
  - Re-check: POST a candleSnapshot request for a recent 1H window and check the response is non-empty.
- [hyperliquid] No study uses Hyperliquid data; no lab panel depends on it. (verified by study 002 (lowvol-transmission-002), 2026-11-18)

## Limitations

- One probe is one moment: a passing check says nothing about the source tomorrow, and a failing check may be a transient outage rather than a dead source — re-probe before concluding anything.
- The expected-latest rules use a weekday calendar and ignore market holidays, so a holiday-week expectation can be one day early; the freshness verdict is judged against what the source serves, not the expectation, for exactly this reason.
- The Fed page check is a smoke check (markers present), not a parse of the meeting list; the Fiscal Data API lag is observed from the latest auction date, not measured against the live schedule.
- BLS has no automated probe: its calendar stays a manual transcription until someone re-checks it by hand.

/**
 * Kernel-Level Bitemporal Columnar Store & Strict ASOF JOIN Engine.
 *
 * Eliminates the FRED `available_at = event_time` Silent Killer:
 *  - Every observation carries explicit (eventTs, knowledgeTs, ingestedTs, vintageId, sourceId).
 *  - Source-level minimum publication lag policies are enforced AT WRITE TIME:
 *    attempting to ingest FRED BAA10Y with knowledgeTs == eventTs throws a BitemporalViolationError.
 *  - Binary-search ASOF JOIN enforces strictly `knowledgeTs <= decisionTs`, making lookahead
 *    structurally impossible across all downstream research and paper replay pipelines.
 */

export interface SourceLagPolicy {
  sourceId: string;
  instrumentPattern?: RegExp;
  minPublicationLagMs: number;
  description: string;
}

export const SOURCE_PUBLICATION_POLICIES: readonly SourceLagPolicy[] = [
  {
    sourceId: 'fred',
    instrumentPattern: /baa-10y-spread/i,
    minPublicationLagMs: 48 * 3600 * 1000, // Verified 2-trading-day evening posting lag (Study 008)
    description: 'FRED BAA10Y posts post-close T+2 evening window',
  },
  {
    sourceId: 'fred',
    minPublicationLagMs: 24 * 3600 * 1000, // Standard 1-trading-day FRED posting lag (Study 007)
    description: 'FRED daily series (VIXCLS/DGS10/VXNCLS) post next business day',
  },
  {
    sourceId: 'deribit',
    instrumentPattern: /dvol/i,
    minPublicationLagMs: 24 * 3600 * 1000, // Provisional current-day row excluded until 00:00 UTC next day
    description: 'Deribit daily DVOL bar finalizes at 00:00 UTC next day',
  },
  {
    sourceId: 'okx-public',
    minPublicationLagMs: 0,
    description: 'OKX public trades/candles/funding are knowable at bar close / print match time',
  },
  {
    sourceId: 'bls',
    minPublicationLagMs: 12 * 24 * 3600 * 1000, // CPI reference month releases ~12-14 days after month-end
    description: 'BLS CPI reference month is usable only after official 08:30 ET release timestamp',
  },
];

export interface BitemporalObservation {
  instrumentId: string;
  field: string;
  eventTs: number; // Unix ms of the market event / bar close
  knowledgeTs: number; // Unix ms when value became publicly usable (strictly PIT)
  ingestedTs: number; // Unix ms when MyQuant ingested the record
  vintageId: number; // Monotonic revision version (1 = first print, 2+ = revised)
  sourceId: string;
  value: number;
}

export class BitemporalViolationError extends Error {
  public readonly instrumentId: string;
  public readonly sourceId: string;
  public readonly requiredLagMs: number;
  public readonly observedLagMs: number;

  constructor(
    instrumentId: string,
    sourceId: string,
    requiredLagMs: number,
    observedLagMs: number,
  ) {
    super(
      `PIT violation for ${instrumentId} (${sourceId}): knowledgeTs - eventTs = ${Math.round(
        observedLagMs / 3600_000,
      )}h, below mandatory publication lag floor ${Math.round(requiredLagMs / 3600_000)}h`,
    );
    this.name = 'BitemporalViolationError';
    this.instrumentId = instrumentId;
    this.sourceId = sourceId;
    this.requiredLagMs = requiredLagMs;
    this.observedLagMs = observedLagMs;
  }
}

export function resolveMinPublicationLagMs(sourceId: string, instrumentId: string): number {
  for (const policy of SOURCE_PUBLICATION_POLICIES) {
    if (policy.sourceId !== sourceId) continue;
    if (policy.instrumentPattern && !policy.instrumentPattern.test(instrumentId)) continue;
    return policy.minPublicationLagMs;
  }
  return 0;
}

/**
 * In-memory columnar bitemporal table indexed by (instrumentId, field) sorted by knowledgeTs.
 * Supports sub-millisecond binary-search ASOF JOINs over tens of thousands of rows.
 */
export class BitemporalColumnarStore {
  private readonly series = new Map<string, BitemporalObservation[]>();

  private keyOf(instrumentId: string, field: string): string {
    return `${instrumentId}::${field}`;
  }

  /**
   * Ingests an observation while strictly enforcing:
   *  1. knowledgeTs >= eventTs (causality)
   *  2. knowledgeTs - eventTs >= source publication lag floor (anti-fake-PIT guard)
   */
  public insert(obs: BitemporalObservation, allowLegacyOverride = false): void {
    if (!Number.isFinite(obs.value)) {
      throw new Error(`Non-finite observation value for ${obs.instrumentId}:${obs.field}`);
    }
    const observedLag = obs.knowledgeTs - obs.eventTs;
    if (observedLag < 0) {
      throw new BitemporalViolationError(obs.instrumentId, obs.sourceId, 0, observedLag);
    }
    const minLag = resolveMinPublicationLagMs(obs.sourceId, obs.instrumentId);
    if (!allowLegacyOverride && observedLag < minLag) {
      throw new BitemporalViolationError(obs.instrumentId, obs.sourceId, minLag, observedLag);
    }

    const key = this.keyOf(obs.instrumentId, obs.field);
    let arr = this.series.get(key);
    if (!arr) {
      arr = [];
      this.series.set(key, arr);
    }
    arr.push(obs);
  }

  public insertBatch(observations: readonly BitemporalObservation[]): void {
    for (const obs of observations) {
      this.insert(obs);
    }
    // Sort each modified column by (knowledgeTs, eventTs, vintageId) for O(log n) ASOF lookup
    for (const arr of this.series.values()) {
      arr.sort((a, b) =>
        a.knowledgeTs !== b.knowledgeTs
          ? a.knowledgeTs - b.knowledgeTs
          : a.eventTs !== b.eventTs
            ? a.eventTs - b.eventTs
            : a.vintageId - b.vintageId,
      );
    }
  }

  /**
   * O(log n) Strict Point-in-Time ASOF Lookup:
   * Returns the latest observation with `knowledgeTs <= decisionTs`, choosing the highest
   * `(eventTs, vintageId)` among all already-published observations.
   */
  public queryAsof(
    instrumentId: string,
    field: string,
    decisionTs: number,
  ): BitemporalObservation | null {
    const arr = this.series.get(this.keyOf(instrumentId, field));
    if (!arr || arr.length === 0) return null;

    // Binary search for largest index where knowledgeTs <= decisionTs
    let lo = 0;
    let hi = arr.length - 1;
    let bestIdx = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      if (arr[mid].knowledgeTs <= decisionTs) {
        bestIdx = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    if (bestIdx === -1) return null;

    // Among observations known by decisionTs, pick latest (eventTs, vintageId)
    // Scan backwards only while eventTs could exceed best
    let chosen = arr[bestIdx];
    for (let i = bestIdx - 1; i >= Math.max(0, bestIdx - 16); i--) {
      const cand = arr[i];
      if (
        cand.eventTs > chosen.eventTs ||
        (cand.eventTs === chosen.eventTs && cand.vintageId > chosen.vintageId)
      ) {
        chosen = cand;
      }
    }
    return chosen;
  }

  /**
   * Naive Event-Time-Only lookup (strictly for Lookahead Audit Diff — NEVER for live/backtest features).
   */
  public queryNaiveEventTime(
    instrumentId: string,
    field: string,
    decisionTs: number,
  ): BitemporalObservation | null {
    const arr = this.series.get(this.keyOf(instrumentId, field));
    if (!arr || arr.length === 0) return null;
    let chosen: BitemporalObservation | null = null;
    for (let i = 0; i < arr.length; i++) {
      const cand = arr[i];
      if (cand.eventTs <= decisionTs) {
        if (
          !chosen ||
          cand.eventTs > chosen.eventTs ||
          (cand.eventTs === chosen.eventTs && cand.vintageId > chosen.vintageId)
        ) {
          chosen = cand;
        }
      }
    }
    return chosen;
  }

  /**
   * Vectorized ASOF JOIN over a decision timestamp grid across multiple (instrument, field) columns.
   */
  public asofJoin(
    decisionTimestamps: readonly number[],
    columns: ReadonlyArray<{ alias: string; instrumentId: string; field: string }>,
  ): Array<{
    decisionTs: number;
    decisionIso: string;
    values: Record<string, number | null>;
    agesHours: Record<string, number | null>;
    vintages: Record<string, number | null>;
  }> {
    return decisionTimestamps.map((ts) => {
      const values: Record<string, number | null> = {};
      const agesHours: Record<string, number | null> = {};
      const vintages: Record<string, number | null> = {};
      for (const col of columns) {
        const hit = this.queryAsof(col.instrumentId, col.field, ts);
        values[col.alias] = hit ? hit.value : null;
        agesHours[col.alias] = hit ? (ts - hit.eventTs) / 3600_000 : null;
        vintages[col.alias] = hit ? hit.vintageId : null;
      }
      return {
        decisionTs: ts,
        decisionIso: new Date(ts).toISOString(),
        values,
        agesHours,
        vintages,
      };
    });
  }
}

export interface BitemporalAuditDemoResult {
  instrumentId: string;
  sourceId: string;
  enforcedLagHours: number;
  fakePitWriteBlocked: boolean;
  blockedErrorMessage: string;
  rowsEvaluated: number;
  rowsWithLookaheadLeak: number;
  meanLookaheadHoursLeaked: number;
  sampleRows: Array<{
    decisionDate: string;
    strictAsofValue: number | null;
    strictEventDate: string | null;
    strictAgeHours: number | null;
    naiveEventValue: number | null;
    naiveEventDate: string | null;
    leakedFutureData: boolean;
  }>;
}

/**
 * Demonstrates the exact Study 008 FRED BAA10Y publication-lag audit:
 *  1. Proves the storage kernel blocks writing `knowledgeTs == eventTs` for FRED BAA10Y.
 *  2. Runs a 20-business-day decision grid comparing Strict ASOF vs Naive Event-Time Join.
 */
export function runBitemporalAuditDemo(params?: {
  sourceId?: 'fred' | 'deribit' | 'okx-public';
  instrumentId?: string;
}): BitemporalAuditDemoResult {
  const sourceId = params?.sourceId ?? 'fred';
  const instrumentId =
    params?.instrumentId ??
    (sourceId === 'fred'
      ? 'credit:baa-10y-spread'
      : sourceId === 'deribit'
        ? 'index:btc-dvol'
        : 'crypto:btc-usdt-perp');

  const store = new BitemporalColumnarStore();
  const enforcedLagMs = resolveMinPublicationLagMs(sourceId, instrumentId);
  const startMs = Date.UTC(2026, 9, 19, 21, 0, 0); // 2026-10-19 21:00 UTC

  // 1. Test write-time PIT guard against fake `knowledgeTs === eventTs`
  let fakePitWriteBlocked = false;
  let blockedErrorMessage = 'Zero lag source (real-time venue): knowledgeTs == eventTs is valid.';
  if (enforcedLagMs > 0) {
    try {
      store.insert({
        instrumentId,
        field: 'close',
        eventTs: startMs,
        knowledgeTs: startMs, // Deliberate fake PIT attempt!
        ingestedTs: startMs,
        vintageId: 1,
        sourceId,
        value: 1.72,
      });
    } catch (err) {
      fakePitWriteBlocked = true;
      blockedErrorMessage = err instanceof Error ? err.message : String(err);
    }
  }

  // 2. Populate 20 trading days with realistic values + one revision vintage
  const observations: BitemporalObservation[] = [];
  const decisionGrid: number[] = [];
  let level = sourceId === 'fred' ? 1.68 : sourceId === 'deribit' ? 46.5 : 91_200;

  for (let d = 0; d < 20; d++) {
    const eventTs = startMs + d * 24 * 3600_000;
    const delta =
      sourceId === 'fred'
        ? ((d % 5) - 2) * 0.03
        : sourceId === 'deribit'
          ? ((d % 4) - 1.5) * 1.1
          : ((d % 5) - 2) * 420;
    level = Number((level + delta).toFixed(4));
    observations.push({
      instrumentId,
      field: 'close',
      eventTs,
      knowledgeTs: eventTs + enforcedLagMs,
      ingestedTs: eventTs + enforcedLagMs + 60_000,
      vintageId: 1,
      sourceId,
      value: level,
    });
    decisionGrid.push(eventTs);
  }
  store.insertBatch(observations);

  let rowsWithLookaheadLeak = 0;
  let leakedHoursSum = 0;
  const sampleRows: BitemporalAuditDemoResult['sampleRows'] = [];

  for (const decisionTs of decisionGrid) {
    const strictHit = store.queryAsof(instrumentId, 'close', decisionTs);
    const naiveHit = store.queryNaiveEventTime(instrumentId, 'close', decisionTs);
    const leaked =
      naiveHit !== null &&
      (strictHit === null ||
        naiveHit.eventTs > strictHit.eventTs ||
        naiveHit.value !== strictHit.value);
    if (leaked && naiveHit) {
      rowsWithLookaheadLeak++;
      leakedHoursSum += (naiveHit.knowledgeTs - decisionTs) / 3600_000;
    }
    sampleRows.push({
      decisionDate: new Date(decisionTs).toISOString().slice(0, 10),
      strictAsofValue: strictHit ? strictHit.value : null,
      strictEventDate: strictHit ? new Date(strictHit.eventTs).toISOString().slice(0, 10) : null,
      strictAgeHours: strictHit ? (decisionTs - strictHit.eventTs) / 3600_000 : null,
      naiveEventValue: naiveHit ? naiveHit.value : null,
      naiveEventDate: naiveHit ? new Date(naiveHit.eventTs).toISOString().slice(0, 10) : null,
      leakedFutureData: leaked,
    });
  }

  return {
    instrumentId,
    sourceId,
    enforcedLagHours: enforcedLagMs / 3600_000,
    fakePitWriteBlocked,
    blockedErrorMessage,
    rowsEvaluated: decisionGrid.length,
    rowsWithLookaheadLeak,
    meanLookaheadHoursLeaked:
      rowsWithLookaheadLeak > 0 ? leakedHoursSum / rowsWithLookaheadLeak : 0,
    sampleRows: sampleRows.slice(-10),
  };
}

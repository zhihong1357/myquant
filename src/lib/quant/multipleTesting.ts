/**
 * Static FWER/FDR (Bonferroni, Holm, BH) + Sequential Online FDR Control (LORD++ & SAFFRON)
 * and Research Hygiene Filters (excluding mechanical identity edges & discontinued series).
 *
 * Online FDR references:
 *  - Ramdas, Yang, Wainwright & Jordan (2017): "Online Control of the False Discovery Rate
 *    with Decaying Memory" (LORD++).
 *  - Ramdas, Zrnic, Wainwright & Jordan (2018): "SAFFRON: An Adaptive Algorithm for Online
 *    Control of the False Discovery Rate".
 */

export type MultiplicityMethod =
  | 'none'
  | 'bonferroni'
  | 'holm'
  | 'benjamini_hochberg'
  | 'online_lord_pp'
  | 'online_saffron';

export interface AdjustedPValue {
  originalIndex: number;
  rawPValue: number;
  adjustedPValue: number;
  alphaThreshold?: number;
  reject: boolean;
  method: MultiplicityMethod;
  targetErrorRate: number;
}

/**
 * Known mechanical identity edges and discontinued/untradable series flagged by Red-Team Audit.
 */
export const MECHANICAL_EDGE_IDS = new Set<string>(['E0026']);
export const DISCONTINUED_INSTRUMENTS = new Set<string>(['index:tyvix']);

export interface HygieneTaggedEdge {
  edge_id: string;
  source_instrument?: string;
  target_instrument?: string;
  status: string;
  p_value: number | null;
  [key: string]: unknown;
}

export interface HygieneAssessment {
  edgeId: string;
  isMechanicalIdentity: boolean;
  usesDiscontinuedSeries: boolean;
  cleanForPlanner: boolean;
  reason: string | null;
}

export function assessEdgeHygiene(edge: HygieneTaggedEdge): HygieneAssessment {
  const isMechanicalIdentity = MECHANICAL_EDGE_IDS.has(edge.edge_id);
  const usesDiscontinuedSeries =
    (typeof edge.source_instrument === 'string' &&
      DISCONTINUED_INSTRUMENTS.has(edge.source_instrument)) ||
    (typeof edge.target_instrument === 'string' &&
      DISCONTINUED_INSTRUMENTS.has(edge.target_instrument));

  let reason: string | null = null;
  if (isMechanicalIdentity) {
    reason = 'Mechanical identity: BAA10Y = BAA - DGS10 contains target by definition';
  } else if (usesDiscontinuedSeries) {
    reason = 'Discontinued series: FRED VXTYN (TYVIX) ended 2020-05-15 with zero modern regime coverage';
  }

  return {
    edgeId: edge.edge_id,
    isMechanicalIdentity,
    usesDiscontinuedSeries,
    cleanForPlanner: !isMechanicalIdentity && !usesDiscontinuedSeries,
    reason,
  };
}

export function filterCleanLabEdges<T extends HygieneTaggedEdge>(edges: readonly T[]): {
  clean: T[];
  excluded: Array<{ edge: T; assessment: HygieneAssessment }>;
} {
  const clean: T[] = [];
  const excluded: Array<{ edge: T; assessment: HygieneAssessment }> = [];
  for (const edge of edges) {
    const assessment = assessEdgeHygiene(edge);
    if (assessment.cleanForPlanner) {
      clean.push(edge);
    } else {
      excluded.push({ edge, assessment });
    }
  }
  return { clean, excluded };
}

/**
 * Standard gamma_m sequence for online FDR:
 * gamma_m = 0.07720838 * log(max(m, 2)) / (m * exp(sqrt(log(m)))), normalized to sum <= 1.
 */
function buildGammaSequence(length: number): number[] {
  const raw = new Array<number>(length);
  let sum = 0;
  for (let m = 1; m <= length; m++) {
    const val = Math.log(Math.max(m, 2)) / (m * Math.exp(Math.sqrt(Math.log(m))));
    raw[m - 1] = val;
    sum += val;
  }
  // Infinite series sum of raw is ~12.952; normalize conservatively so partial sum <= 1.0
  const norm = Math.max(sum, 12.952);
  return raw.map((v) => v / norm);
}

/**
 * Online LORD++ sequential FDR control (Ramdas et al., 2017).
 * Valid even when hypothesis t+1 is selected adaptively after observing outcomes 1..t!
 */
export function onlineLordPlusPlus(
  pValues: readonly number[],
  targetFdr = 0.05,
  initialWealthFraction = 0.5,
): AdjustedPValue[] {
  const n = pValues.length;
  const gamma = buildGammaSequence(n + 2);
  const w0 = targetFdr * initialWealthFraction;
  const rejectionTimes: number[] = [];
  const results: AdjustedPValue[] = [];

  for (let t = 1; t <= n; t++) {
    let alphaT = w0 * gamma[t - 1];
    if (rejectionTimes.length > 0) {
      const tau1 = rejectionTimes[0];
      alphaT += (targetFdr - w0) * gamma[t - tau1 - 1];
      for (let j = 1; j < rejectionTimes.length; j++) {
        const tauJ = rejectionTimes[j];
        alphaT += targetFdr * gamma[t - tauJ - 1];
      }
    }
    alphaT = Math.min(targetFdr, Math.max(1e-12, alphaT));
    const p = pValues[t - 1];
    const reject = p <= alphaT;
    if (reject) {
      rejectionTimes.push(t);
    }
    // Effective adjusted p-value scaled relative to targetFdr
    const effectiveAdj = Math.min(1.0, (p * targetFdr) / alphaT);
    results.push({
      originalIndex: t - 1,
      rawPValue: p,
      adjustedPValue: effectiveAdj,
      alphaThreshold: alphaT,
      reject,
      method: 'online_lord_pp',
      targetErrorRate: targetFdr,
    });
  }
  return results;
}

/**
 * Online SAFFRON adaptive sequential FDR control (Ramdas et al., 2018).
 * Estimates the proportion of true nulls online using candidacy threshold lambda (default 0.5),
 * preserving alpha wealth when non-nulls appear sequentially.
 */
export function onlineSaffron(
  pValues: readonly number[],
  targetFdr = 0.05,
  lambda = 0.5,
  initialWealthFraction = 0.5,
): AdjustedPValue[] {
  const n = pValues.length;
  const gamma = buildGammaSequence(n + 2);
  const w0 = (1 - lambda) * targetFdr * initialWealthFraction;
  const candidateFlags: number[] = []; // C_j = 1 if p_j <= lambda
  const rejectionTimes: number[] = [];
  const results: AdjustedPValue[] = [];

  for (let t = 1; t <= n; t++) {
    // Count candidates since start and since each rejection
    const cPlus = (afterIdx: number) => {
      let count = 0;
      for (let i = afterIdx; i < candidateFlags.length; i++) {
        count += candidateFlags[i];
      }
      return count;
    };

    const gIdx0 = Math.max(0, t - 1 - cPlus(0));
    let alphaT = w0 * gamma[Math.min(gIdx0, gamma.length - 1)];

    if (rejectionTimes.length > 0) {
      const tau1 = rejectionTimes[0];
      const idx1 = Math.max(0, t - tau1 - 1 - cPlus(tau1));
      alphaT += ((1 - lambda) * targetFdr - w0) * gamma[Math.min(idx1, gamma.length - 1)];
      for (let j = 1; j < rejectionTimes.length; j++) {
        const tauJ = rejectionTimes[j];
        const idxJ = Math.max(0, t - tauJ - 1 - cPlus(tauJ));
        alphaT += (1 - lambda) * targetFdr * gamma[Math.min(idxJ, gamma.length - 1)];
      }
    }

    alphaT = Math.min(lambda, Math.max(1e-12, alphaT));
    const p = pValues[t - 1];
    const reject = p <= alphaT;
    candidateFlags.push(p <= lambda ? 1 : 0);
    if (reject) {
      rejectionTimes.push(t);
    }

    const effectiveAdj = Math.min(1.0, (p * targetFdr) / alphaT);
    results.push({
      originalIndex: t - 1,
      rawPValue: p,
      adjustedPValue: effectiveAdj,
      alphaThreshold: alphaT,
      reject,
      method: 'online_saffron',
      targetErrorRate: targetFdr,
    });
  }
  return results;
}

export function adjustPValues(
  pValues: readonly number[],
  method: MultiplicityMethod,
  targetErrorRate = 0.05,
): AdjustedPValue[] {
  if (!Array.isArray(pValues) || pValues.length === 0) {
    throw new Error('pValues must not be empty');
  }
  for (const v of pValues) {
    if (!Number.isFinite(v) || v < 0 || v > 1) {
      throw new Error('pValues must all be finite numbers in [0, 1]');
    }
  }
  if (!Number.isFinite(targetErrorRate) || targetErrorRate <= 0 || targetErrorRate >= 1) {
    throw new Error('targetErrorRate must lie strictly between 0 and 1');
  }
  if (method === 'none' && pValues.length !== 1) {
    throw new Error('NONE correction is only valid for a single planned test');
  }

  if (method === 'online_lord_pp') {
    return onlineLordPlusPlus(pValues, targetErrorRate);
  }
  if (method === 'online_saffron') {
    return onlineSaffron(pValues, targetErrorRate);
  }

  const count = pValues.length;
  const order = pValues
    .map((value, index) => ({ value, index }))
    .sort((a, b) => (a.value !== b.value ? a.value - b.value : a.index - b.index));

  const sortedAdjusted = new Array<number>(count);

  if (method === 'none') {
    sortedAdjusted[0] = order[0].value;
  } else if (method === 'bonferroni') {
    for (let i = 0; i < count; i++) {
      sortedAdjusted[i] = Math.min(1.0, order[i].value * count);
    }
  } else if (method === 'holm') {
    let runningMax = 0;
    for (let i = 0; i < count; i++) {
      const candidate = order[i].value * (count - i);
      runningMax = Math.max(runningMax, candidate);
      sortedAdjusted[i] = Math.min(1.0, runningMax);
    }
  } else if (method === 'benjamini_hochberg') {
    let runningMin = 1.0;
    for (let i = count - 1; i >= 0; i--) {
      const rank = i + 1;
      const candidate = (order[i].value * count) / rank;
      runningMin = Math.min(runningMin, candidate);
      sortedAdjusted[i] = Math.min(1.0, runningMin);
    }
  } else {
    throw new Error(`Unsupported multiple-testing method: ${String(method)}`);
  }

  const adjustedByOriginal = new Array<number>(count);
  for (let i = 0; i < count; i++) {
    adjustedByOriginal[order[i].index] = sortedAdjusted[i];
  }

  return pValues.map((raw, index) => {
    const adj = adjustedByOriginal[index];
    return {
      originalIndex: index,
      rawPValue: raw,
      adjustedPValue: adj,
      reject: adj <= targetErrorRate,
      method,
      targetErrorRate,
    };
  });
}

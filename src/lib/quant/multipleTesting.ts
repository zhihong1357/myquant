/**
 * Family-wise and false-discovery multiple-testing corrections.
 * Direct TypeScript port of myquant.stats.multiple_testing.adjust_pvalues.
 */

export type MultiplicityMethod = 'none' | 'bonferroni' | 'holm' | 'benjamini_hochberg';

export interface AdjustedPValue {
  originalIndex: number;
  rawPValue: number;
  adjustedPValue: number;
  reject: boolean;
  method: MultiplicityMethod;
  targetErrorRate: number;
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

/**
 * Institutional Backtest Overfitting Controls:
 *  1. Combinatorially Symmetric Cross-Validation (CSCV) Probability of Backtest Overfitting (PBO)
 *     — Bailey, Borwein, Lopez de Prado & Zhu (2015).
 *  2. Non-Gaussian Deflated Sharpe Ratio (DSR)
 *     — Bailey & Lopez de Prado (2014), accounting for skewness, excess kurtosis,
 *       independent trial count, and cross-trial Sharpe variance.
 */

import { normalCdf, normalPpf } from './normal.ts';
import { createMulberry32 } from './leadLag.ts';

export interface DeflatedSharpeInput {
  returns: readonly number[];
  numTrials: number;
  trialSharpeVariance?: number; // Variance of annualized or per-period Sharpe across trials
  periodsPerYear?: number;
}

export interface DeflatedSharpeResult {
  observations: number;
  sharpePerPeriod: number;
  sharpeAnnualized: number;
  skewness: number;
  excessKurtosis: number;
  expectedMaxSharpeNull: number;
  deflatedSharpeRatio: number; // Probability true SR > SR_0*
  passesThreshold95: boolean;
}

export interface CscvPboResult {
  numStrategies: number;
  observations: number;
  numSubsets: number;
  combinationsEvaluated: number;
  pbo: number; // Fraction of combinations with logit <= 0 (OOS rank <= median)
  meanRelativeOosRank: number;
  medianLogit: number;
  degradationSlope: number; // OLS slope of OOS Sharpe on IS Sharpe across winning trials
  logits: number[];
}

function sampleMoments(series: readonly number[]) {
  const n = series.length;
  if (n < 4) {
    throw new Error('At least 4 observations required to compute higher moments');
  }
  let mean = 0;
  for (let i = 0; i < n; i++) mean += series[i];
  mean /= n;

  let m2 = 0;
  let m3 = 0;
  let m4 = 0;
  for (let i = 0; i < n; i++) {
    const d = series[i] - mean;
    const d2 = d * d;
    m2 += d2;
    m3 += d2 * d;
    m4 += d2 * d2;
  }
  const variance = m2 / (n - 1);
  const std = Math.sqrt(Math.max(0, variance));
  const skewness = std > 1e-12 ? m3 / n / Math.pow(std, 3) : 0;
  const excessKurtosis = std > 1e-12 ? m4 / n / Math.pow(std, 4) - 3 : 0;
  return { mean, std, skewness, excessKurtosis };
}

function sharpeOf(series: readonly number[]): number {
  const n = series.length;
  if (n < 2) return 0;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += series[i];
  mean /= n;
  let ss = 0;
  for (let i = 0; i < n; i++) {
    const d = series[i] - mean;
    ss += d * d;
  }
  const std = Math.sqrt(ss / (n - 1));
  return std > 1e-12 ? mean / std : 0;
}

/**
 * Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio.
 * Computes P(SR* > SR_0) where SR_0 is the expected maximum Sharpe under N independent null trials.
 */
export function computeDeflatedSharpeRatio(input: DeflatedSharpeInput): DeflatedSharpeResult {
  const n = input.returns.length;
  const numTrials = Math.max(1, Math.floor(input.numTrials));
  const periodsPerYear = input.periodsPerYear ?? 252;
  const { mean, std, skewness, excessKurtosis } = sampleMoments(input.returns);
  const sr = std > 1e-12 ? mean / std : 0;
  const srAnnual = sr * Math.sqrt(periodsPerYear);

  // Expected maximum Sharpe across numTrials null trials (Euler-Mascheroni extreme value approx)
  const EULER_GAMMA = 0.5772156649015329;
  const trialStd = Math.sqrt(
    Math.max(1e-12, input.trialSharpeVariance ?? 1 / Math.max(1, n - 1)),
  );
  let sr0 = 0;
  if (numTrials > 1) {
    const z1 = normalPpf(1 - 1 / numTrials);
    const z2 = normalPpf(1 - 1 / (numTrials * Math.E));
    sr0 = trialStd * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2);
  }

  // Non-Gaussian Sharpe standard error denominator: sqrt((1 - g3*SR + ((g4 + 2)/4)*SR^2) / (n - 1))
  const kurtosisFull = excessKurtosis + 3;
  const varTerm = Math.max(
    1e-9,
    1 - skewness * sr + ((kurtosisFull - 1) / 4) * sr * sr,
  );
  const zStat = ((sr - sr0) * Math.sqrt(Math.max(1, n - 1))) / Math.sqrt(varTerm);
  const dsr = normalCdf(zStat);

  return {
    observations: n,
    sharpePerPeriod: sr,
    sharpeAnnualized: srAnnual,
    skewness,
    excessKurtosis,
    expectedMaxSharpeNull: sr0,
    deflatedSharpeRatio: dsr,
    passesThreshold95: dsr >= 0.95,
  };
}

function generateCombinations(total: number, choose: number, maxCombos: number, seed: number): number[][] {
  const results: number[][] = [];
  // Estimate C(total, choose)
  let totalPossible = 1;
  for (let i = 1; i <= choose; i++) {
    totalPossible = (totalPossible * (total - choose + i)) / i;
  }

  if (totalPossible <= maxCombos) {
    const current: number[] = [];
    const dfs = (start: number) => {
      if (current.length === choose) {
        results.push([...current]);
        return;
      }
      for (let i = start; i <= total - (choose - current.length); i++) {
        current.push(i);
        dfs(i + 1);
        current.pop();
      }
    };
    dfs(0);
    return results;
  }

  // Deterministic Fisher-Yates sampling when C(S, S/2) > maxCombos
  const rng = createMulberry32(seed);
  const seen = new Set<string>();
  const indices = Array.from({ length: total }, (_, i) => i);
  let attempts = 0;
  while (results.length < maxCombos && attempts < maxCombos * 5) {
    attempts++;
    const copy = [...indices];
    for (let i = total - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      const tmp = copy[i];
      copy[i] = copy[j];
      copy[j] = tmp;
    }
    const combo = copy.slice(0, choose).sort((a, b) => a - b);
    const key = combo.join(',');
    if (!seen.has(key)) {
      seen.add(key);
      results.push(combo);
    }
  }
  return results;
}

/**
 * Combinatorially Symmetric Cross-Validation (CSCV) Probability of Backtest Overfitting.
 * Input: strategyReturns[m][t] — matrix of M strategies across T aligned periods.
 */
export function computeCscvPbo(
  strategyReturns: readonly (readonly number[])[],
  numSubsets = 8,
  maxCombinations = 252,
  seed = 2026,
): CscvPboResult {
  const M = strategyReturns.length;
  if (M < 2) {
    throw new Error('CSCV PBO requires at least 2 strategy return series');
  }
  const T = Math.min(...strategyReturns.map((s) => s.length));
  const S = numSubsets % 2 === 0 ? Math.max(4, Math.min(16, numSubsets)) : Math.max(4, numSubsets - 1);
  if (T < S * 4) {
    throw new Error(`Insufficient observations (${T}) for ${S} CSCV subsets`);
  }

  const blockSize = Math.floor(T / S);
  const usableT = blockSize * S;

  // Pre-slice each strategy into S contiguous blocks
  const blocks: number[][][] = Array.from({ length: M }, (_, m) =>
    Array.from({ length: S }, (_, s) =>
      strategyReturns[m].slice(s * blockSize, (s + 1) * blockSize),
    ),
  );

  const halfS = S / 2;
  const combos = generateCombinations(S, halfS, maxCombinations, seed);
  const logits: number[] = [];
  const relativeRanks: number[] = [];
  const winningIsSharpes: number[] = [];
  const winningOosSharpes: number[] = [];

  for (const trainSet of combos) {
    const trainMask = new Set(trainSet);
    const isSharpes = new Array<number>(M);
    const oosSharpes = new Array<number>(M);

    for (let m = 0; m < M; m++) {
      const isArr: number[] = [];
      const oosArr: number[] = [];
      for (let s = 0; s < S; s++) {
        const blk = blocks[m][s];
        if (trainMask.has(s)) {
          for (let i = 0; i < blk.length; i++) isArr.push(blk[i]);
        } else {
          for (let i = 0; i < blk.length; i++) oosArr.push(blk[i]);
        }
      }
      isSharpes[m] = sharpeOf(isArr);
      oosSharpes[m] = sharpeOf(oosArr);
    }

    // Best in-sample strategy n*
    let bestIdx = 0;
    for (let m = 1; m < M; m++) {
      if (isSharpes[m] > isSharpes[bestIdx]) bestIdx = m;
    }

    // Relative OOS rank of n* in (0, 1)
    let strictlyBetterCount = 0;
    let tiedCount = 0;
    const targetOos = oosSharpes[bestIdx];
    for (let m = 0; m < M; m++) {
      if (oosSharpes[m] < targetOos) strictlyBetterCount++;
      else if (oosSharpes[m] === targetOos) tiedCount++;
    }
    const rank1Based = strictlyBetterCount + 0.5 * (tiedCount + 1);
    const omegaBar = Math.max(1 / (M + 1), Math.min(M / (M + 1), rank1Based / (M + 1)));
    const logit = Math.log(omegaBar / (1 - omegaBar));

    relativeRanks.push(omegaBar);
    logits.push(logit);
    winningIsSharpes.push(isSharpes[bestIdx]);
    winningOosSharpes.push(targetOos);
  }

  const pbo = logits.filter((l) => l <= 0).length / Math.max(1, logits.length);
  const meanRelativeOosRank =
    relativeRanks.reduce((acc, v) => acc + v, 0) / Math.max(1, relativeRanks.length);
  const sortedLogits = [...logits].sort((a, b) => a - b);
  const medianLogit = sortedLogits[Math.floor(sortedLogits.length / 2)] ?? 0;

  // Linear degradation slope: OOS Sharpe regressed on IS Sharpe
  const meanIs = winningIsSharpes.reduce((a, b) => a + b, 0) / Math.max(1, winningIsSharpes.length);
  const meanOos =
    winningOosSharpes.reduce((a, b) => a + b, 0) / Math.max(1, winningOosSharpes.length);
  let cov = 0;
  let varIs = 0;
  for (let i = 0; i < winningIsSharpes.length; i++) {
    const dx = winningIsSharpes[i] - meanIs;
    cov += dx * (winningOosSharpes[i] - meanOos);
    varIs += dx * dx;
  }
  const degradationSlope = varIs > 1e-12 ? cov / varIs : 0;

  return {
    numStrategies: M,
    observations: usableT,
    numSubsets: S,
    combinationsEvaluated: combos.length,
    pbo,
    meanRelativeOosRank,
    medianLogit,
    degradationSlope,
    logits,
  };
}

/**
 * Deterministic synthetic transmission panel generator and OLS / Newey-West HAC
 * partial lead-lag estimator.
 * Ported from myquant.synthetic + myquant.stats.regression + myquant.stats.hac + myquant.stats.lead_lag.
 */

import { twoSidedPValueFromZ } from './normal.ts';

export type SyntheticScenario =
  | 'null'
  | 'source_leads_target'
  | 'common_factor'
  | 'regime_shift';

export interface SyntheticLeadLagParams {
  scenario: SyntheticScenario;
  observations: number;
  beta: number;
  commonFactorLoading: number;
  lagSteps: number;
  maxHacLag: number;
  controlCommonFactor: boolean;
  seed: number;
}

export interface LeadLagResult {
  scenario: SyntheticScenario;
  observations: number;
  lagSteps: number;
  maxHacLag: number;
  controlCommonFactor: boolean;
  coefficient: number;
  standardError: number;
  tStatistic: number;
  pValue: number;
  rSquared: number;
  partialRSquared: number;
  incrementalRSquared: number;
  samplePoints: Array<{ x: number; y: number; t: number }>;
}

function createMulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function createStandardNormal(seed: number): () => number {
  const uniform = createMulberry32(seed);
  let spare: number | null = null;
  return () => {
    if (spare !== null) {
      const value = spare;
      spare = null;
      return value;
    }
    let u = 0;
    let v = 0;
    while (u === 0) u = uniform();
    while (v === 0) v = uniform();
    const mag = Math.sqrt(-2.0 * Math.log(u));
    spare = mag * Math.sin(2.0 * Math.PI * v);
    return mag * Math.cos(2.0 * Math.PI * v);
  };
}

function invertMatrix(matrix: number[][]): number[][] {
  const n = matrix.length;
  const aug = matrix.map((row, i) => [
    ...row,
    ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0)),
  ]);

  for (let col = 0; col < n; col++) {
    let pivotRow = col;
    let maxVal = Math.abs(aug[col][col]);
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(aug[r][col]) > maxVal) {
        maxVal = Math.abs(aug[r][col]);
        pivotRow = r;
      }
    }
    if (maxVal < 1e-12) {
      throw new Error('Design matrix is singular or collinear');
    }
    if (pivotRow !== col) {
      const tmp = aug[col];
      aug[col] = aug[pivotRow];
      aug[pivotRow] = tmp;
    }
    const pivot = aug[col][col];
    for (let j = 0; j < 2 * n; j++) {
      aug[col][j] /= pivot;
    }
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const factor = aug[r][col];
      for (let j = 0; j < 2 * n; j++) {
        aug[r][j] -= factor * aug[col][j];
      }
    }
  }
  return aug.map((row) => row.slice(n));
}

function fitOlsHac(X: number[][], y: number[], maxHacLag: number) {
  const n = y.length;
  const k = X[0].length;

  // Compute X'X and X'y
  const xtx = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  const xty = new Array<number>(k).fill(0);
  for (let i = 0; i < n; i++) {
    const row = X[i];
    const yi = y[i];
    for (let a = 0; a < k; a++) {
      xty[a] += row[a] * yi;
      for (let b = 0; b < k; b++) {
        xtx[a][b] += row[a] * row[b];
      }
    }
  }

  const xtxInv = invertMatrix(xtx);
  const beta = new Array<number>(k).fill(0);
  for (let a = 0; a < k; a++) {
    let sum = 0;
    for (let b = 0; b < k; b++) {
      sum += xtxInv[a][b] * xty[b];
    }
    beta[a] = sum;
  }

  const residuals = new Array<number>(n);
  let meanY = 0;
  for (let i = 0; i < n; i++) meanY += y[i];
  meanY /= n;

  let sse = 0;
  let sst = 0;
  for (let i = 0; i < n; i++) {
    let pred = 0;
    for (let a = 0; a < k; a++) pred += X[i][a] * beta[a];
    const res = y[i] - pred;
    residuals[i] = res;
    sse += res * res;
    sst += (y[i] - meanY) * (y[i] - meanY);
  }
  const rSquared = sst > 0 ? Math.max(0, 1 - sse / sst) : 0;

  // Newey-West Bartlett HAC Meat matrix: S = sum_{l=-L}^{L} w_l sum_t (x_t e_t)(x_{t-l} e_{t-l})'
  const meat = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  const scores: number[][] = new Array(n);
  for (let i = 0; i < n; i++) {
    scores[i] = X[i].map((v) => v * residuals[i]);
  }

  for (let i = 0; i < n; i++) {
    const s = scores[i];
    for (let a = 0; a < k; a++) {
      for (let b = 0; b < k; b++) {
        meat[a][b] += s[a] * s[b];
      }
    }
  }

  const effectiveLag = Math.min(maxHacLag, Math.max(0, n - 1));
  for (let lag = 1; lag <= effectiveLag; lag++) {
    const weight = 1 - lag / (effectiveLag + 1);
    for (let i = lag; i < n; i++) {
      const sNow = scores[i];
      const sPrev = scores[i - lag];
      for (let a = 0; a < k; a++) {
        for (let b = 0; b < k; b++) {
          meat[a][b] += weight * (sNow[a] * sPrev[b] + sPrev[a] * sNow[b]);
        }
      }
    }
  }

  // Sandwich: (X'X)^-1 * S * (X'X)^-1 with small-sample dof adjustment n / (n - k)
  const dofScale = n > k ? n / (n - k) : 1;
  const temp = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  for (let a = 0; a < k; a++) {
    for (let b = 0; b < k; b++) {
      let s = 0;
      for (let c = 0; c < k; c++) s += xtxInv[a][c] * meat[c][b];
      temp[a][b] = s;
    }
  }

  const cov = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  for (let a = 0; a < k; a++) {
    for (let b = 0; b < k; b++) {
      let s = 0;
      for (let c = 0; c < k; c++) s += temp[a][c] * xtxInv[c][b];
      cov[a][b] = s * dofScale;
    }
  }

  const standardErrors = cov.map((row, idx) => Math.sqrt(Math.max(0, row[idx])));
  return { beta, standardErrors, sse, sst, rSquared };
}

export function runSyntheticLeadLag(params: SyntheticLeadLagParams): LeadLagResult {
  const nTotal = Math.max(80, Math.min(5000, Math.floor(params.observations)));
  const lagSteps = Math.max(1, Math.min(10, Math.floor(params.lagSteps)));
  const maxHacLag = Math.max(0, Math.min(20, Math.floor(params.maxHacLag)));
  const randn = createStandardNormal(params.seed);

  const factor = new Array<number>(nTotal);
  const source = new Array<number>(nTotal);
  const target = new Array<number>(nTotal);

  for (let t = 0; t < nTotal; t++) {
    // Mild AR(1) factor persistence in common_factor scenario so uncontrolled lag looks spurious
    const prevF = t > 0 ? factor[t - 1] : 0;
    factor[t] = (params.scenario === 'common_factor' ? 0.45 * prevF : 0) + randn();
  }

  for (let t = 0; t < nTotal; t++) {
    if (params.scenario === 'null') {
      source[t] = randn();
      target[t] = randn();
    } else if (params.scenario === 'source_leads_target') {
      source[t] = randn();
      const laggedSource = t >= lagSteps ? source[t - lagSteps] : 0;
      target[t] = params.beta * laggedSource + params.commonFactorLoading * factor[t] + randn();
    } else if (params.scenario === 'common_factor') {
      // No causal lead-lag; both load on persistent common factor
      source[t] = params.commonFactorLoading * factor[t] + 0.5 * randn();
      target[t] = params.commonFactorLoading * factor[t] + 0.5 * randn();
    } else {
      // regime_shift: signal active only in first half, zero in second half
      source[t] = randn();
      const activeBeta = t < nTotal / 2 ? params.beta : 0;
      const laggedSource = t >= lagSteps ? source[t - lagSteps] : 0;
      target[t] = activeBeta * laggedSource + randn();
    }
  }

  const XFull: number[][] = [];
  const XReduced: number[][] = [];
  const y: number[] = [];

  for (let t = lagSteps; t < nTotal; t++) {
    const srcLag = source[t - lagSteps];
    const tgtLag = target[t - 1];
    const facNow = factor[t];

    if (params.controlCommonFactor) {
      XFull.push([1, srcLag, tgtLag, facNow]);
      XReduced.push([1, tgtLag, facNow]);
    } else {
      XFull.push([1, srcLag, tgtLag]);
      XReduced.push([1, tgtLag]);
    }
    y.push(target[t]);
  }

  const fullFit = fitOlsHac(XFull, y, maxHacLag);
  const reducedFit = fitOlsHac(XReduced, y, maxHacLag);

  const coef = fullFit.beta[1];
  const se = fullFit.standardErrors[1];
  const tStat = se > 0 ? coef / se : 0;
  const pValue = twoSidedPValueFromZ(tStat);
  const partialRSquared =
    reducedFit.sse > 0 ? Math.max(0, (reducedFit.sse - fullFit.sse) / reducedFit.sse) : 0;
  const incrementalRSquared = Math.max(0, fullFit.rSquared - reducedFit.rSquared);

  // Sample up to 160 evenly spaced points for lightweight scatter plot rendering
  const maxPoints = 160;
  const stride = Math.max(1, Math.floor(y.length / maxPoints));
  const samplePoints: Array<{ x: number; y: number; t: number }> = [];
  for (let i = 0; i < y.length && samplePoints.length < maxPoints; i += stride) {
    samplePoints.push({ x: XFull[i][1], y: y[i], t: i + lagSteps });
  }

  return {
    scenario: params.scenario,
    observations: y.length,
    lagSteps,
    maxHacLag,
    controlCommonFactor: params.controlCommonFactor,
    coefficient: coef,
    standardError: se,
    tStatistic: tStat,
    pValue,
    rSquared: fullFit.rSquared,
    partialRSquared,
    incrementalRSquared,
    samplePoints,
  };
}

/**
 * Institutional Lead-Lag Partial Regression & Newey-West HAC Kernel.
 *
 * Key hardening fixes over legacy prototype:
 *  1. Strictly PIT-safe lagged common-factor control (factor[t - lagSteps]) by default,
 *     eliminating contemporaneous factor lookahead inflation. Includes an explicit audit
 *     comparison against legacy contemporaneous conditioning so lookahead bias can be quantified.
 *  2. Householder QR decomposition replacing fragile Gauss-Jordan inversion, with
 *     numerical condition-number diagnostics.
 *  3. Andrews (1991) data-driven AR(1) plug-in optimal Bartlett HAC bandwidth alongside
 *     manual lag override.
 *  4. Exact finite-sample Student-t inference + deterministic Circular Block-Bootstrap CI.
 *  5. Effective sample size (N_eff) adjusted for residual autocorrelation.
 */

import { twoSidedPValueFromT, twoSidedPValueFromZ } from './normal.ts';

export type SyntheticScenario =
  | 'null'
  | 'source_leads_target'
  | 'common_factor'
  | 'regime_shift'
  | 'heavy_tail_garch';

export type FactorTimingMode = 'pit_lagged' | 'legacy_contemporaneous_leak';

export interface SyntheticLeadLagParams {
  scenario: SyntheticScenario;
  observations: number;
  beta: number;
  commonFactorLoading: number;
  lagSteps: number;
  maxHacLag: number;
  autoBandwidth?: boolean;
  controlCommonFactor: boolean;
  factorTiming?: FactorTimingMode;
  bootstrapResamples?: number;
  bootstrapBlockLength?: number;
  seed: number;
}

export interface LeadLagResult {
  scenario: SyntheticScenario;
  factorTiming: FactorTimingMode;
  observations: number;
  effectiveSampleSize: number;
  lagSteps: number;
  maxHacLag: number;
  andrewsBandwidth: number;
  bandwidthMode: 'andrews_auto' | 'manual';
  controlCommonFactor: boolean;
  coefficient: number;
  standardError: number;
  tStatistic: number;
  degreesOfFreedom: number;
  pValue: number; // Exact finite-sample Student-t p-value
  asymptoticNormalPValue: number;
  bootstrapCiLower: number;
  bootstrapCiUpper: number;
  bootstrapPValue: number;
  conditionNumber: number;
  residualLag1Autocorr: number;
  rSquared: number;
  partialRSquared: number;
  incrementalRSquared: number;
  lookaheadComparison?: {
    pitCoefficient: number;
    pitPartialRSquared: number;
    pitPValue: number;
    leakedCoefficient: number;
    leakedPartialRSquared: number;
    leakedPValue: number;
    partialRSquaredInflationRatio: number;
  };
  samplePoints: Array<{ x: number; y: number; t: number }>;
}

export function createMulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createStandardNormal(seed: number): () => number {
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

/**
 * Householder QR decomposition of an n x k matrix X (n >= k).
 * Returns upper-triangular R (k x k), Q^T y (length k), and R^{-1} for stable (X'X)^{-1} = R^{-1} R^{-T}.
 */
export function qrDecomposeAndSolve(
  X: number[][],
  y: number[],
): {
  beta: number[];
  xtxInv: number[][];
  conditionNumber: number;
} {
  const n = X.length;
  const k = X[0].length;
  if (n < k) {
    throw new Error(`Underdetermined system: observations (${n}) < predictors (${k})`);
  }

  // Copy X into column-major flat arrays for cache-friendly Householder reflections
  const R: Float64Array[] = Array.from({ length: k }, (_, j) => {
    const col = new Float64Array(n);
    for (let i = 0; i < n; i++) col[i] = X[i][j];
    return col;
  });
  const qty = Float64Array.from(y);

  for (let j = 0; j < k; j++) {
    let normSq = 0;
    for (let i = j; i < n; i++) {
      const v = R[j][i];
      normSq += v * v;
    }
    const norm = Math.sqrt(normSq);
    if (norm < 1e-12) {
      throw new Error('Design matrix is rank-deficient or collinear');
    }

    const sign = R[j][j] >= 0 ? 1 : -1;
    const u0 = R[j][j] + sign * norm;
    const v = new Float64Array(n - j);
    v[0] = 1.0;
    let vNormSq = 1.0;
    for (let i = j + 1; i < n; i++) {
      const val = R[j][i] / u0;
      v[i - j] = val;
      vNormSq += val * val;
    }
    const tau = 2.0 / vNormSq;

    // Apply reflection to remaining columns of R
    R[j][j] = -sign * norm;
    for (let i = j + 1; i < n; i++) R[j][i] = 0;

    for (let col = j + 1; col < k; col++) {
      let dot = 0;
      for (let i = j; i < n; i++) dot += v[i - j] * R[col][i];
      const scale = tau * dot;
      for (let i = j; i < n; i++) R[col][i] -= scale * v[i - j];
    }

    // Apply reflection to qty
    let dotY = 0;
    for (let i = j; i < n; i++) dotY += v[i - j] * qty[i];
    const scaleY = tau * dotY;
    for (let i = j; i < n; i++) qty[i] -= scaleY * v[i - j];
  }

  // Extract k x k upper triangular matrix U and estimate condition number from diagonal
  let maxDiag = 0;
  let minDiag = Infinity;
  for (let j = 0; j < k; j++) {
    const absD = Math.abs(R[j][j]);
    if (absD < 1e-12) {
      throw new Error('Design matrix is numerically singular after QR');
    }
    if (absD > maxDiag) maxDiag = absD;
    if (absD < minDiag) minDiag = absD;
  }
  const conditionNumber = maxDiag / minDiag;

  // Back-substitution for beta = U^{-1} (Q^T y)
  const beta = new Array<number>(k).fill(0);
  for (let i = k - 1; i >= 0; i--) {
    let sum = qty[i];
    for (let j = i + 1; j < k; j++) {
      sum -= R[j][i] * beta[j];
    }
    beta[i] = sum / R[i][i];
  }

  // Compute U^{-1} via back-substitution column by column
  const uInv: number[][] = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  for (let col = 0; col < k; col++) {
    for (let i = col; i >= 0; i--) {
      let sum = i === col ? 1.0 : 0.0;
      for (let j = i + 1; j <= col; j++) {
        sum -= R[j][i] * uInv[j][col];
      }
      uInv[i][col] = sum / R[i][i];
    }
  }

  // (X'X)^{-1} = U^{-1} (U^{-1})'
  const xtxInv: number[][] = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  for (let a = 0; a < k; a++) {
    for (let b = 0; b < k; b++) {
      let sum = 0;
      for (let c = Math.max(a, b); c < k; c++) {
        sum += uInv[a][c] * uInv[b][c];
      }
      xtxInv[a][b] = sum;
    }
  }

  return { beta, xtxInv, conditionNumber };
}

/**
 * Andrews (1991) data-driven AR(1) plug-in optimal bandwidth for the Bartlett kernel.
 * Uses score vectors v_{t,j} = x_{t,j} * e_t across non-intercept regressors.
 */
export function computeAndrewsBartlettBandwidth(scores: number[][]): number {
  const n = scores.length;
  const k = scores[0].length;
  if (n < 12) return 1;

  let num = 0;
  let den = 0;
  const startCol = k > 1 ? 1 : 0;

  for (let col = startCol; col < k; col++) {
    let sxx = 0;
    let sxy = 0;
    for (let t = 1; t < n; t++) {
      const prev = scores[t - 1][col];
      const curr = scores[t][col];
      sxx += prev * prev;
      sxy += prev * curr;
    }
    const rho = sxx > 1e-18 ? Math.max(-0.97, Math.min(0.97, sxy / sxx)) : 0;
    let residVar = 0;
    for (let t = 1; t < n; t++) {
      const r = scores[t][col] - rho * scores[t - 1][col];
      residVar += r * r;
    }
    const sigma2 = residVar / Math.max(1, n - 1);
    const denomTerm = Math.pow(1 - rho, 4);
    const numTerm = 4 * rho * rho * sigma2 * sigma2;
    num += numTerm / Math.max(1e-12, denomTerm);
    den += (sigma2 * sigma2) / Math.max(1e-12, denomTerm);
  }

  const alpha1 = den > 1e-18 ? num / den : 0;
  const bandwidth = Math.floor(1.1447 * Math.cbrt(Math.max(0, alpha1) * n));
  return Math.max(1, Math.min(Math.floor(n / 4), Math.max(1, bandwidth)));
}

export function lag1Autocorrelation(series: readonly number[]): number {
  const n = series.length;
  if (n < 3) return 0;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += series[i];
  mean /= n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    const d = series[i] - mean;
    den += d * d;
    if (i > 0) {
      num += d * (series[i - 1] - mean);
    }
  }
  return den > 1e-18 ? Math.max(-0.99, Math.min(0.99, num / den)) : 0;
}

export function fitOlsHac(
  X: number[][],
  y: number[],
  maxHacLag: number,
  autoBandwidth = true,
) {
  const n = y.length;
  const k = X[0].length;
  const { beta, xtxInv, conditionNumber } = qrDecomposeAndSolve(X, y);

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

  const scores: number[][] = new Array(n);
  for (let i = 0; i < n; i++) {
    scores[i] = X[i].map((v) => v * residuals[i]);
  }

  const andrewsBandwidth = computeAndrewsBartlettBandwidth(scores);
  const chosenLag = autoBandwidth ? andrewsBandwidth : maxHacLag;
  const effectiveLag = Math.min(chosenLag, Math.max(0, n - 1));

  // Bartlett HAC meat matrix
  const meat = Array.from({ length: k }, () => new Array<number>(k).fill(0));
  for (let i = 0; i < n; i++) {
    const s = scores[i];
    for (let a = 0; a < k; a++) {
      for (let b = 0; b < k; b++) {
        meat[a][b] += s[a] * s[b];
      }
    }
  }

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

  // Sandwich covariance: (X'X)^-1 * S * (X'X)^-1 with small-sample dof adjustment
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
  const rho1 = lag1Autocorrelation(residuals);
  const neffRatio = (1 - Math.abs(rho1)) / (1 + Math.abs(rho1));
  const effectiveSampleSize = Math.max(k + 1, Math.round(n * neffRatio));

  return {
    beta,
    standardErrors,
    sse,
    sst,
    rSquared,
    andrewsBandwidth,
    effectiveLag,
    conditionNumber,
    residualLag1Autocorr: rho1,
    effectiveSampleSize,
  };
}

/**
 * Deterministic Circular Block-Bootstrap for the primary regression slope beta[1].
 * Preserves serial dependence and heavy tails without Gaussian residual assumptions.
 */
function circularBlockBootstrapBeta1(
  X: number[][],
  y: number[],
  blockLength: number,
  resamples: number,
  seed: number,
): { ciLower: number; ciUpper: number; pValue: number } {
  const n = y.length;
  const B = Math.max(50, Math.min(400, Math.floor(resamples)));
  const L = Math.max(2, Math.min(Math.floor(n / 4), Math.floor(blockLength)));
  const rng = createMulberry32(seed ^ 0x9e3779b9);
  const betas: number[] = [];

  for (let b = 0; b < B; b++) {
    const Xb: number[][] = new Array(n);
    const yb: number[] = new Array(n);
    let idx = 0;
    while (idx < n) {
      const start = Math.floor(rng() * n);
      for (let j = 0; j < L && idx < n; j++) {
        const pos = (start + j) % n;
        Xb[idx] = X[pos];
        yb[idx] = y[pos];
        idx++;
      }
    }
    try {
      const solved = qrDecomposeAndSolve(Xb, yb);
      betas.push(solved.beta[1]);
    } catch {
      // Skip degenerate bootstrap sample
    }
  }

  if (betas.length < 10) {
    return { ciLower: NaN, ciUpper: NaN, pValue: 1.0 };
  }
  betas.sort((a, b) => a - b);
  const loIdx = Math.floor(0.025 * (betas.length - 1));
  const hiIdx = Math.ceil(0.975 * (betas.length - 1));
  const belowZero = betas.filter((v) => v <= 0).length;
  const aboveZero = betas.filter((v) => v >= 0).length;
  const twoSidedP = Math.min(1.0, (2 * Math.min(belowZero, aboveZero) + 1) / (betas.length + 1));

  return {
    ciLower: betas[loIdx],
    ciUpper: betas[hiIdx],
    pValue: twoSidedP,
  };
}

function buildDesignMatrices(
  source: number[],
  target: number[],
  factor: number[],
  lagSteps: number,
  controlCommonFactor: boolean,
  factorTiming: FactorTimingMode,
) {
  const nTotal = source.length;
  const XFull: number[][] = [];
  const XReduced: number[][] = [];
  const y: number[] = [];

  for (let t = lagSteps; t < nTotal; t++) {
    const srcLag = source[t - lagSteps];
    const tgtLag = target[t - 1];
    // PIT-safe: only factor[t - lagSteps] is observable at decision time t - lagSteps!
    // Legacy leak mode deliberately uses factor[t] to quantify lookahead inflation.
    const facControl = factorTiming === 'pit_lagged' ? factor[t - lagSteps] : factor[t];

    if (controlCommonFactor) {
      XFull.push([1, srcLag, tgtLag, facControl]);
      XReduced.push([1, tgtLag, facControl]);
    } else {
      XFull.push([1, srcLag, tgtLag]);
      XReduced.push([1, tgtLag]);
    }
    y.push(target[t]);
  }
  return { XFull, XReduced, y };
}

export function runSyntheticLeadLag(params: SyntheticLeadLagParams): LeadLagResult {
  const nTotal = Math.max(80, Math.min(5000, Math.floor(params.observations)));
  const lagSteps = Math.max(1, Math.min(10, Math.floor(params.lagSteps)));
  const maxHacLag = Math.max(0, Math.min(30, Math.floor(params.maxHacLag)));
  const autoBandwidth = params.autoBandwidth ?? true;
  const factorTiming: FactorTimingMode = params.factorTiming ?? 'pit_lagged';
  const randn = createStandardNormal(params.seed);

  const factor = new Array<number>(nTotal);
  const source = new Array<number>(nTotal);
  const target = new Array<number>(nTotal);

  for (let t = 0; t < nTotal; t++) {
    const prevF = t > 0 ? factor[t - 1] : 0;
    const phi = params.scenario === 'common_factor' ? 0.55 : 0.25;
    factor[t] = phi * prevF + randn();
  }

  // Optional GARCH(1,1) heavy-tail volatility clustering
  let h = 1.0;
  for (let t = 0; t < nTotal; t++) {
    if (params.scenario === 'null') {
      source[t] = randn();
      target[t] = randn();
    } else if (params.scenario === 'source_leads_target') {
      source[t] = randn();
      const laggedSource = t >= lagSteps ? source[t - lagSteps] : 0;
      target[t] = params.beta * laggedSource + params.commonFactorLoading * factor[t] + randn();
    } else if (params.scenario === 'common_factor') {
      // No causal lead-lag; both load contemporaneously on persistent AR(1) factor
      source[t] = params.commonFactorLoading * factor[t] + 0.5 * randn();
      target[t] = params.commonFactorLoading * factor[t] + 0.5 * randn();
    } else if (params.scenario === 'heavy_tail_garch') {
      const z1 = randn();
      const z2 = randn();
      // Student-t-like heavy tail via chi-square scale mixture
      const w = Math.sqrt(4 / (randn() ** 2 + randn() ** 2 + randn() ** 2 + randn() ** 2 + 0.5));
      const shock = Math.sqrt(h) * z2 * w;
      h = 0.08 + 0.14 * Math.min(25, shock * shock) + 0.78 * h;
      source[t] = z1 * Math.sqrt(h);
      const laggedSource = t >= lagSteps ? source[t - lagSteps] : 0;
      target[t] = params.beta * laggedSource + shock;
    } else {
      // regime_shift: signal active only in first half, zero in second half
      source[t] = randn();
      const activeBeta = t < nTotal / 2 ? params.beta : 0;
      const laggedSource = t >= lagSteps ? source[t - lagSteps] : 0;
      target[t] = activeBeta * laggedSource + randn();
    }
  }

  const { XFull, XReduced, y } = buildDesignMatrices(
    source,
    target,
    factor,
    lagSteps,
    params.controlCommonFactor,
    factorTiming,
  );

  const fullFit = fitOlsHac(XFull, y, maxHacLag, autoBandwidth);
  const reducedFit = fitOlsHac(XReduced, y, maxHacLag, autoBandwidth);

  const coef = fullFit.beta[1];
  const se = fullFit.standardErrors[1];
  const tStat = se > 0 ? coef / se : 0;
  const df = Math.max(1, y.length - XFull[0].length);
  const pValue = twoSidedPValueFromT(tStat, df);
  const asymptoticNormalPValue = twoSidedPValueFromZ(tStat);
  const partialRSquared =
    reducedFit.sse > 0 ? Math.max(0, (reducedFit.sse - fullFit.sse) / reducedFit.sse) : 0;
  const incrementalRSquared = Math.max(0, fullFit.rSquared - reducedFit.rSquared);

  const boot = circularBlockBootstrapBeta1(
    XFull,
    y,
    params.bootstrapBlockLength ?? 10,
    params.bootstrapResamples ?? 160,
    params.seed,
  );

  // When common factor control is enabled, compute explicit PIT vs Contemporaneous-Leak audit diff
  let lookaheadComparison: LeadLagResult['lookaheadComparison'];
  if (params.controlCommonFactor) {
    const pitMats = buildDesignMatrices(source, target, factor, lagSteps, true, 'pit_lagged');
    const leakMats = buildDesignMatrices(
      source,
      target,
      factor,
      lagSteps,
      true,
      'legacy_contemporaneous_leak',
    );
    const pitFull = fitOlsHac(pitMats.XFull, pitMats.y, maxHacLag, autoBandwidth);
    const pitRed = fitOlsHac(pitMats.XReduced, pitMats.y, maxHacLag, autoBandwidth);
    const leakFull = fitOlsHac(leakMats.XFull, leakMats.y, maxHacLag, autoBandwidth);
    const leakRed = fitOlsHac(leakMats.XReduced, leakMats.y, maxHacLag, autoBandwidth);

    const pitPR2 = pitRed.sse > 0 ? Math.max(0, (pitRed.sse - pitFull.sse) / pitRed.sse) : 0;
    const leakPR2 = leakRed.sse > 0 ? Math.max(0, (leakRed.sse - leakFull.sse) / leakRed.sse) : 0;
    const pitT = pitFull.standardErrors[1] > 0 ? pitFull.beta[1] / pitFull.standardErrors[1] : 0;
    const leakT =
      leakFull.standardErrors[1] > 0 ? leakFull.beta[1] / leakFull.standardErrors[1] : 0;
    const auditDf = Math.max(1, pitMats.y.length - 4);

    lookaheadComparison = {
      pitCoefficient: pitFull.beta[1],
      pitPartialRSquared: pitPR2,
      pitPValue: twoSidedPValueFromT(pitT, auditDf),
      leakedCoefficient: leakFull.beta[1],
      leakedPartialRSquared: leakPR2,
      leakedPValue: twoSidedPValueFromT(leakT, auditDf),
      partialRSquaredInflationRatio: pitPR2 > 1e-12 ? leakPR2 / pitPR2 : leakPR2 > 0 ? Infinity : 1,
    };
  }

  const maxPoints = 160;
  const stride = Math.max(1, Math.floor(y.length / maxPoints));
  const samplePoints: Array<{ x: number; y: number; t: number }> = [];
  for (let i = 0; i < y.length && samplePoints.length < maxPoints; i += stride) {
    samplePoints.push({ x: XFull[i][1], y: y[i], t: i + lagSteps });
  }

  return {
    scenario: params.scenario,
    factorTiming,
    observations: y.length,
    effectiveSampleSize: fullFit.effectiveSampleSize,
    lagSteps,
    maxHacLag: fullFit.effectiveLag,
    andrewsBandwidth: fullFit.andrewsBandwidth,
    bandwidthMode: autoBandwidth ? 'andrews_auto' : 'manual',
    controlCommonFactor: params.controlCommonFactor,
    coefficient: coef,
    standardError: se,
    tStatistic: tStat,
    degreesOfFreedom: df,
    pValue,
    asymptoticNormalPValue,
    bootstrapCiLower: boot.ciLower,
    bootstrapCiUpper: boot.ciUpper,
    bootstrapPValue: boot.pValue,
    conditionNumber: fullFit.conditionNumber,
    residualLag1Autocorr: fullFit.residualLag1Autocorr,
    rSquared: fullFit.rSquared,
    partialRSquared,
    incrementalRSquared,
    lookaheadComparison,
    samplePoints,
  };
}

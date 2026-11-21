/**
 * Institutional Portfolio Construction & Dynamic Transaction-Cost-Aware Optimization:
 *  1. Ledoit-Wolf (2004) analytical shrinkage covariance toward scaled identity.
 *  2. Garleanu-Pedersen (2013) style Multi-Asset Convex Quadratic Program with:
 *       max_w  alpha' w - (gamma / 2) w' Sigma w - c_tc' |w - w_prev| - (lambda / 2) ||w - w_prev||^2
 *     solved deterministically via Proximal Coordinate Descent with exact L1 soft-thresholding
 *     (creating a mathematically optimal No-Trade Zone that slashes wasteful turnover),
 *     box limits, gross leverage cap, net exposure bound, and ex-ante Volatility Targeting.
 *  3. Head-to-head benchmark against MyQuant's legacy 100% Sign-Rule cost gate.
 */

import { createStandardNormal } from './leadLag.ts';

export interface LedoitWolfResult {
  covariance: number[][];
  sampleCovariance: number[][];
  shrinkageIntensity: number; // delta* in [0, 1]
  targetVariance: number;
}

export interface PortfolioOptimizerConfig {
  riskAversion: number; // gamma (default 4.0)
  linearCostBps: number; // per-unit turnover cost c_tc in bps (fee + half-spread)
  quadraticImpactBps: number; // quadratic market impact penalty lambda in bps
  maxPositionWeight: number; // single-asset abs cap, e.g. 0.5
  maxGrossLeverage: number; // sum |w_i| <= L_max, e.g. 1.5
  maxNetExposure: number; // |sum w_i| <= N_max, e.g. 1.0
  targetAnnualVol: number; // e.g. 0.12 (12% annualized vol target)
  periodsPerYear?: number;
}

export interface PortfolioOptimizationOutput {
  weights: number[];
  rawUnconstrainedWeights: number[];
  turnover: number; // sum |w_i - w_prev_i|
  exAnteAnnualVol: number;
  volScaleFactor: number;
  expectedAlphaBps: number;
  expectedLinearCostBps: number;
  expectedNetAlphaBps: number;
  grossLeverage: number;
  netExposure: number;
  assetsInNoTradeZone: number;
}

export interface SignVsQpComparison {
  assets: string[];
  periods: number;
  shrinkageIntensity: number;
  signRule: {
    netSharpe: number;
    grossSharpe: number;
    totalNetReturnPct: number;
    annualizedVolPct: number;
    maxDrawdownPct: number;
    averageDailyTurnover: number;
    totalFlipCount: number;
    totalCostDragPct: number;
    equityCurve: number[];
  };
  qpOptimized: {
    netSharpe: number;
    grossSharpe: number;
    totalNetReturnPct: number;
    annualizedVolPct: number;
    maxDrawdownPct: number;
    averageDailyTurnover: number;
    noTradeHoldRatePct: number;
    totalCostDragPct: number;
    finalWeights: number[];
    equityCurve: number[];
  };
  turnoverReductionPct: number;
  sharpeImprovement: number;
}

/**
 * Analytical Ledoit-Wolf (2004) optimal shrinkage of sample covariance toward mu * I.
 * Input: returnsMatrix[t][i] (T observations x N assets).
 */
export function ledoitWolfCovariance(returnsMatrix: readonly (readonly number[])[]): LedoitWolfResult {
  const T = returnsMatrix.length;
  if (T < 5) {
    throw new Error('Ledoit-Wolf covariance requires at least 5 observations');
  }
  const N = returnsMatrix[0].length;
  if (N < 1) {
    throw new Error('At least 1 asset required');
  }

  const means = new Array<number>(N).fill(0);
  for (let t = 0; t < T; t++) {
    for (let i = 0; i < N; i++) means[i] += returnsMatrix[t][i];
  }
  for (let i = 0; i < N; i++) means[i] /= T;

  const centered: number[][] = Array.from({ length: T }, (_, t) =>
    Array.from({ length: N }, (_, i) => returnsMatrix[t][i] - means[i]),
  );

  // Sample covariance S = (1 / T) X' X
  const S: number[][] = Array.from({ length: N }, () => new Array<number>(N).fill(0));
  for (let t = 0; t < T; t++) {
    const row = centered[t];
    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        S[i][j] += row[i] * row[j];
      }
    }
  }
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) S[i][j] /= T;
  }

  // Target: mu * I where mu = trace(S) / N
  let trace = 0;
  for (let i = 0; i < N; i++) trace += S[i][i];
  const mu = trace / N;

  // d^2 = ||S - mu*I||_F^2 / N
  let d2 = 0;
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      const diff = S[i][j] - (i === j ? mu : 0);
      d2 += diff * diff;
    }
  }
  d2 /= N;

  // b_bar^2 = (1 / T^2) sum_t ||x_t x_t' - S||_F^2 / N
  let bBar2 = 0;
  for (let t = 0; t < T; t++) {
    const row = centered[t];
    let normSq = 0;
    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        const diff = row[i] * row[j] - S[i][j];
        normSq += diff * diff;
      }
    }
    bBar2 += normSq / N;
  }
  bBar2 /= T * T;

  const b2 = Math.min(bBar2, d2);
  const delta = d2 > 1e-18 ? Math.max(0, Math.min(1, b2 / d2)) : 1.0;

  // Shrunk covariance: (1 - delta) * S + delta * mu * I
  const shrunk: number[][] = Array.from({ length: N }, (_, i) =>
    Array.from({ length: N }, (_, j) => (1 - delta) * S[i][j] + (i === j ? delta * mu : 0)),
  );

  return {
    covariance: shrunk,
    sampleCovariance: S,
    shrinkageIntensity: delta,
    targetVariance: mu,
  };
}

function softThreshold(x: number, threshold: number): number {
  if (x > threshold) return x - threshold;
  if (x < -threshold) return x + threshold;
  return 0;
}

function portfolioVariance(weights: readonly number[], cov: readonly (readonly number[])[]): number {
  const N = weights.length;
  let v = 0;
  for (let i = 0; i < N; i++) {
    let rowSum = 0;
    for (let j = 0; j < N; j++) rowSum += cov[i][j] * weights[j];
    v += weights[i] * rowSum;
  }
  return Math.max(0, v);
}

/**
 * Solves the Transaction-Cost-Aware Convex Portfolio QP via Proximal Coordinate Descent.
 * Soft-thresholding on delta_w = w - w_prev produces an exact No-Trade Zone around w_prev.
 */
export function optimizePortfolioQP(
  expectedReturns: readonly number[], // per-period expected returns (decimals, e.g. 0.001 = 10 bps)
  covariance: readonly (readonly number[])[],
  prevWeights: readonly number[],
  config: PortfolioOptimizerConfig,
): PortfolioOptimizationOutput {
  const N = expectedReturns.length;
  const gamma = Math.max(1e-4, config.riskAversion);
  const cLinear = Math.max(0, config.linearCostBps) / 10_000;
  const cQuad = Math.max(0, config.quadraticImpactBps) / 10_000;
  const periodsPerYear = config.periodsPerYear ?? 252;

  // Unconstrained baseline for diagnostic comparison
  const rawW = new Array<number>(N);
  for (let i = 0; i < N; i++) {
    const diagVar = Math.max(1e-8, covariance[i][i]);
    rawW[i] = expectedReturns[i] / (gamma * diagVar);
  }

  // Coordinate descent on delta_w_i = w_i - w_prev_i
  const w = [...prevWeights];
  const maxIter = 80;
  for (let iter = 0; iter < maxIter; iter++) {
    let maxChange = 0;
    for (let i = 0; i < N; i++) {
      // Partial derivative of smooth objective w.r.t. w_i evaluated at w_i = prevWeights[i]:
      // g_i = alpha_i - gamma * sum_{j != i} Sigma_{ij} w_j - gamma * Sigma_{ii} * prev_i
      let crossRisk = 0;
      for (let j = 0; j < N; j++) {
        if (j !== i) crossRisk += covariance[i][j] * w[j];
      }
      const denom = gamma * Math.max(1e-9, covariance[i][i]) + cQuad;
      const numAtPrev = expectedReturns[i] - gamma * crossRisk - gamma * covariance[i][i] * prevWeights[i];

      // Exact proximal step for L1 penalty cLinear * |delta_i|
      const deltaI = softThreshold(numAtPrev, cLinear) / denom;
      let nextWi = prevWeights[i] + deltaI;

      // Box constraint |w_i| <= maxPositionWeight
      nextWi = Math.max(-config.maxPositionWeight, Math.min(config.maxPositionWeight, nextWi));

      const diff = Math.abs(nextWi - w[i]);
      if (diff > maxChange) maxChange = diff;
      w[i] = nextWi;
    }
    if (maxChange < 1e-8) break;
  }

  // Project onto gross leverage constraint sum |w_i| <= maxGrossLeverage
  let gross = w.reduce((acc, v) => acc + Math.abs(v), 0);
  if (gross > config.maxGrossLeverage && gross > 1e-12) {
    const scale = config.maxGrossLeverage / gross;
    for (let i = 0; i < N; i++) w[i] *= scale;
    gross = config.maxGrossLeverage;
  }

  // Soft-enforce net exposure constraint |sum w_i| <= maxNetExposure
  let net = w.reduce((acc, v) => acc + v, 0);
  if (Math.abs(net) > config.maxNetExposure) {
    const excess = net - Math.sign(net) * config.maxNetExposure;
    const shift = excess / N;
    for (let i = 0; i < N; i++) {
      w[i] = Math.max(-config.maxPositionWeight, Math.min(config.maxPositionWeight, w[i] - shift));
    }
  }

  // Ex-ante Volatility Targeting: scale down if annualized vol exceeds targetAnnualVol
  const rawAnnualVol = Math.sqrt(portfolioVariance(w, covariance) * periodsPerYear);
  let volScaleFactor = 1.0;
  if (config.targetAnnualVol > 0 && rawAnnualVol > config.targetAnnualVol) {
    volScaleFactor = config.targetAnnualVol / rawAnnualVol;
    for (let i = 0; i < N; i++) w[i] *= volScaleFactor;
  }

  const finalAnnualVol = Math.sqrt(portfolioVariance(w, covariance) * periodsPerYear);
  let turnover = 0;
  let assetsInNoTradeZone = 0;
  let expectedAlpha = 0;
  gross = 0;
  net = 0;
  for (let i = 0; i < N; i++) {
    const dw = Math.abs(w[i] - prevWeights[i]);
    turnover += dw;
    if (dw < 1e-6) assetsInNoTradeZone++;
    expectedAlpha += expectedReturns[i] * w[i];
    gross += Math.abs(w[i]);
    net += w[i];
  }
  const linearCost = cLinear * turnover;

  return {
    weights: w,
    rawUnconstrainedWeights: rawW,
    turnover,
    exAnteAnnualVol: finalAnnualVol,
    volScaleFactor,
    expectedAlphaBps: expectedAlpha * 10_000,
    expectedLinearCostBps: linearCost * 10_000,
    expectedNetAlphaBps: (expectedAlpha - linearCost) * 10_000,
    grossLeverage: gross,
    netExposure: net,
    assetsInNoTradeZone,
  };
}

function summarizeSeries(netReturns: number[], grossReturns: number[], periodsPerYear = 252) {
  const T = netReturns.length;
  const meanNet = netReturns.reduce((a, b) => a + b, 0) / Math.max(1, T);
  const meanGross = grossReturns.reduce((a, b) => a + b, 0) / Math.max(1, T);
  const varNet =
    netReturns.reduce((a, r) => a + (r - meanNet) ** 2, 0) / Math.max(1, T - 1);
  const varGross =
    grossReturns.reduce((a, r) => a + (r - meanGross) ** 2, 0) / Math.max(1, T - 1);
  const stdNet = Math.sqrt(Math.max(1e-14, varNet));
  const stdGross = Math.sqrt(Math.max(1e-14, varGross));

  const equityCurve: number[] = [];
  let eq = 1.0;
  let peak = 1.0;
  let maxDd = 0;
  for (let t = 0; t < T; t++) {
    eq *= 1 + netReturns[t];
    if (eq > peak) peak = eq;
    const dd = (peak - eq) / peak;
    if (dd > maxDd) maxDd = dd;
    equityCurve.push(eq);
  }

  return {
    netSharpe: (meanNet / stdNet) * Math.sqrt(periodsPerYear),
    grossSharpe: (meanGross / stdGross) * Math.sqrt(periodsPerYear),
    totalNetReturnPct: (eq - 1) * 100,
    annualizedVolPct: stdNet * Math.sqrt(periodsPerYear) * 100,
    maxDrawdownPct: maxDd * 100,
    equityCurve,
  };
}

/**
 * Deterministic head-to-head comparison: Legacy 100% Sign Rule vs Garleanu-Pedersen QP + Vol-Targeting
 * on a realistic 3-asset (BTC / ETH / SOL) correlated noisy-alpha panel.
 */
export function compareSignRuleVsQP(params: {
  periods?: number;
  signalStrength?: number; // IC-like signal-to-noise ratio (default 0.08)
  linearCostBps?: number; // default 7.5 bps (5 bps taker + 1.5 bps half-spread + 1 bp slip)
  riskAversion?: number;
  targetAnnualVol?: number;
  seed?: number;
}): SignVsQpComparison {
  const assets = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP'];
  const N = assets.length;
  const T = Math.max(120, Math.min(1000, Math.floor(params.periods ?? 360)));
  const signalStrength = params.signalStrength ?? 0.09;
  const linearCostBps = params.linearCostBps ?? 7.5;
  const riskAversion = params.riskAversion ?? 5.0;
  const targetAnnualVol = params.targetAnnualVol ?? 0.16;
  const randn = createStandardNormal(params.seed ?? 2026);

  // Correlated multi-asset returns + realistic noisy alpha forecasts (with persistence + noise flips)
  const assetVols = [0.026, 0.034, 0.048];
  const returns: number[][] = [];
  const alphas: number[][] = [];
  const latentSignal = new Array<number>(N).fill(0);

  for (let t = 0; t < T; t++) {
    const commonShock = randn();
    const rowRet = new Array<number>(N);
    const rowAlpha = new Array<number>(N);
    for (let i = 0; i < N; i++) {
      // Mildly persistent true expected return (half-life ~5 days)
      latentSignal[i] = 0.85 * latentSignal[i] + 0.52 * randn();
      const trueMu = signalStrength * assetVols[i] * latentSignal[i] * 0.25;
      // Observed noisy forecast: true alpha + estimation noise that causes frequent sign flips!
      rowAlpha[i] = trueMu + randn() * assetVols[i] * 0.045;
      // Realized next-period return
      const idio = randn();
      const corrLoad = i === 0 ? 0.8 : i === 1 ? 0.85 : 0.75;
      rowRet[i] =
        trueMu + assetVols[i] * (corrLoad * commonShock + Math.sqrt(1 - corrLoad * corrLoad) * idio);
    }
    returns.push(rowRet);
    alphas.push(rowAlpha);
  }

  const warmup = 60;
  const lwInit = ledoitWolfCovariance(returns.slice(0, warmup));

  let prevSignW = new Array<number>(N).fill(0);
  let prevQpW = new Array<number>(N).fill(0);
  const signNet: number[] = [];
  const signGross: number[] = [];
  const qpNet: number[] = [];
  const qpGross: number[] = [];
  let signTurnoverSum = 0;
  let qpTurnoverSum = 0;
  let signFlips = 0;
  let noTradeCount = 0;
  let signCostDrag = 0;
  let qpCostDrag = 0;

  const costRate = linearCostBps / 10_000;
  const qpConfig: PortfolioOptimizerConfig = {
    riskAversion,
    linearCostBps,
    quadraticImpactBps: 2.0,
    maxPositionWeight: 0.6,
    maxGrossLeverage: 1.5,
    maxNetExposure: 1.0,
    targetAnnualVol,
    periodsPerYear: 365,
  };

  let latestLw = lwInit;

  for (let t = warmup; t < T; t++) {
    // Re-estimate Ledoit-Wolf covariance every 15 bars strictly on past window [t-60, t)
    if ((t - warmup) % 15 === 0) {
      latestLw = ledoitWolfCovariance(returns.slice(t - warmup, t));
    }

    // 1. Legacy 100% Sign Rule (equal-weight gross 1.0 across assets by sign(alpha))
    const signW = alphas[t].map((a) => (a >= 0 ? 1 / N : -1 / N));
    let sTurn = 0;
    for (let i = 0; i < N; i++) {
      if (prevSignW[i] !== 0 && Math.sign(signW[i]) !== Math.sign(prevSignW[i])) {
        signFlips++;
      }
      sTurn += Math.abs(signW[i] - prevSignW[i]);
    }
    const sGross = signW.reduce((acc, w, i) => acc + w * returns[t][i], 0);
    const sCost = sTurn * costRate;
    signGross.push(sGross);
    signNet.push(sGross - sCost);
    signTurnoverSum += sTurn;
    signCostDrag += sCost;
    prevSignW = signW;

    // 2. Garleanu-Pedersen QP + Ledoit-Wolf + Vol-Targeting
    const opt = optimizePortfolioQP(alphas[t], latestLw.covariance, prevQpW, qpConfig);
    const qGross = opt.weights.reduce((acc, w, i) => acc + w * returns[t][i], 0);
    const qCost = opt.turnover * costRate;
    qpGross.push(qGross);
    qpNet.push(qGross - qCost);
    qpTurnoverSum += opt.turnover;
    qpCostDrag += qCost;
    noTradeCount += opt.assetsInNoTradeZone;
    prevQpW = opt.weights;
  }

  const evalPeriods = T - warmup;
  const signStats = summarizeSeries(signNet, signGross, 365);
  const qpStats = summarizeSeries(qpNet, qpGross, 365);

  const avgSignTurnover = signTurnoverSum / evalPeriods;
  const avgQpTurnover = qpTurnoverSum / evalPeriods;
  const turnoverReductionPct =
    avgSignTurnover > 1e-12 ? ((avgSignTurnover - avgQpTurnover) / avgSignTurnover) * 100 : 0;

  return {
    assets,
    periods: evalPeriods,
    shrinkageIntensity: latestLw.shrinkageIntensity,
    signRule: {
      ...signStats,
      averageDailyTurnover: avgSignTurnover,
      totalFlipCount: signFlips,
      totalCostDragPct: signCostDrag * 100,
    },
    qpOptimized: {
      ...qpStats,
      averageDailyTurnover: avgQpTurnover,
      noTradeHoldRatePct: (noTradeCount / (evalPeriods * N)) * 100,
      totalCostDragPct: qpCostDrag * 100,
      finalWeights: prevQpW,
    },
    turnoverReductionPct,
    sharpeImprovement: qpStats.netSharpe - signStats.netSharpe,
  };
}

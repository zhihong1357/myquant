/**
 * Institutional Purged & Embargoed Walk-Forward Validation, Regime Stress Attribution,
 * and 6-Gate Quantitative Release Scorecard (Marcos Lopez de Prado, AFML Ch. 7).
 *
 * Strictly paper-only deterministic validation kernel.
 */

import {
  runUnifiedStrategyPipeline,
  STRATEGY_CATALOG,
  type StrategyId,
} from '../engine/unifiedPipeline.ts';
import type { IncrementalMerkleLedger } from '../engine/merkleLedger.ts';
import { computeDeflatedSharpeRatio } from './overfitting.ts';

export interface WalkForwardFold {
  foldIndex: number;
  trainStart: number;
  trainEnd: number; // exclusive
  purgeStart: number;
  purgeEnd: number; // exclusive — zero overlap with train or test!
  testStart: number;
  testEnd: number; // exclusive
  embargoEnd: number;
  isSharpe: number;
  oosSharpe: number;
  oosReturnPct: number;
  oosMaxDrawdownPct: number;
  oosPositive: boolean;
}

export interface RegimeAttributionRow {
  regime: 'calm_trend' | 'normal_chop' | 'high_vol_stress';
  observations: number;
  sharePct: number;
  annualizedReturnPct: number;
  annualizedVolPct: number;
  sharpe: number;
  maxDrawdownPct: number;
}

export interface InstitutionalGateCheck {
  id: string;
  passed: boolean;
  severity: 'pass' | 'warn' | 'fail';
  observedText: string;
  thresholdText: string;
}

export interface WalkForwardReport {
  strategyId: StrategyId;
  strategyName: string;
  optimizerMode: 'qp_optimized' | 'legacy_sign_rule';
  totalObservations: number;
  purgeGapBars: number;
  embargoBars: number;
  folds: WalkForwardFold[];
  meanIsSharpe: number;
  meanOosSharpe: number;
  oosRetentionRatio: number; // meanOosSharpe / max(0.05, meanIsSharpe)
  oosProfitableFoldRatePct: number;
  overallNetSharpe: number;
  overallMaxDrawdownPct: number;
  overallTotalReturnPct: number;
  avgDailyTurnoverPct: number;
  totalCostDragPct: number;
  deflatedSharpeRatio: number;
  liquidated: boolean;
  regimes: RegimeAttributionRow[];
  healthScore: number; // 0-100 composite institutional readiness score
  releaseVerdict: 'paper_ready' | 'needs_tuning' | 'rejected';
  gates: InstitutionalGateCheck[];
}

export interface ArenaCompetitorSummary {
  rank: number;
  label: string;
  strategyId: StrategyId;
  optimizerMode: 'qp_optimized' | 'legacy_sign_rule';
  healthScore: number;
  releaseVerdict: 'paper_ready' | 'needs_tuning' | 'rejected';
  overallNetSharpe: number;
  meanOosSharpe: number;
  oosRetentionRatio: number;
  overallMaxDrawdownPct: number;
  avgDailyTurnoverPct: number;
  totalCostDragPct: number;
  deflatedSharpeRatio: number;
  liquidated: boolean;
  equityCurve: number[];
}

export interface StrategyArenaReport {
  generatedAtIso: string;
  periods: number;
  targetAnnualVol: number;
  maxLeverage: number;
  linearCostBps: number;
  competitors: ArenaCompetitorSummary[];
  winnerId: string;
}

function seriesStats(returns: readonly number[], periodsPerYear: number) {
  const n = returns.length;
  if (n < 2) {
    return { sharpe: 0, totalReturnPct: 0, annReturnPct: 0, annVolPct: 0, maxDrawdownPct: 0 };
  }
  let mean = 0;
  for (let i = 0; i < n; i++) mean += returns[i];
  mean /= n;

  let ss = 0;
  for (let i = 0; i < n; i++) {
    const d = returns[i] - mean;
    ss += d * d;
  }
  const std = Math.sqrt(Math.max(1e-14, ss / (n - 1)));
  const sharpe = (mean / std) * Math.sqrt(periodsPerYear);

  let eq = 1.0;
  let peak = 1.0;
  let maxDd = 0;
  for (let i = 0; i < n; i++) {
    eq *= Math.max(0.01, 1 + returns[i]);
    if (eq > peak) peak = eq;
    const dd = (peak - eq) / peak;
    if (dd > maxDd) maxDd = dd;
  }

  return {
    sharpe,
    totalReturnPct: (eq - 1) * 100,
    annReturnPct: mean * periodsPerYear * 100,
    annVolPct: std * Math.sqrt(periodsPerYear) * 100,
    maxDrawdownPct: maxDd * 100,
  };
}

/**
 * Evaluates a strategy using chronological Purged & Embargoed Walk-Forward folds,
 * splits realized returns into volatility regimes, and computes a deterministic 6-gate scorecard.
 */
export function runPurgedWalkForwardAudit(
  params: {
    strategyId: StrategyId;
    optimizerMode: 'qp_optimized' | 'legacy_sign_rule';
    periods?: number;
    numFolds?: number;
    purgeGapBars?: number;
    embargoBars?: number;
    targetAnnualVol?: number;
    maxLeverage?: number;
    linearCostBps?: number;
    seed?: number;
  },
  ledger?: IncrementalMerkleLedger,
): WalkForwardReport {
  const periods = Math.max(180, Math.min(600, Math.floor(params.periods ?? 300)));
  const numFolds = Math.max(3, Math.min(6, Math.floor(params.numFolds ?? 5)));
  const purgeGapBars = Math.max(2, Math.min(15, Math.floor(params.purgeGapBars ?? 6)));
  const embargoBars = Math.max(1, Math.min(10, Math.floor(params.embargoBars ?? 4)));
  const periodsPerYear = params.strategyId === 'perp_carry_funding' ? 365 * 3 : 365;

  // Execute unified deterministic pipeline (non-mutating by default for audit)
  const run = runUnifiedStrategyPipeline(
    {
      strategyId: params.strategyId,
      optimizerMode: params.optimizerMode,
      periods,
      targetAnnualVol: params.targetAnnualVol ?? 0.14,
      maxLeverage: params.maxLeverage ?? 2.0,
      linearCostBps: params.linearCostBps ?? 6.5,
      seed: params.seed ?? 2026,
      persistToLedger: false,
    },
    ledger,
  );

  // Reconstruct per-step net returns from equity curve
  const netReturns: number[] = [];
  let prevEq = 100_000;
  for (const pt of run.equityCurve) {
    const r = prevEq > 1e-6 ? (pt.equity - prevEq) / prevEq : 0;
    netReturns.push(r);
    prevEq = pt.equity;
  }

  const T = netReturns.length;
  // Build strictly purged chronological expanding-window walk-forward folds
  const minTrain = Math.max(60, Math.floor(T * 0.35));
  const remaining = Math.max(numFolds * 12, T - minTrain);
  const testLen = Math.max(10, Math.floor((remaining - numFolds * purgeGapBars) / numFolds));

  const folds: WalkForwardFold[] = [];
  for (let f = 0; f < numFolds; f++) {
    const testStart = minTrain + f * (testLen + purgeGapBars);
    const testEnd = Math.min(T, testStart + testLen);
    const trainEnd = Math.max(20, testStart - purgeGapBars);
    if (testEnd - testStart < 8 || trainEnd < 20) break;

    const trainSlice = netReturns.slice(0, trainEnd);
    const testSlice = netReturns.slice(testStart, testEnd);
    const isStats = seriesStats(trainSlice, periodsPerYear);
    const oosStats = seriesStats(testSlice, periodsPerYear);

    folds.push({
      foldIndex: f + 1,
      trainStart: 0,
      trainEnd,
      purgeStart: trainEnd,
      purgeEnd: testStart,
      testStart,
      testEnd,
      embargoEnd: Math.min(T, testEnd + embargoBars),
      isSharpe: isStats.sharpe,
      oosSharpe: oosStats.sharpe,
      oosReturnPct: oosStats.totalReturnPct,
      oosMaxDrawdownPct: oosStats.maxDrawdownPct,
      oosPositive: oosStats.sharpe > 0,
    });
  }

  const meanIsSharpe =
    folds.reduce((a, f) => a + f.isSharpe, 0) / Math.max(1, folds.length);
  const meanOosSharpe =
    folds.reduce((a, f) => a + f.oosSharpe, 0) / Math.max(1, folds.length);
  const oosRetentionRatio =
    meanIsSharpe > 0.1
      ? Math.max(-1, Math.min(2.0, meanOosSharpe / meanIsSharpe))
      : meanOosSharpe > 0
        ? 1.0
        : 0;
  const oosProfitableFoldRatePct =
    (folds.filter((f) => f.oosPositive).length / Math.max(1, folds.length)) * 100;

  // Rolling 15-bar realized volatility regime classification (Calm / Normal / High-Vol Stress)
  const rollingVols: number[] = [];
  for (let i = 0; i < T; i++) {
    const start = Math.max(0, i - 14);
    const window = netReturns.slice(start, i + 1);
    const st = seriesStats(window, periodsPerYear);
    rollingVols.push(st.annVolPct);
  }
  const sortedVols = [...rollingVols].sort((a, b) => a - b);
  const q33 = sortedVols[Math.floor(sortedVols.length * 0.33)] ?? 10;
  const q75 = sortedVols[Math.floor(sortedVols.length * 0.75)] ?? 20;

  const calmReturns: number[] = [];
  const normalReturns: number[] = [];
  const stressReturns: number[] = [];
  for (let i = 0; i < T; i++) {
    if (rollingVols[i] <= q33) calmReturns.push(netReturns[i]);
    else if (rollingVols[i] >= q75) stressReturns.push(netReturns[i]);
    else normalReturns.push(netReturns[i]);
  }

  const buildRegimeRow = (
    regime: RegimeAttributionRow['regime'],
    arr: number[],
  ): RegimeAttributionRow => {
    const st = seriesStats(arr, periodsPerYear);
    return {
      regime,
      observations: arr.length,
      sharePct: (arr.length / Math.max(1, T)) * 100,
      annualizedReturnPct: st.annReturnPct,
      annualizedVolPct: st.annVolPct,
      sharpe: st.sharpe,
      maxDrawdownPct: st.maxDrawdownPct,
    };
  };

  const regimes: RegimeAttributionRow[] = [
    buildRegimeRow('calm_trend', calmReturns),
    buildRegimeRow('normal_chop', normalReturns),
    buildRegimeRow('high_vol_stress', stressReturns),
  ];
  const stressDd = regimes[2].maxDrawdownPct;

  const dsr = computeDeflatedSharpeRatio({
    returns: netReturns,
    numTrials: Math.max(3, ledger ? ledger.getEntries().length : 4),
    periodsPerYear,
  }).deflatedSharpeRatio;

  // Deterministic 6-Gate Institutional Release Checklist
  const gates: InstitutionalGateCheck[] = [
    {
      id: 'liquidation_survival',
      passed: !run.metrics.liquidated,
      severity: run.metrics.liquidated ? 'fail' : 'pass',
      observedText: run.metrics.liquidated
        ? `Liquidated @ step ${run.metrics.liquidationStep}`
        : 'Survived all intraday wicks',
      thresholdText: '0 forced liquidations',
    },
    {
      id: 'oos_decay_guard',
      passed: meanOosSharpe >= 0.4 && oosRetentionRatio >= 0.5,
      severity:
        meanOosSharpe >= 0.4 && oosRetentionRatio >= 0.5
          ? 'pass'
          : meanOosSharpe > 0
            ? 'warn'
            : 'fail',
      observedText: `OOS SR ${meanOosSharpe.toFixed(2)} (${(oosRetentionRatio * 100).toFixed(0)}% retention)`,
      thresholdText: 'OOS SR >= 0.40 & Retention >= 50%',
    },
    {
      id: 'deflated_sharpe',
      passed: dsr >= 0.75,
      severity: dsr >= 0.9 ? 'pass' : dsr >= 0.65 ? 'warn' : 'fail',
      observedText: `DSR ${(dsr * 100).toFixed(1)}%`,
      thresholdText: 'DSR >= 75% (Non-Gaussian)',
    },
    {
      id: 'turnover_cost_efficiency',
      passed: run.metrics.totalCostDragPct <= 6.0 && run.metrics.avgDailyTurnover <= 0.45,
      severity:
        run.metrics.totalCostDragPct <= 6.0
          ? 'pass'
          : run.metrics.totalCostDragPct <= 14.0
            ? 'warn'
            : 'fail',
      observedText: `Cost drag -${run.metrics.totalCostDragPct.toFixed(2)}% (Turn ${(run.metrics.avgDailyTurnover * 100).toFixed(1)}%/bar)`,
      thresholdText: 'Cost drag <= 6.0% & Turn <= 45%',
    },
    {
      id: 'stress_regime_drawdown',
      passed: stressDd <= 15.0 && run.metrics.maxDrawdownPct <= 20.0,
      severity:
        run.metrics.maxDrawdownPct <= 15.0
          ? 'pass'
          : run.metrics.maxDrawdownPct <= 25.0
            ? 'warn'
            : 'fail',
      observedText: `Stress DD ${stressDd.toFixed(1)}% · Max DD ${run.metrics.maxDrawdownPct.toFixed(1)}%`,
      thresholdText: 'Stress DD <= 15% & Max DD <= 20%',
    },
    {
      id: 'oos_fold_consistency',
      passed: oosProfitableFoldRatePct >= 60,
      severity:
        oosProfitableFoldRatePct >= 60
          ? 'pass'
          : oosProfitableFoldRatePct >= 40
            ? 'warn'
            : 'fail',
      observedText: `${oosProfitableFoldRatePct.toFixed(0)}% profitable OOS folds`,
      thresholdText: '>= 60% profitable OOS folds',
    },
  ];

  // Weighted composite score (0-100); liquidation caps score at 20 immediately
  const weights = [25, 22, 18, 15, 10, 10];
  let rawScore = 0;
  for (let i = 0; i < gates.length; i++) {
    const g = gates[i];
    if (g.severity === 'pass') rawScore += weights[i];
    else if (g.severity === 'warn') rawScore += weights[i] * 0.5;
  }
  const healthScore = run.metrics.liquidated ? Math.min(20, Math.round(rawScore)) : Math.round(rawScore);
  const releaseVerdict: WalkForwardReport['releaseVerdict'] =
    run.metrics.liquidated || healthScore < 55
      ? 'rejected'
      : healthScore >= 78
        ? 'paper_ready'
        : 'needs_tuning';

  return {
    strategyId: run.strategy.id,
    strategyName: run.strategy.name,
    optimizerMode: run.optimizerMode,
    totalObservations: T,
    purgeGapBars,
    embargoBars,
    folds,
    meanIsSharpe,
    meanOosSharpe,
    oosRetentionRatio,
    oosProfitableFoldRatePct,
    overallNetSharpe: run.metrics.netSharpe,
    overallMaxDrawdownPct: run.metrics.maxDrawdownPct,
    overallTotalReturnPct: run.metrics.totalNetReturnPct,
    avgDailyTurnoverPct: run.metrics.avgDailyTurnover * 100,
    totalCostDragPct: run.metrics.totalCostDragPct,
    deflatedSharpeRatio: dsr,
    liquidated: run.metrics.liquidated,
    regimes,
    healthScore,
    releaseVerdict,
    gates,
  };
}

/**
 * 1-Click Strategy Arena: pits all 3 tradable QP strategies against the Legacy Sign-Rule baseline
 * under identical Purged Walk-Forward, Square-Root Impact, and OKX Tiered Margin constraints.
 */
export function runStrategyArena(
  params?: {
    periods?: number;
    targetAnnualVol?: number;
    maxLeverage?: number;
    linearCostBps?: number;
    seed?: number;
  },
  ledger?: IncrementalMerkleLedger,
): StrategyArenaReport {
  const periods = Math.max(180, Math.min(480, Math.floor(params?.periods ?? 280)));
  const targetAnnualVol = params?.targetAnnualVol ?? 0.14;
  const maxLeverage = params?.maxLeverage ?? 2.0;
  const linearCostBps = params?.linearCostBps ?? 6.5;
  const seed = params?.seed ?? 2026;

  const lineup: Array<{
    label: string;
    strategyId: StrategyId;
    optimizerMode: 'qp_optimized' | 'legacy_sign_rule';
  }> = [
    ...STRATEGY_CATALOG.map((s) => ({
      label: `${s.name} (QP)`,
      strategyId: s.id,
      optimizerMode: 'qp_optimized' as const,
    })),
    {
      label: 'Legacy 100% Sign-Rule Baseline',
      strategyId: 'perp_carry_funding',
      optimizerMode: 'legacy_sign_rule',
    },
  ];

  const evaluated = lineup.map((item) => {
    const wf = runPurgedWalkForwardAudit(
      {
        strategyId: item.strategyId,
        optimizerMode: item.optimizerMode,
        periods,
        targetAnnualVol,
        maxLeverage,
        linearCostBps,
        seed,
      },
      ledger,
    );
    const pipe = runUnifiedStrategyPipeline(
      {
        strategyId: item.strategyId,
        optimizerMode: item.optimizerMode,
        periods,
        targetAnnualVol,
        maxLeverage,
        linearCostBps,
        seed,
        persistToLedger: false,
      },
      ledger,
    );

    return {
      rank: 0,
      label: item.label,
      strategyId: item.strategyId,
      optimizerMode: item.optimizerMode,
      healthScore: wf.healthScore,
      releaseVerdict: wf.releaseVerdict,
      overallNetSharpe: wf.overallNetSharpe,
      meanOosSharpe: wf.meanOosSharpe,
      oosRetentionRatio: wf.oosRetentionRatio,
      overallMaxDrawdownPct: wf.overallMaxDrawdownPct,
      avgDailyTurnoverPct: wf.avgDailyTurnoverPct,
      totalCostDragPct: wf.totalCostDragPct,
      deflatedSharpeRatio: wf.deflatedSharpeRatio,
      liquidated: wf.liquidated,
      equityCurve: pipe.equityCurve.map((p) => p.equity),
    };
  });

  evaluated.sort((a, b) =>
    b.healthScore !== a.healthScore
      ? b.healthScore - a.healthScore
      : b.meanOosSharpe - a.meanOosSharpe,
  );
  evaluated.forEach((c, idx) => {
    c.rank = idx + 1;
  });

  return {
    generatedAtIso: new Date().toISOString(),
    periods,
    targetAnnualVol,
    maxLeverage,
    linearCostBps,
    competitors: evaluated,
    winnerId: evaluated[0]?.label ?? '',
  };
}

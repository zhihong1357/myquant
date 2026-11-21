import test from 'node:test';
import assert from 'node:assert/strict';
import {
  compareSignRuleVsQP,
  ledoitWolfCovariance,
  optimizePortfolioQP,
} from './portfolioOptimizer.ts';
import { createStandardNormal } from './leadLag.ts';

test('Ledoit-Wolf shrinkage produces PSD covariance with delta in [0, 1]', () => {
  const randn = createStandardNormal(123);
  const mat = Array.from({ length: 40 }, () => {
    const f = randn() * 0.02;
    return [f + randn() * 0.01, f * 1.1 + randn() * 0.012, f * 0.9 + randn() * 0.015];
  });
  const lw = ledoitWolfCovariance(mat);
  assert.ok(lw.shrinkageIntensity >= 0 && lw.shrinkageIntensity <= 1);
  assert.equal(lw.covariance.length, 3);
  for (let i = 0; i < 3; i++) {
    assert.ok(lw.covariance[i][i] > 0);
    for (let j = 0; j < 3; j++) {
      assert.ok(Math.abs(lw.covariance[i][j] - lw.covariance[j][i]) < 1e-12);
    }
  }
});

test('Garleanu-Pedersen QP enforces No-Trade Zone and gross/box/vol constraints', () => {
  const cov = [
    [0.0004, 0.0002, 0.0001],
    [0.0002, 0.0005, 0.0002],
    [0.0001, 0.0002, 0.0006],
  ];
  const prevW = [0.25, -0.15, 0.1];
  // Tiny alphas smaller than linear transaction cost (15 bps) -> all 3 assets should stay inside No-Trade Zone!
  const tinyAlpha = [0.0002, -0.0001, 0.00015];
  const opt = optimizePortfolioQP(tinyAlpha, cov, prevW, {
    riskAversion: 4.0,
    linearCostBps: 20,
    quadraticImpactBps: 2,
    maxPositionWeight: 0.5,
    maxGrossLeverage: 1.5,
    maxNetExposure: 1.0,
    targetAnnualVol: 0.4,
    periodsPerYear: 252,
  });

  assert.ok(opt.assetsInNoTradeZone >= 2, `Expected no-trade zone hold, got ${opt.assetsInNoTradeZone}`);
  assert.ok(opt.grossLeverage <= 1.5 + 1e-9);
  for (const w of opt.weights) {
    assert.ok(Math.abs(w) <= 0.5 + 1e-9);
  }
});

test('compareSignRuleVsQP dramatically reduces turnover and improves net Sharpe over Sign Rule', () => {
  const cmp = compareSignRuleVsQP({
    periods: 360,
    signalStrength: 0.1,
    linearCostBps: 8.0,
    riskAversion: 5.0,
    targetAnnualVol: 0.16,
    seed: 2026,
  });

  assert.ok(
    cmp.turnoverReductionPct > 35,
    `Expected >35% turnover reduction vs Sign Rule, got ${cmp.turnoverReductionPct.toFixed(1)}%`,
  );
  assert.ok(cmp.qpOptimized.totalCostDragPct < cmp.signRule.totalCostDragPct);
  assert.ok(cmp.qpOptimized.netSharpe > cmp.signRule.netSharpe);
  assert.ok(cmp.qpOptimized.noTradeHoldRatePct > 10);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { runPurgedWalkForwardAudit, runStrategyArena } from './walkForward.ts';

test('Purged Walk-Forward enforces strict non-overlapping purge gaps between train and test folds', () => {
  const report = runPurgedWalkForwardAudit({
    strategyId: 'perp_carry_funding',
    optimizerMode: 'qp_optimized',
    periods: 300,
    numFolds: 5,
    purgeGapBars: 6,
    embargoBars: 4,
    seed: 2026,
  });

  assert.ok(report.folds.length >= 3);
  for (const f of report.folds) {
    assert.equal(f.purgeEnd - f.purgeStart, 6);
    assert.ok(f.trainEnd < f.testStart, 'Train end must strictly precede test start');
    assert.equal(f.trainEnd, f.purgeStart);
    assert.equal(f.purgeEnd, f.testStart);
  }

  // Regime observations must partition the full sample exactly
  const regimeObsSum = report.regimes.reduce((acc, r) => acc + r.observations, 0);
  assert.equal(regimeObsSum, report.totalObservations);
  assert.equal(report.gates.length, 6);
  assert.ok(report.healthScore >= 0 && report.healthScore <= 100);
});

test('Strategy Arena ranks all 4 competitors and penalizes high-leverage liquidation immediately', () => {
  const arena = runStrategyArena({
    periods: 240,
    targetAnnualVol: 0.14,
    maxLeverage: 2.0,
    linearCostBps: 6.5,
    seed: 2026,
  });
  assert.equal(arena.competitors.length, 4);
  assert.equal(arena.competitors[0].rank, 1);
  assert.ok(arena.competitors[0].healthScore >= arena.competitors[3].healthScore);

  // Extreme 10x legacy sign rule should be penalized heavily or rejected
  const reckless = runPurgedWalkForwardAudit({
    strategyId: 'perp_carry_funding',
    optimizerMode: 'legacy_sign_rule',
    periods: 240,
    maxLeverage: 10.0,
    linearCostBps: 7.5,
    seed: 2026,
  });
  assert.ok(reckless.healthScore < 60);
});

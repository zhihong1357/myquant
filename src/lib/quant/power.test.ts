import test from 'node:test';
import assert from 'node:assert/strict';
import {
  effectiveSampleSize,
  mdeCohensD,
  mdeMeanRatio,
  mdePartialRSquared,
  mdeStandardizedMean,
  noncentrality,
} from './power.ts';

test('noncentrality matches standard normal critical values at alpha=0.05, power=0.80', () => {
  const twoSided = noncentrality(0.05, 0.8, false);
  const oneSided = noncentrality(0.05, 0.8, true);
  assert.ok(Math.abs(twoSided - 2.801585) < 1e-4);
  assert.ok(Math.abs(oneSided - 2.486475) < 1e-4);
});

test('MDE formulas match published review_report.json reference numbers under i.i.d. baseline', () => {
  const ll = mdePartialRSquared(1414, 0.05, 0.8);
  assert.ok(Math.abs(ll.minimumDetectableEffect - 0.005520192649316948) < 1e-6);

  const car = mdeStandardizedMean(135, 0.05, 0.8, true);
  assert.ok(Math.abs(car.minimumDetectableEffect - 0.21400168279054138) < 1e-6);

  const d = mdeCohensD(116, 2009, 0.05, 0.8);
  assert.ok(Math.abs(d.minimumDetectableEffect - 0.26752498076303577) < 1e-6);

  const ratio = mdeMeanRatio(0.02, 0.001, 0.05, 0.8, 100);
  assert.ok(ratio.minimumDetectableEffect > 1.13 && ratio.minimumDetectableEffect < 1.15);
});

test('Autocorrelation-adjusted N_eff accurately inflates MDE on persistent macro/spread predictors', () => {
  // Study 007 CPI step function: 1,414 daily bars but only 69 monthly CPI releases and rho = 0.95
  const nEff = effectiveSampleSize(1414, 0.95, 69);
  assert.ok(nEff <= 69);

  const naive = mdePartialRSquared(1414, 0.05, 0.8, 0);
  const adjusted = mdePartialRSquared(1414, 0.05, 0.8, 0.95, 69);
  assert.ok(adjusted.minimumDetectableEffect > naive.minimumDetectableEffect * 15);
  assert.ok((adjusted.inflationFactor ?? 1) > 15);
});

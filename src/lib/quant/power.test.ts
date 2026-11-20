import test from 'node:test';
import assert from 'node:assert/strict';
import {
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

test('MDE formulas match published review_report.json reference numbers', () => {
  // E0001: lead-lag n=1414 -> MDE partial R^2 = 0.00552019...
  const ll = mdePartialRSquared(1414, 0.05, 0.8);
  assert.ok(Math.abs(ll.minimumDetectableEffect - 0.005520192649316948) < 1e-6);

  // E0023: event-study n=135 -> MDE std mean CAR = 0.21400168...
  const car = mdeStandardizedMean(135, 0.05, 0.8, true);
  assert.ok(Math.abs(car.minimumDetectableEffect - 0.21400168279054138) < 1e-6);

  // E0030: mean comparison n=116/2009 -> MDE Cohen's d = 0.26752498...
  const d = mdeCohensD(116, 2009, 0.05, 0.8);
  assert.ok(Math.abs(d.minimumDetectableEffect - 0.26752498076303577) < 1e-6);

  // Mean ratio sanity check
  const ratio = mdeMeanRatio(0.02, 0.001, 0.05, 0.8, 100);
  assert.ok(ratio.minimumDetectableEffect > 1.13 && ratio.minimumDetectableEffect < 1.15);
});

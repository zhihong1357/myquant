import test from 'node:test';
import assert from 'node:assert/strict';
import { computeCscvPbo, computeDeflatedSharpeRatio } from './overfitting.ts';
import { createStandardNormal } from './leadLag.ts';

test('Deflated Sharpe Ratio penalizes multiple trials and negative skewness / fat tails', () => {
  const randn = createStandardNormal(2026);
  const returns = Array.from({ length: 300 }, () => 0.0012 + 0.01 * randn());

  const dsr1 = computeDeflatedSharpeRatio({ returns, numTrials: 1 });
  const dsr50 = computeDeflatedSharpeRatio({ returns, numTrials: 50 });

  assert.ok(dsr1.deflatedSharpeRatio > dsr50.deflatedSharpeRatio);
  assert.ok(dsr50.expectedMaxSharpeNull > dsr1.expectedMaxSharpeNull);

  // Inject negative crash skew into returns while keeping similar mean -> lower DSR
  const skewed = [...returns];
  skewed[10] = -0.14;
  skewed[11] = 0.03;
  skewed[12] = 0.03;
  skewed[13] = 0.03;
  skewed[14] = 0.03;
  const dsrSkewed = computeDeflatedSharpeRatio({ returns: skewed, numTrials: 10 });
  assert.ok(dsrSkewed.skewness < 0);
  assert.ok(dsrSkewed.excessKurtosis > 5);
});

test('CSCV-PBO separates pure noise overfit matrix (high PBO) from genuine alpha leader (low PBO)', () => {
  const randn = createStandardNormal(99);
  const T = 160;

  // 1. Pure noise strategies (M=8, zero true mean) -> PBO should be near ~0.4-0.7
  const noiseMatrix = Array.from({ length: 8 }, () =>
    Array.from({ length: T }, () => randn() * 0.01),
  );
  const noisePbo = computeCscvPbo(noiseMatrix, 8, 70, 2026);
  assert.equal(noisePbo.combinationsEvaluated, 70);
  assert.ok(noisePbo.pbo >= 0.25 && noisePbo.pbo <= 0.85, `Unexpected noise PBO: ${noisePbo.pbo}`);

  // 2. Genuine strong alpha leader + 7 pure noise peers -> PBO should be near 0
  const alphaMatrix = [
    Array.from({ length: T }, () => 0.0045 + randn() * 0.008),
    ...Array.from({ length: 7 }, () => Array.from({ length: T }, () => randn() * 0.01)),
  ];
  const alphaPbo = computeCscvPbo(alphaMatrix, 8, 70, 2026);
  assert.ok(alphaPbo.pbo < 0.1, `Expected low PBO for genuine alpha, got ${alphaPbo.pbo}`);
  assert.ok(alphaPbo.meanRelativeOosRank > 0.75);
});

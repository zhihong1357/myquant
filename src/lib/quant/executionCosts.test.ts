import test from 'node:test';
import assert from 'node:assert/strict';
import {
  estimatePaperExecutionCost,
  fundingSettlementsBetween,
  legacyLinearCappedImpactBps,
  notionalValue,
  squareRootImpactBps,
} from './executionCosts.ts';

test('notional value and unbounded square-root impact replace legacy 5 bps cap and null=0 bug', () => {
  assert.equal(notionalValue(90000, 10, 0.01), 9000);

  // Legacy capped impact saturates at 5.0 bps even at 10x top-5 depth
  assert.equal(legacyLinearCappedImpactBps(10, 50, 5.0), 1.0);
  assert.equal(legacyLinearCappedImpactBps(500, 50, 5.0), 5.0);
  assert.equal(legacyLinearCappedImpactBps(10, null, 5.0), null);

  // Unbounded convex square-root impact grows sharply above top-5 depth (no 5 bps ceiling!)
  const small = squareRootImpactBps({ orderQuantity: 10, depth: 50, coefficientBps: 5.0 });
  const large = squareRootImpactBps({ orderQuantity: 500, depth: 50, coefficientBps: 5.0 });
  assert.equal(small.failClosedPenaltyApplied, false);
  assert.equal(large.failClosedPenaltyApplied, false);
  assert.ok(large.impactBps > 50, `Expected unbounded large-order impact > 50 bps, got ${large.impactBps}`);
  assert.ok(large.impactBps > small.impactBps * 20);

  // Fail-Closed missing depth NEVER returns 0 bps
  const missing = squareRootImpactBps({ orderQuantity: 50, depth: null, coefficientBps: 5.0 });
  assert.equal(missing.failClosedPenaltyApplied, true);
  assert.ok(missing.impactBps >= 5.0);
});

test('funding settlements count 00/08/16 UTC boundaries strictly in (start, end]', () => {
  const start = new Date('2026-11-18T00:00:00Z');
  const end = new Date('2026-11-19T00:00:00Z');
  const settlements = fundingSettlementsBetween(start, end);
  assert.equal(settlements.length, 3);

  // 10-minute trade spanning 08:00 UTC boundary MUST charge 1 funding settlement
  const shortCrossing = fundingSettlementsBetween(
    new Date('2026-11-18T07:55:00Z'),
    new Date('2026-11-18T08:05:00Z'),
  );
  assert.equal(shortCrossing.length, 1);
});

test('estimatePaperExecutionCost enforces fail-closed missing depth and exact UTC boundary funding', () => {
  const missingDepthCost = estimatePaperExecutionCost({
    price: 100000,
    quantityContracts: 100,
    contractValue: 0.01,
    side: 'buy',
    executionRole: 'taker',
    spreadBps: 2.0,
    marketSlippageBps: 1.0,
    impactCoefficientBps: 5.0,
    orderBookDepthContracts: null,
    holdingHours: 0.25,
    entryTimestampIso: '2026-11-18T07:55:00Z',
    fundingRateBpsPer8h: 1.5,
    roundTrip: true,
  });

  assert.equal(missingDepthCost.impactMissingDepthFlag, true);
  assert.equal(missingDepthCost.failClosedPenaltyApplied, true);
  assert.ok(missingDepthCost.impactBps >= 10.0);
  assert.equal(missingDepthCost.fundingExactTimestampUsed, true);
  assert.equal(missingDepthCost.fundingIntervalsCrossed, 1);
  assert.equal(missingDepthCost.fundingBps, 1.5);
  assert.ok(missingDepthCost.totalBps > 25);
});

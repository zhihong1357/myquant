import test from 'node:test';
import assert from 'node:assert/strict';
import {
  estimatePaperExecutionCost,
  fundingSettlementsBetween,
  impactBps,
  notionalValue,
} from './executionCosts.ts';

test('notional value and impact bps handle normal, zero, and missing depth', () => {
  assert.equal(notionalValue(90000, 10, 0.01), 9000);
  assert.equal(impactBps(10, 50, 5.0), 1.0);
  assert.equal(impactBps(100, 50, 5.0), 5.0); // capped at coefficient
  assert.equal(impactBps(10, 0, 5.0), 5.0);
  assert.equal(impactBps(10, null, 5.0), null);
});

test('funding settlements count 00/08/16 UTC boundaries strictly in (start, end]', () => {
  const start = new Date('2026-11-18T00:00:00Z');
  const end = new Date('2026-11-19T00:00:00Z');
  const settlements = fundingSettlementsBetween(start, end);
  // Crosses 08:00, 16:00 on Nov 18 and 00:00 on Nov 19 (start at 00:00 excluded)
  assert.equal(settlements.length, 3);
});

test('round-trip taker cost breakdown sums all components accurately', () => {
  const result = estimatePaperExecutionCost({
    price: 100000,
    quantityContracts: 10,
    contractValue: 0.01,
    side: 'buy',
    executionRole: 'taker',
    spreadBps: 2.0,
    marketSlippageBps: 1.0,
    impactCoefficientBps: 5.0,
    orderBookDepthContracts: 50,
    holdingHours: 16,
    fundingRateBpsPer8h: 1.0,
    roundTrip: true,
  });

  // Notional = 10,000 USDT
  assert.equal(result.notionalUsdt, 10000);
  // Taker fee: 5 bps * 2 = 10 bps
  assert.equal(result.feeBps, 10);
  // Spread crossing: 1 bps * 2 = 2 bps
  assert.equal(result.spreadCrossBps, 2);
  // Slippage: 1 bps * 2 = 2 bps
  assert.equal(result.slippageBps, 2);
  // Impact: (10/50 * 5 = 1 bps) * 2 = 2 bps
  assert.equal(result.impactBps, 2);
  // Funding: 2 intervals * 1 bps = 2 bps (long pays positive funding)
  assert.equal(result.fundingIntervalsCrossed, 2);
  assert.equal(result.fundingBps, 2);
  assert.equal(result.totalBps, 18);
  assert.ok(Math.abs(result.totalUsdt - 18) < 1e-9);
});

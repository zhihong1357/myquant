import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildSyntheticL2Book,
  CoupledOrderBook,
  runPerpetualMarginStress,
  simulatePassiveLimitOrder,
} from './executionEngine.ts';

test('CoupledOrderBook mutates L2 depth across sequential child orders and increases slippage', () => {
  const snapshot = buildSyntheticL2Book({
    midPrice: 90_000,
    spreadBps: 1.0,
    topLevelContracts: 40,
    levels: 12,
    tickSize: 0.1,
    lotSize: 0.01,
  });
  const book = new CoupledOrderBook(snapshot);
  const initialTop5 = book.getTopNDepth('buy', 5);

  const child1 = book.executeTakerOrder('buy', 120);
  const child2 = book.executeTakerOrder('buy', 120);

  assert.equal(child1.filledContracts, 120);
  assert.equal(child2.filledContracts, 120);
  assert.ok(child1.remainingTop5DepthAfter < initialTop5 || child2.vwapFillPrice > child1.vwapFillPrice);
  assert.ok(
    child2.vwapFillPrice > child1.vwapFillPrice,
    `Second sequential child fill (${child2.vwapFillPrice}) must execute worse than first (${child1.vwapFillPrice})`,
  );
  assert.ok(child2.bookWalkSlippageBps >= child1.bookWalkSlippageBps);
});

test('simulatePassiveLimitOrder applies non-zero conservative fallback and detects adverse selection markout', () => {
  // Missing queueAheadContracts (null) MUST NOT default to 0.0!
  const result = simulatePassiveLimitOrder({
    side: 'buy',
    limitPrice: 90_000,
    orderContracts: 10,
    queueAheadContracts: null,
    medianLevelDepthContracts: 40,
    tapePrints: [
      // Touch print smaller than 75% fallback queue (30 contracts) -> zero fill at touch!
      { tsOffsetSec: 1, price: 90_000, size: 20, aggressorSide: 'sell' },
      // Toxic trade-through sweeps our bid and crashes price!
      { tsOffsetSec: 2, price: 89_980, size: 15, aggressorSide: 'sell' },
    ],
    postFillMid1s: 89_970,
    postFillMid10s: 89_920,
    postFillMid60s: 89_880,
  });

  assert.equal(result.conservativeFallbackApplied, true);
  assert.equal(result.queueAheadUsed, 30);
  assert.equal(result.touchOnlyFills, 0);
  assert.equal(result.tradeThroughFills, 10);
  assert.equal(result.adverseSelectionDetected, true);
  assert.ok((result.markout60sBps ?? 0) < -10);
});

test('runPerpetualMarginStress triggers intraday forced liquidation while naive margin-free model survives', () => {
  // 10x Long BTC enters at 100k, suffers an intraday flash wick down 12% to 88k, then rebounds to 105k
  const bars = [
    {
      timestampIso: '2026-11-18T00:00:00Z',
      open: 100_000,
      high: 100_500,
      low: 99_500,
      close: 100_200,
      markPrice: 100_200,
      fundingRate: 0.0001,
      isFundingBoundary: false,
    },
    {
      timestampIso: '2026-11-18T08:00:00Z',
      open: 100_200,
      high: 101_000,
      low: 88_000, // -12% flash wick wipes out 10x leveraged long!
      close: 101_500,
      markPrice: 101_500,
      fundingRate: 0.0001,
      isFundingBoundary: true,
    },
    {
      timestampIso: '2026-11-18T16:00:00Z',
      open: 101_500,
      high: 105_500,
      low: 101_000,
      close: 105_000,
      markPrice: 105_000,
      fundingRate: 0.0001,
      isFundingBoundary: true,
    },
  ];

  const sim = runPerpetualMarginStress({
    initialCashUsdt: 100_000,
    side: 'long',
    targetLeverage: 10,
    bars,
  });

  assert.equal(sim.liquidated, true);
  assert.equal(sim.liquidationPrice, 88_000);
  assert.equal(sim.finalEquity, 0);
  // Meanwhile legacy margin-free PaperPortfolio falsely claims huge +49% profit!
  assert.ok(sim.naiveNoMarginFinalEquity > 140_000);
});

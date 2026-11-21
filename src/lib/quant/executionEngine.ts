/**
 * Coupled L2 Order-Book Execution Physics & Perpetual Tiered Margin/Liquidation State Machine.
 *
 * Eliminates Stage 4b/5a Silent Killers:
 *  1. Sequential L2 Book-Walking with Mutable Depth Depletion (no independent order replay).
 *  2. Strict Tick-Size & Lot-Size Enforcement.
 *  3. Passive Limit Queue-Position & Adverse Selection Markout PnL (replaces queue_ahead_fallback=0.0).
 *  4. OKX-style Tiered Maintenance Margin (MMR), Initial Margin (IM), Mark-Price 00/08/16 UTC Funding,
 *     and Intraday High/Low Forced Liquidation Engine.
 *
 * Strictly paper-only simulation — zero exchange order execution.
 */

import {
  DEFAULT_CONTRACT_VALUE_BTC,
  OKX_REGULAR_MAKER_BPS,
  OKX_REGULAR_TAKER_BPS,
  squareRootImpactBps,
} from './executionCosts.ts';

export interface L2Level {
  price: number;
  size: number; // resting contracts
}

export interface L2BookSnapshot {
  timestampIso: string;
  midPrice: number;
  tickSize: number;
  lotSize: number;
  bids: L2Level[]; // descending price
  asks: L2Level[]; // ascending price
}

export interface BookWalkFillResult {
  side: 'buy' | 'sell';
  requestedContracts: number;
  filledContracts: number;
  unfilledContracts: number;
  vwapFillPrice: number;
  referenceMid: number;
  levelsSwept: number;
  bookWalkSlippageBps: number;
  permanentImpactBps: number;
  feeBps: number;
  totalEffectiveCostBps: number;
  remainingTop5DepthAfter: number;
  fillsByLevel: Array<{ price: number; filledContracts: number }>;
}

export interface PassiveLimitSimulationInput {
  side: 'buy' | 'sell';
  limitPrice: number;
  orderContracts: number;
  queueAheadContracts: number | null; // null triggers conservative fallback (NEVER 0!)
  medianLevelDepthContracts: number;
  tapePrints: Array<{
    tsOffsetSec: number;
    price: number;
    size: number;
    aggressorSide: 'buy' | 'sell';
  }>;
  postFillMid1s: number;
  postFillMid10s: number;
  postFillMid60s: number;
}

export interface PassiveLimitSimulationResult {
  queueAheadUsed: number;
  conservativeFallbackApplied: boolean;
  filledContracts: number;
  fillRate: number;
  touchOnlyFills: number;
  tradeThroughFills: number;
  avgFillPrice: number | null;
  markout1sBps: number | null;
  markout10sBps: number | null;
  markout60sBps: number | null;
  adverseSelectionDetected: boolean;
}

export interface OkxMarginTier {
  maxNotionalUsdt: number;
  mmr: number; // Maintenance margin rate (e.g. 0.004 = 0.4%)
  imrMin: number; // Minimum initial margin rate (1 / maxLeverage)
}

/**
 * OKX BTC-USDT-SWAP style tiered maintenance margin brackets.
 */
export const OKX_BTC_MARGIN_TIERS: readonly OkxMarginTier[] = [
  { maxNotionalUsdt: 200_000, mmr: 0.004, imrMin: 0.01 },
  { maxNotionalUsdt: 1_000_000, mmr: 0.005, imrMin: 0.02 },
  { maxNotionalUsdt: 5_000_000, mmr: 0.01, imrMin: 0.05 },
  { maxNotionalUsdt: 20_000_000, mmr: 0.025, imrMin: 0.1 },
  { maxNotionalUsdt: Infinity, mmr: 0.05, imrMin: 0.2 },
];

export function roundToTick(price: number, tickSize: number): number {
  if (tickSize <= 0) return price;
  return Math.round(price / tickSize) * tickSize;
}

export function roundToLot(size: number, lotSize: number): number {
  if (lotSize <= 0) return size;
  return Math.floor(size / lotSize + 1e-12) * lotSize;
}

export function lookupMarginTier(
  notionalUsdt: number,
  tiers: readonly OkxMarginTier[] = OKX_BTC_MARGIN_TIERS,
): OkxMarginTier {
  const absNotional = Math.abs(notionalUsdt);
  for (const tier of tiers) {
    if (absNotional <= tier.maxNotionalUsdt) {
      return tier;
    }
  }
  return tiers[tiers.length - 1];
}

/**
 * Deterministic synthetic L2 order book generator grounded in realistic OKX BTC-USDT-SWAP depth shape.
 */
export function buildSyntheticL2Book(params: {
  midPrice: number;
  spreadBps?: number;
  topLevelContracts?: number;
  levels?: number;
  tickSize?: number;
  lotSize?: number;
  timestampIso?: string;
}): L2BookSnapshot {
  const mid = params.midPrice;
  const tickSize = params.tickSize ?? 0.1;
  const lotSize = params.lotSize ?? 0.01;
  const halfSpread = Math.max(tickSize * 0.5, (mid * (params.spreadBps ?? 1.2)) / 20_000);
  const topSize = params.topLevelContracts ?? 35;
  const numLevels = Math.max(5, Math.min(40, params.levels ?? 20));

  const bestBid = roundToTick(mid - halfSpread, tickSize);
  const bestAsk = roundToTick(Math.max(bestBid + tickSize, mid + halfSpread), tickSize);

  const bids: L2Level[] = [];
  const asks: L2Level[] = [];

  for (let i = 0; i < numLevels; i++) {
    // Exponentially widening price ticks deeper in the book + realistic hump-shaped liquidity
    const stepTicks = i === 0 ? 0 : Math.round(i * (1 + i * 0.35));
    const depthMultiplier = 1 + 0.35 * Math.min(i, 6) + 0.08 * i;
    const size = roundToLot(topSize * depthMultiplier, lotSize);
    bids.push({ price: roundToTick(bestBid - stepTicks * tickSize, tickSize), size });
    asks.push({ price: roundToTick(bestAsk + stepTicks * tickSize, tickSize), size });
  }

  return {
    timestampIso: params.timestampIso ?? '2026-11-20T08:00:00.000Z',
    midPrice: (bestBid + bestAsk) / 2,
    tickSize,
    lotSize,
    bids,
    asks,
  };
}

/**
 * Mutable Coupled Order Book: sequential orders deplete resting liquidity and propagate self-impact!
 */
export class CoupledOrderBook {
  private bids: L2Level[];
  private asks: L2Level[];
  public readonly tickSize: number;
  public readonly lotSize: number;

  constructor(snapshot: L2BookSnapshot) {
    this.tickSize = snapshot.tickSize;
    this.lotSize = snapshot.lotSize;
    this.bids = snapshot.bids.map((l) => ({ ...l }));
    this.asks = snapshot.asks.map((l) => ({ ...l }));
  }

  public getMidPrice(): number {
    const bb = this.bids[0]?.price ?? 0;
    const ba = this.asks[0]?.price ?? 0;
    if (bb > 0 && ba > 0) return (bb + ba) / 2;
    return bb || ba;
  }

  public getTopNDepth(side: 'buy' | 'sell', n = 5): number {
    const book = side === 'buy' ? this.asks : this.bids;
    let sum = 0;
    for (let i = 0; i < Math.min(n, book.length); i++) {
      sum += book[i].size;
    }
    return sum;
  }

  /**
   * Executes a taker order by walking L2 book levels sequentially and mutating remaining depth.
   * Any overflow beyond visible L2 depth executes on a convex synthetic tail penalty (never capped!).
   */
  public executeTakerOrder(
    side: 'buy' | 'sell',
    rawContracts: number,
    dailyVolBps = 320,
    advContracts = 500_000,
  ): BookWalkFillResult {
    const requestedContracts = roundToLot(Math.max(0, rawContracts), this.lotSize);
    const referenceMid = this.getMidPrice();
    const book = side === 'buy' ? this.asks : this.bids;
    const preTop5Depth = this.getTopNDepth(side, 5);

    let remaining = requestedContracts;
    let totalCost = 0;
    let filled = 0;
    let levelsSwept = 0;
    const fillsByLevel: Array<{ price: number; filledContracts: number }> = [];

    for (let i = 0; i < book.length && remaining > 1e-12; i++) {
      const level = book[i];
      if (level.size <= 1e-12) continue;
      const take = roundToLot(Math.min(remaining, level.size), this.lotSize);
      if (take <= 0) break;
      level.size = Math.max(0, level.size - take);
      remaining = Math.max(0, remaining - take);
      filled += take;
      totalCost += take * level.price;
      levelsSwept++;
      fillsByLevel.push({ price: level.price, filledContracts: take });
    }

    // Remove exhausted top levels so the next child order sees the depleted spread!
    while (book.length > 0 && book[0].size <= 1e-12) {
      book.shift();
    }

    // Overflow beyond visible L2 book: convex tail sweep penalty (never capped!)
    if (remaining > 1e-12) {
      const lastVisiblePrice =
        fillsByLevel.length > 0 ? fillsByLevel[fillsByLevel.length - 1].price : referenceMid;
      const overflowRatio = remaining / Math.max(1, preTop5Depth);
      const overflowPenaltyBps = 15 * Math.pow(overflowRatio, 1.35);
      const overflowPrice = roundToTick(
        side === 'buy'
          ? lastVisiblePrice * (1 + overflowPenaltyBps / 10_000)
          : lastVisiblePrice * (1 - overflowPenaltyBps / 10_000),
        this.tickSize,
      );
      totalCost += remaining * overflowPrice;
      filled += remaining;
      fillsByLevel.push({ price: overflowPrice, filledContracts: remaining });
      remaining = 0;
    }

    const vwapFillPrice = filled > 0 ? totalCost / filled : referenceMid;
    const signedSlippageBps =
      referenceMid > 0
        ? ((side === 'buy' ? vwapFillPrice - referenceMid : referenceMid - vwapFillPrice) /
            referenceMid) *
          10_000
        : 0;
    const bookWalkSlippageBps = Math.max(0, signedSlippageBps);

    // Permanent market impact (Almgren-Chriss participation component beyond immediate book sweep)
    const sqImpact = squareRootImpactBps({
      orderQuantity: filled,
      depth: preTop5Depth,
      coefficientBps: 0, // sweep already measured directly from L2 book walk
      dailyVolBps,
      advContracts,
    });
    const permanentImpactBps = sqImpact.impactBps;
    const feeBps = OKX_REGULAR_TAKER_BPS;

    return {
      side,
      requestedContracts,
      filledContracts: filled,
      unfilledContracts: remaining,
      vwapFillPrice,
      referenceMid,
      levelsSwept,
      bookWalkSlippageBps,
      permanentImpactBps,
      feeBps,
      totalEffectiveCostBps: bookWalkSlippageBps + permanentImpactBps + feeBps,
      remainingTop5DepthAfter: this.getTopNDepth(side, 5),
      fillsByLevel,
    };
  }
}

/**
 * Queue-Aware Passive Limit Fill Simulator with Adverse Selection Markout Attribution.
 * Eliminates the `queue_ahead_fallback = 0.0` Silent Killer.
 */
export function simulatePassiveLimitOrder(
  input: PassiveLimitSimulationInput,
): PassiveLimitSimulationResult {
  const conservativeFallbackApplied = input.queueAheadContracts === null;
  // Never default to 0.0 queue ahead! When book is missing, assume 75% of median level depth ahead.
  const queueAheadUsed =
    input.queueAheadContracts !== null
      ? Math.max(0, input.queueAheadContracts)
      : Math.max(1, input.medianLevelDepthContracts * 0.75);

  let remainingQueue = queueAheadUsed;
  let remainingOrder = Math.max(0, input.orderContracts);
  let touchOnlyFills = 0;
  let tradeThroughFills = 0;
  let notionalFilled = 0;

  for (const print of input.tapePrints) {
    if (remainingOrder <= 1e-12) break;
    // Opposite aggressor required: buy limit fills on seller-initiated prints
    const isOpposite =
      (input.side === 'buy' && print.aggressorSide === 'sell') ||
      (input.side === 'sell' && print.aggressorSide === 'buy');
    if (!isOpposite) continue;

    const isTradeThrough =
      (input.side === 'buy' && print.price < input.limitPrice) ||
      (input.side === 'sell' && print.price > input.limitPrice);
    const isTouch = print.price === input.limitPrice;

    if (!isTradeThrough && !isTouch) continue;

    if (isTradeThrough) {
      // Trade-through sweeps our entire level queue first (high adverse selection!)
      remainingQueue = 0;
      const fill = Math.min(remainingOrder, print.size);
      remainingOrder -= fill;
      tradeThroughFills += fill;
      notionalFilled += fill * input.limitPrice;
    } else if (isTouch) {
      // Touch print must first exhaust queue ahead; conservative 40% fill participation at touch
      if (remainingQueue >= print.size) {
        remainingQueue -= print.size;
      } else {
        const availableAfterQueue = (print.size - remainingQueue) * 0.4;
        remainingQueue = 0;
        const fill = Math.min(remainingOrder, availableAfterQueue);
        remainingOrder -= fill;
        touchOnlyFills += fill;
        notionalFilled += fill * input.limitPrice;
      }
    }
  }

  const filledContracts = touchOnlyFills + tradeThroughFills;
  const fillRate = input.orderContracts > 0 ? filledContracts / input.orderContracts : 0;
  const avgFillPrice = filledContracts > 0 ? notionalFilled / filledContracts : null;

  const sign = input.side === 'buy' ? 1 : -1;
  const markout = (futureMid: number) =>
    avgFillPrice !== null && avgFillPrice > 0
      ? (sign * (futureMid - avgFillPrice) / avgFillPrice) * 10_000 - OKX_REGULAR_MAKER_BPS
      : null;

  const markout1sBps = markout(input.postFillMid1s);
  const markout10sBps = markout(input.postFillMid10s);
  const markout60sBps = markout(input.postFillMid60s);

  return {
    queueAheadUsed,
    conservativeFallbackApplied,
    filledContracts,
    fillRate,
    touchOnlyFills,
    tradeThroughFills,
    avgFillPrice,
    markout1sBps,
    markout10sBps,
    markout60sBps,
    adverseSelectionDetected:
      (markout10sBps !== null && markout10sBps < -1.0) ||
      (markout60sBps !== null && markout60sBps < -2.0),
  };
}

export interface MarginStressBar {
  timestampIso: string;
  open: number;
  high: number;
  low: number;
  close: number;
  markPrice: number;
  fundingRate: number; // signed decimal per 8h, e.g. 0.0001 = 1 bp
  isFundingBoundary: boolean;
}

export interface MarginSimulationResult {
  initialEquity: number;
  finalEquity: number;
  liquidated: boolean;
  liquidationTimestamp: string | null;
  liquidationPrice: number | null;
  liquidationFeePaid: number;
  peakLeverage: number;
  maxDrawdownPct: number;
  totalFundingPaid: number;
  totalFeesPaid: number;
  naiveNoMarginFinalEquity: number; // What PaperPortfolio v1 (no liquidation) would falsely report!
  equityCurve: Array<{
    timestampIso: string;
    equity: number;
    naiveEquity: number;
    marginRatio: number;
    liquidated: boolean;
  }>;
}

/**
 * Perpetual Tiered Margin, Mark-Price Funding & Intraday Liquidation State Machine.
 * Directly contrasts realistic liquidation survival against MyQuant's legacy margin-free PaperPortfolio.
 */
export function runPerpetualMarginStress(params: {
  initialCashUsdt: number;
  side: 'long' | 'short';
  targetLeverage: number;
  contractValue?: number;
  bars: readonly MarginStressBar[];
  liquidationFeeRate?: number; // default 0.005 (50 bps OKX liquidation penalty)
}): MarginSimulationResult {
  const contractVal = params.contractValue ?? DEFAULT_CONTRACT_VALUE_BTC;
  const liqFeeRate = params.liquidationFeeRate ?? 0.005;
  const dir = params.side === 'long' ? 1 : -1;
  if (params.bars.length === 0) {
    throw new Error('At least one market bar is required for margin simulation');
  }

  const entryPrice = params.bars[0].open;
  const targetNotional = params.initialCashUsdt * params.targetLeverage;
  const contracts = targetNotional / (entryPrice * contractVal);
  const entryFee = (targetNotional * OKX_REGULAR_TAKER_BPS) / 10_000;

  let cash = params.initialCashUsdt - entryFee;
  let naiveCash = cash;
  let totalFeesPaid = entryFee;
  let totalFundingPaid = 0;
  let liquidated = false;
  let liquidationTimestamp: string | null = null;
  let liquidationPrice: number | null = null;
  let liquidationFeePaid = 0;
  let peakEquity = params.initialCashUsdt;
  let maxDrawdownPct = 0;
  let peakLeverage = params.targetLeverage;

  const equityCurve: MarginSimulationResult['equityCurve'] = [];

  for (const bar of params.bars) {
    // 1. Intraday worst-case price check for forced liquidation (Low for Long, High for Short)
    if (!liquidated) {
      const worstPrice = dir === 1 ? bar.low : bar.high;
      const worstUnrealized = dir * contracts * contractVal * (worstPrice - entryPrice);
      const worstNotional = contracts * contractVal * worstPrice;
      const tier = lookupMarginTier(worstNotional);
      const maintMargin = worstNotional * tier.mmr;
      const liqFee = worstNotional * liqFeeRate;
      const worstEquity = cash + worstUnrealized;

      if (worstEquity <= maintMargin + liqFee) {
        liquidated = true;
        liquidationTimestamp = bar.timestampIso;
        liquidationPrice = worstPrice;
        liquidationFeePaid = liqFee;
        totalFeesPaid += liqFee;
        cash = Math.max(0, worstEquity - liqFee);
      }
    }

    // 2. Exact UTC 00/08/16 Mark-Price Funding Settlement
    if (bar.isFundingBoundary) {
      const fundingCashFlow = dir * contracts * contractVal * bar.markPrice * bar.fundingRate;
      naiveCash -= fundingCashFlow;
      if (!liquidated) {
        cash -= fundingCashFlow;
        totalFundingPaid += fundingCashFlow;
      }
    }

    // 3. End-of-bar Mark-to-Market equity & margin ratio
    const closeUnrealized = dir * contracts * contractVal * (bar.close - entryPrice);
    const naiveEquity = naiveCash + closeUnrealized;
    const equity = liquidated ? cash : cash + closeUnrealized;
    const notional = liquidated ? 0 : contracts * contractVal * bar.close;
    const tier = lookupMarginTier(notional);
    const maintMargin = notional * tier.mmr;
    const marginRatio = liquidated ? 0 : maintMargin > 0 ? equity / maintMargin : 99;
    const currentLev = !liquidated && equity > 0 ? notional / equity : 0;
    if (currentLev > peakLeverage) peakLeverage = currentLev;

    if (equity > peakEquity) peakEquity = equity;
    const dd = peakEquity > 0 ? ((peakEquity - equity) / peakEquity) * 100 : 0;
    if (dd > maxDrawdownPct) maxDrawdownPct = dd;

    equityCurve.push({
      timestampIso: bar.timestampIso,
      equity,
      naiveEquity,
      marginRatio,
      liquidated,
    });
  }

  const finalPoint = equityCurve[equityCurve.length - 1];
  return {
    initialEquity: params.initialCashUsdt,
    finalEquity: finalPoint.equity,
    liquidated,
    liquidationTimestamp,
    liquidationPrice,
    liquidationFeePaid,
    peakLeverage,
    maxDrawdownPct,
    totalFundingPaid,
    totalFeesPaid,
    naiveNoMarginFinalEquity: finalPoint.naiveEquity,
    equityCurve,
  };
}

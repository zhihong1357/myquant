/**
 * Paper-only execution cost model: fees, spread crossing, slippage, linear depth impact,
 * and 8-hour perpetual funding settlements.
 * Direct TypeScript port of myquant.execution.costs & OKX Regular fee schedule.
 * No live exchange connectivity or real order execution.
 */

export const DEFAULT_CONTRACT_VALUE_BTC = 0.01;
export const OKX_REGULAR_MAKER_BPS = 2.0; // 0.02%
export const OKX_REGULAR_TAKER_BPS = 5.0; // 0.05%
export const FUNDING_SETTLEMENT_HOURS = [0, 8, 16] as const;

export interface PaperExecutionInput {
  price: number;
  quantityContracts: number;
  contractValue?: number;
  side: 'buy' | 'sell';
  executionRole: 'taker' | 'maker';
  spreadBps: number;
  marketSlippageBps: number;
  impactCoefficientBps: number;
  orderBookDepthContracts: number | null;
  holdingHours: number;
  fundingRateBpsPer8h: number;
  roundTrip: boolean;
}

export interface PaperExecutionCostBreakdown {
  notionalUsdt: number;
  feeBps: number;
  feeUsdt: number;
  spreadCrossBps: number;
  spreadCrossUsdt: number;
  slippageBps: number;
  slippageUsdt: number;
  impactBps: number | null;
  impactUsdt: number | null;
  impactMissingDepthFlag: boolean;
  fundingIntervalsCrossed: number;
  fundingBps: number;
  fundingUsdt: number;
  totalBps: number;
  totalUsdt: number;
  breakEvenGrossMoveBps: number;
}

export function notionalValue(
  price: number,
  quantityContracts: number,
  contractValue = DEFAULT_CONTRACT_VALUE_BTC,
): number {
  return price * quantityContracts * contractValue;
}

export function bpsCost(
  price: number,
  quantityContracts: number,
  bps: number,
  contractValue = DEFAULT_CONTRACT_VALUE_BTC,
): number {
  return (price * quantityContracts * contractValue * bps) / 10_000.0;
}

export function impactBps(
  orderQuantity: number,
  depth: number | null,
  coefficientBps: number,
): number | null {
  if (depth === null) {
    return null;
  }
  if (depth <= 0) {
    return coefficientBps;
  }
  return coefficientBps * Math.min(orderQuantity / depth, 1.0);
}

/**
 * Counts 00:00 / 08:00 / 16:00 UTC funding settlement crossings in (start, end].
 */
export function fundingSettlementsBetween(start: Date, end: Date): Date[] {
  if (end.getTime() <= start.getTime()) {
    return [];
  }
  const results: Date[] = [];
  const startDay = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
  const endDay = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate() + 1);
  const oneDayMs = 24 * 60 * 60 * 1000;

  for (let dayMs = startDay; dayMs <= endDay; dayMs += oneDayMs) {
    const base = new Date(dayMs);
    for (const hour of FUNDING_SETTLEMENT_HOURS) {
      const settlement = new Date(
        Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), base.getUTCDate(), hour, 0, 0, 0),
      );
      if (settlement.getTime() > start.getTime() && settlement.getTime() <= end.getTime()) {
        results.push(settlement);
      }
    }
  }
  return results;
}

export function estimatePaperExecutionCost(
  input: PaperExecutionInput,
): PaperExecutionCostBreakdown {
  if (!Number.isFinite(input.price) || input.price <= 0) {
    throw new Error('price must be finite and positive');
  }
  if (!Number.isFinite(input.quantityContracts) || input.quantityContracts <= 0) {
    throw new Error('quantityContracts must be finite and positive');
  }
  const contractVal = input.contractValue ?? DEFAULT_CONTRACT_VALUE_BTC;
  if (!Number.isFinite(contractVal) || contractVal <= 0) {
    throw new Error('contractValue must be finite and positive');
  }

  const legs = input.roundTrip ? 2 : 1;
  const notionalUsdt = notionalValue(input.price, input.quantityContracts, contractVal);

  const perLegFeeBps =
    input.executionRole === 'maker' ? OKX_REGULAR_MAKER_BPS : OKX_REGULAR_TAKER_BPS;
  const feeBps = perLegFeeBps * legs;
  const feeUsdt = bpsCost(input.price, input.quantityContracts, feeBps, contractVal);

  // Taker crosses half-spread per leg; resting maker avoids crossing spread
  const perLegSpreadBps = input.executionRole === 'taker' ? Math.max(0, input.spreadBps) * 0.5 : 0;
  const spreadCrossBps = perLegSpreadBps * legs;
  const spreadCrossUsdt = bpsCost(input.price, input.quantityContracts, spreadCrossBps, contractVal);

  const perLegSlippageBps =
    input.executionRole === 'taker' ? Math.max(0, input.marketSlippageBps) : 0;
  const slippageBps = perLegSlippageBps * legs;
  const slippageUsdt = bpsCost(input.price, input.quantityContracts, slippageBps, contractVal);

  const perLegImpact =
    input.executionRole === 'taker'
      ? impactBps(input.quantityContracts, input.orderBookDepthContracts, Math.max(0, input.impactCoefficientBps))
      : 0;
  const impactMissingDepthFlag = perLegImpact === null;
  const totalImpactBps = perLegImpact === null ? null : perLegImpact * legs;
  const totalImpactUsdt =
    totalImpactBps === null
      ? null
      : bpsCost(input.price, input.quantityContracts, totalImpactBps, contractVal);

  const holdingHours = Math.max(0, input.holdingHours);
  const fundingIntervalsCrossed = Math.floor(holdingHours / 8);
  const signedDirection = input.side === 'buy' ? 1 : -1;
  // Positive funding rate means longs pay shorts
  const fundingBps = signedDirection * input.fundingRateBpsPer8h * fundingIntervalsCrossed;
  const fundingUsdt = bpsCost(input.price, input.quantityContracts, fundingBps, contractVal);

  const knownImpactBps = totalImpactBps ?? 0;
  const totalBps = feeBps + spreadCrossBps + slippageBps + knownImpactBps + fundingBps;
  const totalUsdt = feeUsdt + spreadCrossUsdt + slippageUsdt + (totalImpactUsdt ?? 0) + fundingUsdt;

  return {
    notionalUsdt,
    feeBps,
    feeUsdt,
    spreadCrossBps,
    spreadCrossUsdt,
    slippageBps,
    slippageUsdt,
    impactBps: totalImpactBps,
    impactUsdt: totalImpactUsdt,
    impactMissingDepthFlag,
    fundingIntervalsCrossed,
    fundingBps,
    fundingUsdt,
    totalBps,
    totalUsdt,
    breakEvenGrossMoveBps: Math.max(0, totalBps),
  };
}

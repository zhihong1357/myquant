/**
 * Minimum Detectable Effects (MDE) for MyQuant's core study designs,
 * upgraded with autocorrelation-adjusted Effective Sample Size (N_eff)
 * to eliminate power overestimation on persistent or step-function predictors.
 */

import { normalPpf } from './normal.ts';

export interface MinimumDetectableEffect {
  design:
    | 'lead_lag_ols'
    | 'regression_coefficient'
    | 'event_study_car'
    | 'mean_comparison';
  effectMeasure:
    | 'partial_r_squared'
    | 'coefficient'
    | 'standardized_mean_car'
    | 'cohens_d'
    | 'mean_ratio';
  minimumDetectableEffect: number;
  naiveMde?: number;
  effectiveSampleSize?: number;
  lag1Autocorrelation?: number;
  inflationFactor?: number;
  alpha: number;
  power: number;
  oneSided: boolean;
  noncentrality: number;
  sampleSize: number;
  groupSize2?: number;
}

export function noncentrality(alpha = 0.05, power = 0.8, oneSided = false): number {
  if (!Number.isFinite(alpha) || alpha <= 0 || alpha >= 1) {
    throw new Error('alpha must lie strictly between 0 and 1');
  }
  if (!Number.isFinite(power) || power <= 0 || power >= 1) {
    throw new Error('power must lie strictly between 0 and 1');
  }
  const critical = oneSided ? normalPpf(1 - alpha) : normalPpf(1 - alpha / 2);
  return critical + normalPpf(power);
}

/**
 * Computes Newey-West / Bartlett effective sample size under AR(1) autocorrelation rho,
 * optionally capped by an explicit number of distinct regime/step values (e.g. 69 CPI releases).
 */
export function effectiveSampleSize(
  observations: number,
  lag1Autocorr = 0,
  distinctRegimeCount?: number,
): number {
  if (!Number.isInteger(observations) || observations < 1) {
    throw new Error('observations must be a positive integer');
  }
  if (!Number.isFinite(lag1Autocorr) || lag1Autocorr <= -1 || lag1Autocorr >= 1) {
    throw new Error('lag1Autocorr must lie strictly inside (-1, 1)');
  }
  // Under positive persistence rho > 0, long-run variance scales by (1 + rho) / (1 - rho)
  const rhoPos = Math.max(0, lag1Autocorr);
  const ar1Neff = observations * ((1 - rhoPos) / (1 + rhoPos));
  const capped =
    distinctRegimeCount !== undefined && Number.isFinite(distinctRegimeCount) && distinctRegimeCount >= 1
      ? Math.min(ar1Neff, distinctRegimeCount)
      : ar1Neff;
  return Math.max(1, Math.round(capped));
}

export function mdePartialRSquared(
  observations: number,
  alpha = 0.05,
  power = 0.8,
  lag1Autocorr = 0,
  distinctRegimeCount?: number,
): MinimumDetectableEffect {
  if (!Number.isInteger(observations) || observations < 1) {
    throw new Error('observations must be a positive integer');
  }
  const lambda = noncentrality(alpha, power, false);
  const lambdaSq = lambda * lambda;
  const naiveMde = lambdaSq / (lambdaSq + observations);
  const nEff = effectiveSampleSize(observations, lag1Autocorr, distinctRegimeCount);
  const mde = lambdaSq / (lambdaSq + nEff);
  return {
    design: 'lead_lag_ols',
    effectMeasure: 'partial_r_squared',
    minimumDetectableEffect: mde,
    naiveMde,
    effectiveSampleSize: nEff,
    lag1Autocorrelation: lag1Autocorr,
    inflationFactor: naiveMde > 0 ? mde / naiveMde : 1,
    alpha,
    power,
    oneSided: false,
    noncentrality: lambda,
    sampleSize: observations,
  };
}

export function mdeCoefficient(
  standardError: number,
  alpha = 0.05,
  power = 0.8,
  oneSided = false,
  sampleSize = 1,
): MinimumDetectableEffect {
  if (!Number.isFinite(standardError) || standardError <= 0) {
    throw new Error('standardError must be finite and positive');
  }
  if (!Number.isInteger(sampleSize) || sampleSize < 1) {
    throw new Error('sampleSize must be a positive integer');
  }
  const lambda = noncentrality(alpha, power, oneSided);
  return {
    design: 'regression_coefficient',
    effectMeasure: 'coefficient',
    minimumDetectableEffect: lambda * standardError,
    alpha,
    power,
    oneSided,
    noncentrality: lambda,
    sampleSize,
  };
}

export function mdeStandardizedMean(
  observations: number,
  alpha = 0.05,
  power = 0.8,
  oneSided = true,
  lag1Autocorr = 0,
): MinimumDetectableEffect {
  if (!Number.isInteger(observations) || observations < 1) {
    throw new Error('observations must be a positive integer');
  }
  const lambda = noncentrality(alpha, power, oneSided);
  const nEff = effectiveSampleSize(observations, lag1Autocorr);
  const naiveMde = lambda / Math.sqrt(observations);
  const mde = lambda / Math.sqrt(nEff);
  return {
    design: 'event_study_car',
    effectMeasure: 'standardized_mean_car',
    minimumDetectableEffect: mde,
    naiveMde,
    effectiveSampleSize: nEff,
    lag1Autocorrelation: lag1Autocorr,
    inflationFactor: naiveMde > 0 ? mde / naiveMde : 1,
    alpha,
    power,
    oneSided,
    noncentrality: lambda,
    sampleSize: observations,
  };
}

export function mdeCohensD(
  groupSize1: number,
  groupSize2: number,
  alpha = 0.05,
  power = 0.8,
): MinimumDetectableEffect {
  if (!Number.isInteger(groupSize1) || groupSize1 < 1) {
    throw new Error('groupSize1 must be a positive integer');
  }
  if (!Number.isInteger(groupSize2) || groupSize2 < 1) {
    throw new Error('groupSize2 must be a positive integer');
  }
  const lambda = noncentrality(alpha, power, false);
  const mde = lambda * Math.sqrt(1 / groupSize1 + 1 / groupSize2);
  return {
    design: 'mean_comparison',
    effectMeasure: 'cohens_d',
    minimumDetectableEffect: mde,
    alpha,
    power,
    oneSided: false,
    noncentrality: lambda,
    sampleSize: groupSize1,
    groupSize2,
  };
}

export function mdeMeanRatio(
  meanBaseline: number,
  standardErrorOfDifference: number,
  alpha = 0.05,
  power = 0.8,
  sampleSize = 1,
): MinimumDetectableEffect {
  if (!Number.isFinite(meanBaseline) || meanBaseline <= 0) {
    throw new Error('meanBaseline must be finite and positive');
  }
  if (!Number.isFinite(standardErrorOfDifference) || standardErrorOfDifference <= 0) {
    throw new Error('standardErrorOfDifference must be finite and positive');
  }
  if (!Number.isInteger(sampleSize) || sampleSize < 1) {
    throw new Error('sampleSize must be a positive integer');
  }
  const lambda = noncentrality(alpha, power, false);
  return {
    design: 'mean_comparison',
    effectMeasure: 'mean_ratio',
    minimumDetectableEffect: 1 + (lambda * standardErrorOfDifference) / meanBaseline,
    alpha,
    power,
    oneSided: false,
    noncentrality: lambda,
    sampleSize,
  };
}

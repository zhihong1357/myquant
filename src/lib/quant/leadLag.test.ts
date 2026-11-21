import test from 'node:test';
import assert from 'node:assert/strict';
import { qrDecomposeAndSolve, runSyntheticLeadLag } from './leadLag.ts';

test('Householder QR solves OLS cleanly with finite condition number and rejects collinearity', () => {
  const X = [
    [1, 1],
    [1, 2],
    [1, 3],
    [1, 4],
  ];
  const y = [3, 5, 7, 9]; // y = 1 + 2x
  const res = qrDecomposeAndSolve(X, y);
  assert.ok(Math.abs(res.beta[0] - 1) < 1e-10);
  assert.ok(Math.abs(res.beta[1] - 2) < 1e-10);
  assert.ok(Number.isFinite(res.conditionNumber) && res.conditionNumber > 0);

  const singular = [
    [1, 2, 4],
    [1, 3, 6],
    [1, 4, 8],
    [1, 5, 10],
  ];
  assert.throws(() => qrDecomposeAndSolve(singular, y), /collinear|singular/);
});

test('detects true lead-lag in SOURCE_LEADS_TARGET and remains null in NULL scenario', () => {
  const lead = runSyntheticLeadLag({
    scenario: 'source_leads_target',
    observations: 800,
    beta: 0.25,
    commonFactorLoading: 0.4,
    lagSteps: 1,
    maxHacLag: 5,
    autoBandwidth: true,
    controlCommonFactor: true,
    factorTiming: 'pit_lagged',
    seed: 2026,
  });

  assert.equal(lead.factorTiming, 'pit_lagged');
  assert.equal(lead.bandwidthMode, 'andrews_auto');
  assert.ok(lead.coefficient > 0.15 && lead.coefficient < 0.35);
  assert.ok(lead.pValue < 0.001);
  assert.ok(lead.partialRSquared > 0.03);
  assert.ok(lead.bootstrapCiLower > 0 && lead.bootstrapCiUpper > lead.bootstrapCiLower);
  assert.ok(lead.effectiveSampleSize > 0 && lead.effectiveSampleSize <= lead.observations);

  const nullRun = runSyntheticLeadLag({
    scenario: 'null',
    observations: 800,
    beta: 0,
    commonFactorLoading: 0,
    lagSteps: 1,
    maxHacLag: 5,
    controlCommonFactor: false,
    seed: 2026,
  });

  assert.ok(Math.abs(nullRun.coefficient) < 0.12);
  assert.ok(nullRun.pValue > 0.05);
});

test('PIT-lagged common-factor control suppresses spurious lead-lag and quantifies legacy lookahead leak', () => {
  const uncontrolled = runSyntheticLeadLag({
    scenario: 'common_factor',
    observations: 1000,
    beta: 0,
    commonFactorLoading: 1.0,
    lagSteps: 1,
    maxHacLag: 5,
    controlCommonFactor: false,
    seed: 42,
  });

  const controlledPit = runSyntheticLeadLag({
    scenario: 'common_factor',
    observations: 1000,
    beta: 0,
    commonFactorLoading: 1.0,
    lagSteps: 1,
    maxHacLag: 5,
    controlCommonFactor: true,
    factorTiming: 'pit_lagged',
    seed: 42,
  });

  assert.ok(Math.abs(controlledPit.coefficient) < Math.abs(uncontrolled.coefficient));
  assert.ok(controlledPit.pValue > 0.05);
  assert.ok(controlledPit.lookaheadComparison !== undefined);

  // Under source_leads_target with heavy common factor loading, leaking factor[t] inflates partial R^2!
  const leakAudit = runSyntheticLeadLag({
    scenario: 'source_leads_target',
    observations: 1000,
    beta: 0.2,
    commonFactorLoading: 1.8,
    lagSteps: 1,
    maxHacLag: 5,
    controlCommonFactor: true,
    factorTiming: 'pit_lagged',
    seed: 101,
  });
  assert.ok(leakAudit.lookaheadComparison !== undefined);
  assert.ok(
    leakAudit.lookaheadComparison.leakedPartialRSquared >
      leakAudit.lookaheadComparison.pitPartialRSquared * 1.5,
    'Contemporaneous factor leak must significantly inflate partial R^2 over strict PIT lag',
  );
});

test('heavy_tail_garch scenario runs stably with Student-t and circular block-bootstrap diagnostics', () => {
  const garch = runSyntheticLeadLag({
    scenario: 'heavy_tail_garch',
    observations: 600,
    beta: 0.22,
    commonFactorLoading: 0.3,
    lagSteps: 1,
    maxHacLag: 6,
    autoBandwidth: true,
    controlCommonFactor: false,
    seed: 77,
  });

  assert.ok(Number.isFinite(garch.pValue) && garch.pValue >= 0 && garch.pValue <= 1);
  assert.ok(Number.isFinite(garch.bootstrapPValue));
  assert.ok(garch.pValue >= garch.asymptoticNormalPValue - 1e-12);
});

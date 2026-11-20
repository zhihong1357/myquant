import test from 'node:test';
import assert from 'node:assert/strict';
import { runSyntheticLeadLag } from './leadLag.ts';

test('detects true lead-lag in SOURCE_LEADS_TARGET and remains null in NULL scenario', () => {
  const lead = runSyntheticLeadLag({
    scenario: 'source_leads_target',
    observations: 800,
    beta: 0.25,
    commonFactorLoading: 0.4,
    lagSteps: 1,
    maxHacLag: 5,
    controlCommonFactor: true,
    seed: 2026,
  });

  assert.ok(lead.coefficient > 0.15 && lead.coefficient < 0.35);
  assert.ok(lead.pValue < 0.001);
  assert.ok(lead.partialRSquared > 0.03);

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

test('common-factor control suppresses spurious lead-lag under COMMON_FACTOR scenario', () => {
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

  const controlled = runSyntheticLeadLag({
    scenario: 'common_factor',
    observations: 1000,
    beta: 0,
    commonFactorLoading: 1.0,
    lagSteps: 1,
    maxHacLag: 5,
    controlCommonFactor: true,
    seed: 42,
  });

  assert.ok(Math.abs(controlled.coefficient) < Math.abs(uncontrolled.coefficient));
  assert.ok(controlled.pValue > 0.05);
});

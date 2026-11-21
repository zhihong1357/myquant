import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { IncrementalMerkleLedger } from './merkleLedger.ts';
import { runUnifiedStrategyPipeline, STRATEGY_CATALOG } from './unifiedPipeline.ts';

test('Unified Strategy Pipeline executes all 3 tradable strategies, persists to Merkle ledger, and computes real CSCV-PBO', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'myquant-pipe-'));
  const ledger = new IncrementalMerkleLedger(
    path.join(tmpDir, 'trials.jsonl'),
    path.join(tmpDir, 'trials.anchor.json'),
  );

  try {
    assert.equal(STRATEGY_CATALOG.length, 3);
    const results = STRATEGY_CATALOG.map((s, idx) =>
      runUnifiedStrategyPipeline(
        {
          strategyId: s.id,
          optimizerMode: 'qp_optimized',
          periods: 180,
          targetAnnualVol: 0.14,
          maxLeverage: 2.0,
          linearCostBps: 6.5,
          seed: 2026 + idx * 17,
          persistToLedger: true,
        },
        ledger,
      ),
    );

    assert.equal(ledger.getEntries().length, 3);
    assert.equal(ledger.verifyIntegrity().valid, true);

    const last = results[2];
    assert.equal(last.merkleReceipt.persisted, true);
    assert.equal(last.merkleReceipt.index, 2);
    assert.equal(last.labOverfittingAudit.totalPersistedTrials, 3);
    assert.ok(
      last.labOverfittingAudit.cscvPbo !== null &&
        last.labOverfittingAudit.cscvPbo >= 0 &&
        last.labOverfittingAudit.cscvPbo <= 1,
    );
    assert.equal(last.equityCurve.length, 180);

    // High leverage (10x) legacy sign rule triggers realistic liquidation check or extreme drawdown
    const highLev = runUnifiedStrategyPipeline({
      strategyId: 'perp_carry_funding',
      optimizerMode: 'legacy_sign_rule',
      periods: 180,
      maxLeverage: 10.0,
      linearCostBps: 7.5,
      seed: 2026,
      persistToLedger: false,
    });
    assert.ok(highLev.metrics.avgDailyTurnover > results[0].metrics.avgDailyTurnover * 2);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

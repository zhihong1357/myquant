import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  IncrementalMerkleLedger,
  verifyMerkleProof,
  type StrategyTrialRecord,
} from './merkleLedger.ts';

function makeDummyTrial(idx: number): StrategyTrialRecord {
  return {
    trialId: `TEST-${idx}`,
    strategyId: 'perp_carry_funding',
    strategyName: 'Perpetual Carry',
    mode: 'qp_optimized',
    recordedAt: new Date(Date.UTC(2026, 10, 1, idx)).toISOString(),
    seed: 100 + idx,
    observations: 80,
    netSharpe: 1.1 + idx * 0.1,
    grossSharpe: 1.4 + idx * 0.1,
    annualizedVolPct: 12,
    maxDrawdownPct: 5.5,
    totalNetReturnPct: 8.2,
    avgDailyTurnover: 0.15,
    liquidated: false,
    rawPValue: 0.02,
    deflatedSharpeRatio: 0.88,
    netReturns: Array.from({ length: 80 }, (_, t) => ((t + idx) % 5 - 1.8) * 0.002),
  };
}

test('IncrementalMerkleLedger appends in O(1), verifies inclusion proofs, and detects truncation/tampering', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'myquant-merkle-'));
  const ledgerPath = path.join(tmpDir, 'ledger.jsonl');
  const anchorPath = path.join(tmpDir, 'ledger.anchor.json');

  try {
    const ledger = new IncrementalMerkleLedger(ledgerPath, anchorPath);
    for (let i = 0; i < 5; i++) {
      ledger.append(makeDummyTrial(i));
    }

    assert.equal(ledger.getEntries().length, 5);
    assert.equal(ledger.verifyIntegrity().valid, true);

    // Inclusion proof for every leaf validates against current Merkle root
    const anchor = ledger.getAnchor();
    for (let i = 0; i < 5; i++) {
      const proof = ledger.proveInclusion(i);
      assert.equal(proof.verified, true);
      assert.equal(verifyMerkleProof(proof.leafHash, proof.proof, anchor.merkleRoot), true);
    }

    // Reload from disk and verify integrity persists
    const reloaded = new IncrementalMerkleLedger(ledgerPath, anchorPath);
    assert.equal(reloaded.getEntries().length, 5);
    assert.equal(reloaded.verifyIntegrity().valid, true);

    // Simulate truncation attack: remove last JSONL line without updating anchor
    const lines = fs.readFileSync(ledgerPath, 'utf-8').trim().split('\n');
    fs.writeFileSync(ledgerPath, `${lines.slice(0, 4).join('\n')}\n`, 'utf-8');
    const tampered = new IncrementalMerkleLedger(ledgerPath, anchorPath);
    const check = tampered.verifyIntegrity();
    assert.equal(check.valid, false);
    assert.match(check.error ?? '', /Anchor mismatch/);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

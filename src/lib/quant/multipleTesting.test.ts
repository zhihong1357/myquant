import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { adjustPValues } from './multipleTesting.ts';

test('Holm and Benjamini-Hochberg preserve input order and adjust correctly', () => {
  const raw = [0.04, 0.001, 0.25, 0.015];
  const holm = adjustPValues(raw, 'holm', 0.05);
  assert.equal(holm.length, 4);
  // Sorted: 0.001 (x4=0.004), 0.015 (x3=0.045), 0.04 (x2=0.08), 0.25 (x1=0.25)
  assert.ok(Math.abs(holm[1].adjustedPValue - 0.004) < 1e-12);
  assert.equal(holm[1].reject, true);
  assert.ok(Math.abs(holm[3].adjustedPValue - 0.045) < 1e-12);
  assert.equal(holm[3].reject, true);
  assert.ok(Math.abs(holm[0].adjustedPValue - 0.08) < 1e-12);
  assert.equal(holm[0].reject, false);

  const bh = adjustPValues(raw, 'benjamini_hochberg', 0.05);
  // Sorted BH: idx1: 0.004, idx3: 0.03, idx0: 0.05333, idx2: 0.25
  assert.ok(Math.abs(bh[1].adjustedPValue - 0.004) < 1e-12);
  assert.ok(Math.abs(bh[3].adjustedPValue - 0.03) < 1e-12);
  assert.equal(bh[3].reject, true);
  assert.equal(bh[0].reject, false);
});

test('Matches real 42-edge lab-wide multiple-testing audit counts (3 Holm, 5 BH)', () => {
  const regPath = path.resolve(process.cwd(), 'research/graph/registry.json');
  const registry = JSON.parse(fs.readFileSync(regPath, 'utf-8')) as {
    edges: Array<{ edge_id: string; status: string; p_value: number | null }>;
  };
  const tested = registry.edges.filter(
    (e) => (e.status === 'supported' || e.status === 'rejected') && typeof e.p_value === 'number',
  );
  assert.equal(tested.length, 42);

  const pvals = tested.map((e) => e.p_value as number);
  const holm = adjustPValues(pvals, 'holm', 0.05);
  const bh = adjustPValues(pvals, 'benjamini_hochberg', 0.05);

  const holmSupported = tested.filter((e, i) => e.status === 'supported' && holm[i].reject).length;
  const bhSupported = tested.filter((e, i) => e.status === 'supported' && bh[i].reject).length;

  assert.equal(holmSupported, 3);
  assert.equal(bhSupported, 5);
});

test('Rejects NONE correction when multiple tests are provided', () => {
  assert.throws(() => adjustPValues([0.01, 0.02], 'none', 0.05), /NONE correction/);
});

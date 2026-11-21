import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  adjustPValues,
  assessEdgeHygiene,
  filterCleanLabEdges,
  onlineLordPlusPlus,
  onlineSaffron,
} from './multipleTesting.ts';

test('Holm and Benjamini-Hochberg preserve input order and adjust correctly', () => {
  const raw = [0.04, 0.001, 0.25, 0.015];
  const holm = adjustPValues(raw, 'holm', 0.05);
  assert.equal(holm.length, 4);
  assert.ok(Math.abs(holm[1].adjustedPValue - 0.004) < 1e-12);
  assert.equal(holm[1].reject, true);
  assert.ok(Math.abs(holm[3].adjustedPValue - 0.045) < 1e-12);
  assert.equal(holm[3].reject, true);
  assert.ok(Math.abs(holm[0].adjustedPValue - 0.08) < 1e-12);
  assert.equal(holm[0].reject, false);

  const bh = adjustPValues(raw, 'benjamini_hochberg', 0.05);
  assert.ok(Math.abs(bh[1].adjustedPValue - 0.004) < 1e-12);
  assert.ok(Math.abs(bh[3].adjustedPValue - 0.03) < 1e-12);
  assert.equal(bh[3].reject, true);
  assert.equal(bh[0].reject, false);
});

test('Online LORD++ and SAFFRON allocate sequential alpha wealth and reward true discoveries', () => {
  const stream = [0.45, 0.0002, 0.3, 0.001, 0.8, 0.0005];
  const lord = onlineLordPlusPlus(stream, 0.05);
  const saffron = onlineSaffron(stream, 0.05);

  assert.equal(lord.length, stream.length);
  assert.equal(saffron.length, stream.length);
  // First very strong signal (0.0002) is rejected; rejection boosts subsequent alpha wealth
  assert.equal(lord[1].reject, true);
  assert.ok((lord[2].alphaThreshold ?? 0) > (lord[1].alphaThreshold ?? 0));
  assert.equal(saffron[1].reject, true);
  assert.equal(lord[4].reject, false);
});

test('Matches real 42-edge lab-wide audit counts AND hygiene filter excludes E0026 + TYVIX edges', () => {
  const regPath = path.resolve(process.cwd(), 'research/graph/registry.json');
  const registry = JSON.parse(fs.readFileSync(regPath, 'utf-8')) as {
    edges: Array<{
      edge_id: string;
      source_instrument?: string;
      target_instrument?: string;
      status: string;
      p_value: number | null;
    }>;
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

  // Hygiene filter catches mechanical identity E0026 and discontinued index:tyvix edges
  const { clean, excluded } = filterCleanLabEdges(tested);
  assert.ok(excluded.some((x) => x.edge.edge_id === 'E0026' && x.assessment.isMechanicalIdentity));
  assert.ok(
    excluded.some((x) => x.assessment.usesDiscontinuedSeries),
    'Discontinued TYVIX edges must be flagged and excluded from clean planner family',
  );
  assert.equal(clean.length + excluded.length, tested.length);
  assert.equal(assessEdgeHygiene({ edge_id: 'E0030', status: 'supported', p_value: 0.001 }).cleanForPlanner, true);
});

test('Rejects NONE correction when multiple tests are provided', () => {
  assert.throws(() => adjustPValues([0.01, 0.02], 'none', 0.05), /NONE correction/);
});

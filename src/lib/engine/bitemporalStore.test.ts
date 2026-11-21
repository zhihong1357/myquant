import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BitemporalColumnarStore,
  BitemporalViolationError,
  runBitemporalAuditDemo,
} from './bitemporalStore.ts';

test('BitemporalColumnarStore blocks fake FRED PIT writes (knowledgeTs == eventTs) at write time', () => {
  const store = new BitemporalColumnarStore();
  const ts = Date.UTC(2026, 9, 19, 21, 0, 0);

  assert.throws(
    () =>
      store.insert({
        instrumentId: 'credit:baa-10y-spread',
        field: 'close',
        eventTs: ts,
        knowledgeTs: ts, // Violates 48h mandatory BAA10Y publication lag!
        ingestedTs: ts,
        vintageId: 1,
        sourceId: 'fred',
        value: 1.75,
      }),
    BitemporalViolationError,
  );
});

test('Strict ASOF JOIN never returns future knowledgeTs and resolves latest revision vintage', () => {
  const store = new BitemporalColumnarStore();
  const day1 = Date.UTC(2026, 9, 19, 21, 0, 0);
  const day3 = day1 + 48 * 3600_000;
  const day5 = day1 + 96 * 3600_000;

  store.insertBatch([
    {
      instrumentId: 'credit:baa-10y-spread',
      field: 'close',
      eventTs: day1,
      knowledgeTs: day3,
      ingestedTs: day3,
      vintageId: 1,
      sourceId: 'fred',
      value: 1.71,
    },
    {
      instrumentId: 'credit:baa-10y-spread',
      field: 'close',
      eventTs: day1,
      knowledgeTs: day5,
      ingestedTs: day5,
      vintageId: 2, // Revision posted on day 5
      sourceId: 'fred',
      value: 1.74,
    },
  ]);

  // On day 2, day 1's BAA10Y is not yet published!
  assert.equal(store.queryAsof('credit:baa-10y-spread', 'close', day1 + 24 * 3600_000), null);
  // On day 3, vintage 1 (1.71) is visible, NOT vintage 2!
  const atDay3 = store.queryAsof('credit:baa-10y-spread', 'close', day3);
  assert.equal(atDay3?.value, 1.71);
  assert.equal(atDay3?.vintageId, 1);
  // On day 5, vintage 2 (1.74) supersedes vintage 1
  const atDay5 = store.queryAsof('credit:baa-10y-spread', 'close', day5);
  assert.equal(atDay5?.value, 1.74);
  assert.equal(atDay5?.vintageId, 2);
});

test('runBitemporalAuditDemo exposes 100% lookahead leak in naive event-time FRED join', () => {
  const audit = runBitemporalAuditDemo({ sourceId: 'fred', instrumentId: 'credit:baa-10y-spread' });
  assert.equal(audit.fakePitWriteBlocked, true);
  assert.equal(audit.enforcedLagHours, 48);
  assert.equal(audit.rowsWithLookaheadLeak, audit.rowsEvaluated);
  assert.equal(audit.meanLookaheadHoursLeaked, 48);
});

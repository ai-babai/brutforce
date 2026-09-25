import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyFastReport } from './verify-fast-report.mjs';

const revision = 'a'.repeat(40);
function fixture() {
  return {
    schemaVersion: 2, revision, status: 'partial',
    databaseEvidence: { valid: true, revision },
    timing: { suites: ['api', 'eval', 'ui', 'database'].map(id => ({ id, status: 'passed', processWallMs: id === 'database' ? null : 1 })) },
    tests: ['api', 'eval', 'ui', 'database'].map(suite => ({ name: `${suite} test`, suite, status: 'passed' })),
    cases: [{ id: 'AIR-001', status: 'passed' }, { id: 'AIR-002', status: 'skipped' }],
  };
}
const registry = () => ({ schemaVersion: 1, cases: [{ id: 'AIR-001' }, { id: 'AIR-002' }] });
function policy() {
  return { schemaVersion: 1, targetScope: 'maks-demo-only', exceptions: [{ ids: ['AIR-002'], reason: 'Device-only behavior', evidence: 'Review note' }] };
}

test('exact deferred case preserves partial BDD coverage and passes the required gate', () => {
  const result = verifyFastReport(fixture(), revision, policy(), registry());
  assert.equal(result.status, 'passed');
  assert.equal(result.bddCoverageStatus, 'partial');
  assert.equal(result.targetScope, 'maks-demo-only');
  assert.deepEqual(result.coverageExceptions.map(item => item.id), ['AIR-002']);
});

test('unexpected skipped case blocks the release', () => {
  const run = fixture(); run.cases.push({ id: 'AIR-003', status: 'skipped' });
  assert.throws(() => verifyFastReport(run, revision, policy(), { ...registry(), cases: [...registry().cases, { id: 'AIR-003' }] }), /Required case is not passed: AIR-003/);
});

test('failure blocks even an excepted case', () => {
  const run = fixture(); run.cases[1].status = 'failed';
  assert.throws(() => verifyFastReport(run, revision, policy(), registry()), /Failed case: AIR-002/);
});

test('missing database evidence or mismatched revision blocks the release', () => {
  const run = fixture(); run.databaseEvidence.valid = false;
  assert.throws(() => verifyFastReport(run, revision, policy(), registry()), /PostgreSQL evidence/);
  run.databaseEvidence.valid = true; run.revision = 'b'.repeat(40);
  assert.throws(() => verifyFastReport(run, revision, policy(), registry()), /revision differs/);
});

test('stale and wildcard-style exceptions block the release', () => {
  const run = fixture(); run.cases[1].status = 'passed'; run.status = 'passed';
  assert.throws(() => verifyFastReport(run, revision, policy(), registry()), /stale exception/);
  const broad = policy(); broad.exceptions[0].ids = ['AIR-*'];
  assert.throws(() => verifyFastReport(fixture(), revision, broad, registry()), /Invalid or duplicate exception/);
});

test('a removed required case, missing suite result or skipped test blocks the release', () => {
  const run = fixture(); run.cases.shift();
  assert.throws(() => verifyFastReport(run, revision, policy(), registry()), /case IDs differ/);
  const noSuite = fixture(); noSuite.timing.suites[0].processWallMs = null;
  assert.throws(() => verifyFastReport(noSuite, revision, policy(), registry()), /no process result/);
  const skipped = fixture(); skipped.tests[0].status = 'skipped';
  assert.throws(() => verifyFastReport(skipped, revision, policy(), registry()), /failed or was skipped/);
});

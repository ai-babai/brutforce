#!/usr/bin/env node
// A partial BDD map may still contain a complete required release set. Every
// deferred case must be named in the versioned policy; failures never defer.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export function verifyFastReport(run, revision, policy, registry) {
  if (run?.schemaVersion !== 2 || !Array.isArray(run.cases) || !run.cases.length)
    throw new Error('Fast report has an invalid case map');
  if (registry?.schemaVersion !== 1 || !Array.isArray(registry.cases) || !registry.cases.length)
    throw new Error('Canonical case registry is missing');
  const expected = new Set(registry.cases.map(item => item.id));
  if (expected.size !== registry.cases.length) throw new Error('Duplicate IDs in canonical case registry');
  const actual = new Set(run.cases.map(item => item.id));
  if (actual.size !== run.cases.length || expected.size !== actual.size || [...expected].some(id => !actual.has(id)))
    throw new Error('Fast report case IDs differ from canonical registry');
  if (run.revision !== revision) throw new Error('Fast report revision differs from package revision');
  if (!['passed', 'partial'].includes(run.status)) throw new Error(`Fast report failed: ${run.status}`);
  if (run.databaseEvidence?.valid !== true || run.databaseEvidence.revision !== revision)
    throw new Error('PostgreSQL evidence is missing, invalid, or for another revision');
  const suiteRows = run.timing?.suites || [];
  const suites = new Set(suiteRows.map(suite => suite.id));
  for (const id of ['api', 'eval', 'ui', 'database'])
    if (!suites.has(id)) throw new Error(`Missing required suite: ${id}`);
  if (suites.size !== suiteRows.length) throw new Error('Duplicate suite ID');
  if (suiteRows.some(suite => suite.id !== 'database' && !Number.isFinite(suite.processWallMs)))
    throw new Error('A required suite has no process result');
  if (suiteRows.find(suite => suite.id === 'database')?.status !== 'passed')
    throw new Error('PostgreSQL suite did not pass');
  if (suiteRows.some(suite => suite.status && suite.status !== 'passed'))
    throw new Error('A required suite did not pass');
  if (!Array.isArray(run.tests) || !run.tests.length)
    throw new Error('Fast report has no test evidence');
  for (const id of ['api', 'eval', 'ui', 'database'])
    if (!run.tests.some(test => test.suite === id)) throw new Error(`No test evidence for suite: ${id}`);
  if (policy?.schemaVersion !== 1 || !Array.isArray(policy.exceptions))
    throw new Error('Invalid release exception policy');
  if (policy.exceptions.length && policy.targetScope !== 'maks-demo-only')
    throw new Error('Coverage exceptions require Maks demo-only scope');
  const exceptions = new Map();
  for (const item of policy.exceptions) {
    if (!item.reason?.trim() || !item.evidence?.trim() || !Array.isArray(item.ids) || !item.ids.length)
      throw new Error('Every exception needs exact IDs, a reason and alternative evidence');
    for (const id of item.ids) {
      if (!/^[A-Z]+-\d{3}$/.test(id) || exceptions.has(id)) throw new Error(`Invalid or duplicate exception: ${id}`);
      exceptions.set(id, { reason: item.reason, evidence: item.evidence });
    }
  }
  const seen = new Set(), deferred = [];
  for (const item of run.cases) {
    if (seen.has(item.id)) throw new Error(`Duplicate case: ${item.id}`);
    seen.add(item.id);
    if (['failed', 'error'].includes(item.status)) throw new Error(`Failed case: ${item.id}`);
    if (item.status === 'passed') {
      if (exceptions.has(item.id)) throw new Error(`Remove stale exception for passing case: ${item.id}`);
      continue;
    }
    if (!['skipped', 'not_run'].includes(item.status) || !exceptions.has(item.id))
      throw new Error(`Required case is not passed: ${item.id} (${item.status})`);
    deferred.push({ id: item.id, status: item.status, ...exceptions.get(item.id) });
  }
  for (const id of exceptions.keys()) if (!seen.has(id)) throw new Error(`Exception refers to an unknown case: ${id}`);
  if (run.tests.some(test => test.status !== 'passed' && !(
    test.status === 'skipped' && ['air-browser', 'design-browser'].includes(test.suite) &&
    exceptions.has(test.name?.replace(/^Chromium rendered /, '')) &&
    run.cases.find(item => item.id === test.name?.replace(/^Chromium rendered /, ''))?.status === 'skipped'
  ))) throw new Error('A test failed or was skipped without an exact browser-case exception');
  if ((deferred.length > 0) !== (run.status === 'partial'))
    throw new Error('Fast report status does not match deferred cases');
  return { schemaVersion: 1, status: 'passed', scope: 'required-release-checks',
    targetScope: deferred.length ? 'maks-demo-only' : 'all-environments',
    revision, bddCoverageStatus: run.status, coverageExceptions: deferred };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const [reportFile, revision, policyFile, registryFile, outputFile] = process.argv.slice(2);
    if (!reportFile || !revision || !policyFile || !registryFile || !outputFile) throw new Error('usage: verify-fast-report.mjs REPORT REVISION POLICY REGISTRY OUTPUT');
    const run = JSON.parse(readFileSync(reportFile, 'utf8'));
    const policyBytes = readFileSync(policyFile);
    const result = verifyFastReport(run, revision, JSON.parse(policyBytes), JSON.parse(readFileSync(registryFile, 'utf8')));
    result.policySHA256 = createHash('sha256').update(policyBytes).digest('hex');
    writeFileSync(outputFile, JSON.stringify(result, null, 2) + '\n');
  } catch (error) { console.error(String(error)); process.exitCode = 1; }
}

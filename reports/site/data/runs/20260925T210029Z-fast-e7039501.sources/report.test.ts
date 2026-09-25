import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const report = readFileSync(join(process.cwd(), '../../reports/site/index.html'), 'utf8');
const script = report.match(/<script>([\s\S]*)<\/script>/)?.[1];

type ReportCase = { id: string; area: string; title: string; status?: string };
type Run = { id: string; label: string; createdAt: string; status: string; timing: { wallMs: number }; cases: ReportCase[] };

function run(id: string, createdAt: string, status: string, cases: ReportCase[]): Run {
  return { id, label: id, createdAt, status: 'passed', timing: { wallMs: 12 }, cases: cases.map(item => ({ ...item, status })) };
}

async function render(cases: ReportCase[], index: Array<string | { path: string; id: string; label: string; createdAt: string; revision: string; status: string }>, runs: Record<string, Run>) {
  if (!script) throw new Error('Report inline script is missing.');
  const page = new DOMParser().parseFromString(report, 'text/html');
  page.querySelector('script')?.remove();
  document.head.innerHTML = page.head.innerHTML;
  document.body.innerHTML = page.body.innerHTML;
  const payloads: Record<string, unknown> = {
    './cases.json': { cases },
    './data/index.json': { runs: index },
    ...Object.fromEntries(Object.entries(runs).map(([path, value]) => [`./data/${path}`, value])),
  };
  const fetch = vi.fn(async (path: string) => {
    if (!(path in payloads)) throw new Error(`Unexpected report fetch: ${path}`);
    return { json: async () => payloads[path] };
  });
  vi.stubGlobal('fetch', fetch);
  window.eval(`(()=>{${script}})()`);
  await new Promise(resolve => window.setTimeout(resolve, 0));
  return { fetch };
}

afterEach(() => { vi.unstubAllGlobals(); document.head.innerHTML = ''; document.body.innerHTML = ''; });

describe('report dashboard regressions', () => {
  it('REPORT-001 keeps the scenario column and every section heading horizontally sticky', async () => {
    const cases = [{ id: 'UI-001', area: 'ui', title: 'Вход в сканирование' }];
    await render(cases, ['runs/one.json'], { 'runs/one.json': run('one', '2026-09-19T10:00:00Z', 'passed', cases) });
    expect(report).toMatch(/\.scenario-column\{[^}]*position:sticky;left:0/);
    expect(report).toMatch(/\.scenario-column\{[^}]*width:290px;min-width:290px;max-width:290px/);
    expect(document.querySelector('#head .scenario-column')?.textContent).toBe('Сценарий');
    expect(document.querySelector('#body .scenario-column:not(.section-column)')?.textContent).toContain('UI-001');
    const headings = [...document.querySelectorAll('#body .section-column')].map(heading => heading.textContent?.trim());
    expect(headings).toEqual(['Поведение', 'DatabaseDB-001…005 требуют отдельного реального PostgreSQL-свидетельства; их внешнее время не входит в «Весь запуск».', 'Security', 'Конкурсный API — контрактПроверки подтверждают адаптер API, а не качество модели.', 'Дизайн']);
  });

  it('groups database scenarios under a sticky Database heading', async () => {
    const cases = [
      { id: 'DB-001', area: 'database', title: 'Миграции' },
      { id: 'DB-006', area: 'database', title: 'Недоступная БД' },
      { id: 'UI-001', area: 'web', title: 'Вход' },
    ];
    await render(cases, ['runs/one.json'], { 'runs/one.json': run('one', '2026-09-19T10:00:00Z', 'passed', cases) });
    const heading = [...document.querySelectorAll('#body .section-column')].find(item => item.textContent?.startsWith('Database'));
    expect(heading).toHaveClass('scenario-column');
    expect(heading?.textContent).toContain('DB-001…005');
    const databaseRows = [...document.querySelectorAll('#body tr')].filter(row => row.querySelector('strong')?.textContent?.startsWith('DB-00'));
    expect(databaseRows).toHaveLength(2);
    expect(databaseRows.every(row => row.querySelector('.scenario-column'))).toBe(true);
  });


  it('groups service and recommendation cases separately from model quality', async () => {
    const cases = [{ id: 'SVC-001', area: 'services', title: 'Поиск' }, { id: 'REC-001', area: 'services', title: 'Рекомендации' }];
    await render(cases, ['runs/one.json'], { 'runs/one.json': run('one', '2026-09-21T10:00:00Z', 'passed', cases) });
    const heading = [...document.querySelectorAll('#body .section-column')].find(item => item.textContent?.startsWith('Поиск и рекомендации'));
    expect(heading).toHaveClass('scenario-column');
    expect(heading?.textContent).toContain('качество ML проверяется отдельно');
    expect(heading?.parentElement?.nextElementSibling?.textContent).toContain('SVC-001');
    expect(heading?.parentElement?.nextElementSibling?.nextElementSibling?.textContent).toContain('REC-001');
  });

  it('REPORT-002 orders an unordered index from newest run to the baseline', async () => {
    const cases = [{ id: 'UI-001', area: 'ui', title: 'Вход в сканирование' }];
    await render(cases, ['runs/middle.json', 'runs/baseline.json', 'runs/new.json'], {
      'runs/baseline.json': run('baseline', '2026-09-19T00:00:00Z', 'not_run', cases),
      'runs/middle.json': run('middle', '2026-09-19T09:00:00Z', 'passed', cases),
      'runs/new.json': run('new', '2026-09-19T12:00:00Z', 'passed', cases),
    });
    expect([...document.querySelectorAll('#head button')].map(button => button.textContent)).toEqual(['new', 'middle', 'baseline']);
    expect(document.querySelector('.summary-label span')?.textContent).toContain('new');
  });

  it('REPORT-003 summarizes only the latest run and keeps skipped cases out of green success cells', async () => {
    const cases = [
      { id: 'UI-001', area: 'ui', title: 'Пройденный кейс' },
      { id: 'UI-002', area: 'ui', title: 'Пропущенный кейс' },
    ];
    const newest: Run = {
      id: 'new', label: 'new', createdAt: '2026-09-19T12:00:00Z', status: 'partial', timing: { wallMs: 12 },
      cases: [{ ...cases[0], status: 'passed' }, { ...cases[1], status: 'skipped' }],
    };
    const old = run('old-failure', '2026-09-19T09:00:00Z', 'failed', cases);
    await render(cases, ['runs/old.json', 'runs/new.json'], { 'runs/old.json': old, 'runs/new.json': newest });
    const metrics = Object.fromEntries([...document.querySelectorAll('.metric')].map(metric => [metric.querySelector('span')?.textContent, metric.querySelector('b')?.textContent]));
    expect(metrics).toMatchObject({ 'Всего кейсов': '2', 'Пройдено': '1', 'Ошибки/падения': '0', 'Пропущено': '1', 'Не запускалось': '0' });
    const skipped = document.querySelector('button.cell.skipped');
    expect(skipped).not.toBeNull();
    expect(skipped).not.toHaveClass('passed');
    expect(getComputedStyle(skipped!).backgroundColor).not.toBe('rgb(220, 238, 221)');
  });
});

it('REPORT-004 preserves a backend failure when UI passes the same behavior and records all IDs', async () => {
  const {goCases, mergeCases} = await import('../../../scripts/report-results.mjs');
  const backend = goCases(JSON.stringify({Test:'TestCAT001PaginationAndCAT002WholeCatalogQuery',Action:'fail',Elapsed:.002}));
  expect([...backend.keys()]).toEqual(['CAT-001','CAT-002']);
  const ui = new Map([['CAT-002',{status:'passed',tests:[{name:'UI full-catalog search'}]}]]);
  for (const result of [mergeCases(backend,ui),mergeCases(ui,backend)]) {
    expect(result.get('CAT-002')?.status).toBe('failed');
    expect(result.get('CAT-002')?.tests).toHaveLength(2);
  }
});

it('REPORT-005 loads 2000 revisions and scenario rows in bounded portions without hiding the latest failure', async () => {
  const cases = Array.from({ length: 41 }, (_, n) => ({ id: `UI-${String(n + 1).padStart(3, '0')}`, area: 'ui', title: `Сценарий ${n + 1}` }));
  const index = Array.from({ length: 2000 }, (_, n) => ({
    path: `runs/rev-${String(n).padStart(4, '0')}.json`, id: `rev-${n}`, label: `Ревизия ${n}`,
    createdAt: new Date(Date.UTC(2026, 8, 1, 0, n)).toISOString(), revision: `sha-${n}`, status: 'passed',
  })).reverse();
  const payloads: Record<string, Run> = {};
  for (let n = 1990; n < 2000; n++) {
    const selected = n === 1999 ? cases : cases.slice(0, 40);
    payloads[`runs/rev-${String(n).padStart(4, '0')}.json`] = {
      id: `rev-${n}`, label: `Ревизия ${n}`, createdAt: index[1999 - n].createdAt,
      status: n === 1999 ? 'failed' : 'passed', timing: { wallMs: 12 },
      cases: selected.map((item, i) => ({ ...item, status: n === 1999 && i === 40 ? 'failed' : 'passed' })),
    };
  }
  const { fetch } = await render(cases, index, payloads);
  expect(fetch.mock.calls.filter(([path]) => String(path).includes('/runs/'))).toHaveLength(5);
  expect(document.querySelectorAll('#head button')).toHaveLength(5);
  expect(document.querySelectorAll('#body button.cell')).toHaveLength(40 * 5);
  expect(document.querySelector('#runs-range')?.textContent).toContain('5 из 2000');
  expect(document.querySelector('#cases-range')?.textContent).toContain('40 из 41');
  expect(document.querySelector('#summary')?.textContent).toContain('Ошибки/падения');
  expect([...document.querySelectorAll('.metric')].find(el => el.textContent?.includes('Ошибки/падения'))?.querySelector('b')?.textContent).toBe('1');
  const moreRuns = document.querySelector<HTMLButtonElement>('#more-runs')!;
  moreRuns.click(); moreRuns.click();
  await new Promise(resolve => window.setTimeout(resolve, 0));
  expect(fetch.mock.calls.filter(([path]) => String(path).includes('/runs/'))).toHaveLength(10);
  expect(document.querySelectorAll('#head button')).toHaveLength(10);
  document.querySelector<HTMLButtonElement>('#more-cases')!.click();
  expect(document.querySelectorAll('#body button.cell')).toHaveLength(41 * 10);
  const finalRow = [...document.querySelectorAll('#body tr')].find(row => row.querySelector('strong')?.textContent === 'UI-041')!;
  expect(finalRow.querySelectorAll('button.cell')[0]).toHaveClass('failed');
  expect(finalRow.querySelectorAll('button.cell')[1]).toHaveClass('not_run');
});

it('REPORT-005 keeps selected details and the latest summary when an older revision fails to load, then retries', async () => {
  const cases = [{ id: 'UI-001', area: 'ui', title: 'Вход в сканирование' }];
  const index = Array.from({ length: 7 }, (_, n) => ({
    path: `runs/rev-${n}.json`, id: `rev-${n}`, label: `Ревизия ${n}`,
    createdAt: new Date(Date.UTC(2026, 8, 1, 0, n)).toISOString(), revision: `sha-${n}`, status: 'passed',
  })).reverse();
  const payloads = Object.fromEntries(index.map(entry => [entry.path, run(entry.id, entry.createdAt, 'passed', cases)]));
  const { fetch } = await render(cases, index, payloads);
  document.querySelector<HTMLButtonElement>('#body button.cell')!.click();
  const detail = document.querySelector('#detail')!.textContent;
  const summary = document.querySelector('#summary')!.textContent;
  const originalFetch = fetch.getMockImplementation()!;
  let rejectOlder = true;
  fetch.mockImplementation(async (path: string) => {
    if (path === './data/runs/rev-1.json' && rejectOlder) throw new Error('HTTP 503');
    return originalFetch(path);
  });
  document.querySelector<HTMLButtonElement>('#more-runs')!.click();
  await new Promise(resolve => window.setTimeout(resolve, 0));
  expect(document.querySelectorAll('#head button')).toHaveLength(5);
  expect(document.querySelector('#detail')?.textContent).toBe(detail);
  expect(document.querySelector('#summary')?.textContent).toBe(summary);
  expect(document.querySelector('#load-status')?.textContent).toContain('Повторите попытку');
  rejectOlder = false;
  document.querySelector<HTMLButtonElement>('#more-runs')!.click();
  await new Promise(resolve => window.setTimeout(resolve, 0));
  expect(document.querySelectorAll('#head button')).toHaveLength(7);
  expect(document.querySelector('#detail')?.textContent).toBe(detail);
  expect(document.querySelector('#summary')?.textContent).toBe(summary);
  expect(document.querySelector('#load-status')?.textContent).toBe('');
});

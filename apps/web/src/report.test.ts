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

async function render(cases: ReportCase[], index: string[], runs: Record<string, Run>) {
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
  it('REPORT-001 marks only the scenario column as horizontally sticky', async () => {
    const cases = [{ id: 'UI-001', area: 'ui', title: 'Вход в сканирование' }];
    await render(cases, ['runs/one.json'], { 'runs/one.json': run('one', '2026-09-19T10:00:00Z', 'passed', cases) });
    expect(report).toMatch(/\.scenario-column\{[^}]*position:sticky;left:0/);
    expect(document.querySelector('#head .scenario-column')?.textContent).toBe('Сценарий');
    expect(document.querySelector('#body .scenario-column')?.textContent).toContain('UI-001');
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

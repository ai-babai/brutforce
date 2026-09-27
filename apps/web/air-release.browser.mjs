#!/usr/bin/env node
// Rendered, mocked-transport evidence for the audited Air release cases.
// One JSON object is printed even when an individual assertion fails.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const root = resolve(import.meta.dirname, '../..');
export const evidenceSources = [
  'apps/web/air-release.browser.mjs', 'apps/web/src/App.tsx',
  'apps/web/src/air.css', 'apps/web/src/v2.css',
  'design/wine-ux-v3/air/behavior-v3.feature',
  'design/wine-ux-v3/air37/behavior-v37.feature',
];
async function sourceDigest() {
  const hash = createHash('sha256');
  for (const source of evidenceSources) {
    hash.update(source).update('\0').update(await readFile(resolve(root, source))).update('\0');
  }
  return hash.digest('hex');
}

const first = { id: 'first', name: 'Первое вино с длинным различающим названием', winery: 'Первая винодельня',
  year: 2021, image: '/assets/concept-bottle.png', description: 'Описание первого вина.' };
const second = { ...first, id: 'second', name: 'Второе вино', winery: 'Вторая винодельня', year: 2022 };
const receipt = { id: 'a'.repeat(32), createdAt: '2026-09-28T00:00:00Z', bytes: 1, mime: 'image/png', width: 1, height: 1 };
const results = [];
let browser;
let server;

async function checked(id, complete, reason, run) {
  const start = performance.now();
  try {
    const detail = await run();
    results.push({ id, status: complete ? 'passed' : 'skipped', reason: complete ? 'Rendered Chromium scenario passed.' : reason,
      detail, durationMs: Math.round(performance.now() - start) });
  } catch (error) {
    results.push({ id, status: 'failed', reason: String(error?.stack || error),
      durationMs: Math.round(performance.now() - start) });
  }
}

async function context(width = 320, height = 640, reducedMotion = 'no-preference') {
  const ctx = await browser.newContext({ viewport: { width, height }, reducedMotion });
  await ctx.route('**/v2/catalog**', route => route.fulfill({ json: { demo: false, catalogVersion: 'fixture', candidates: [first, second] } }));
  await ctx.route('**/v1/recommendations**', route => route.fulfill({ json: { demo: false, candidates: [] } }));
  await ctx.route('**/v1/photos', route => route.fulfill({ status: 201, json: receipt }));
  await ctx.route('**/v1/search', route => route.fulfill({ json: { demo: false, candidates: [first, second] } }));
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:5192/');
  return { ctx, page };
}

async function photoResults(page) {
  const picker = page.locator('input[aria-label="Загрузить фотографию этикетки"]');
  await picker.setInputFiles({ name: 'fixture.png', mimeType: 'image/png',
    buffer: await readFile(resolve(root, 'apps/web/public/assets/concept-bottle.png')) });
  await page.locator('#UI-006 .candidate-list button').first().waitFor();
  await page.locator('#UI-006 .candidate-list button').first().locator('img').evaluate(image => image.decode());
}

const geometry = () => {
  const app = document.querySelector('.app').getBoundingClientRect();
  const page = document.querySelector('#UI-006').getBoundingClientRect();
  const list = [...document.querySelectorAll('#UI-006 .candidate-list button')];
  const leader = list[0];
  const box = leader.getBoundingClientRect();
  const style = getComputedStyle(leader);
  const image = leader.querySelector('img');
  return { app: app.toJSON(), page: page.toJSON(), leader: box.toJSON(),
    list: list.map(el => ({ name: el.getAttribute('aria-label'), box: el.getBoundingClientRect().toJSON() })),
    borderLeft: style.borderLeftWidth, borderRight: style.borderRightWidth, radius: style.borderRadius,
    background: style.backgroundImage, imageLoaded: !!image && image.complete && image.naturalWidth > 0,
    imageBox: image?.getBoundingClientRect().toJSON(), textBox: leader.querySelector('span').getBoundingClientRect().toJSON(),
    nextTextBox: list[1].querySelector('span').getBoundingClientRect().toJSON(),
    overflow: document.documentElement.scrollWidth > innerWidth,
    clipped: list.some(el => el.scrollWidth > el.clientWidth),
  };
};

try {
  server = await createServer({ server: { host: '127.0.0.1', port: 5192, strictPort: true } });
  await server.listen();
  browser = await chromium.launch();

  await checked('AIR-026', true, '', async () => {
    const detail = [];
    for (const [width, height] of [[320, 640], [430, 932], [844, 390]]) {
      const { ctx, page } = await context(width, height);
      try {
        await photoResults(page);
        const m = await page.evaluate(geometry);
        assert.equal(m.list.length, 2);
        assert.deepEqual(m.list.map(row => row.name), [first.name + ', 2021', second.name + ', 2022']);
        assert.ok(Math.abs(m.leader.left - m.app.left) <= 1 && Math.abs(m.leader.right - m.app.right) <= 1,
          `${width}: leader must touch both inner app edges: ${JSON.stringify(m)}`);
        assert.equal(m.borderLeft, '0px'); assert.equal(m.borderRight, '0px');
        assert.equal(m.radius, '0px');
        assert.notEqual(m.background, 'none');
        assert.ok(m.imageLoaded && !m.overflow && !m.clipped, `${width}: loaded image or readable list: ${JSON.stringify(m)}`);
        assert.ok(m.imageBox.right < m.textBox.left && Math.abs(m.textBox.right - m.nextTextBox.right) <= 3,
          `${width}: image and text alignment: ${JSON.stringify(m)}`);
        await page.locator('#UI-006 .candidate-list button').nth(1).click();
        await page.locator('#UI-007').waitFor();
        assert.match(await page.locator('#UI-007 h2').innerText(), /Второе вино/);
        detail.push(`${width}×${height}: edge-to-edge loaded leader, ordered selectable rows`);
      } finally { await ctx.close(); }
    }
    return detail;
  });

  await checked('AIR-027', true, '', async () => {
    const detail = [];
    for (const motion of ['no-preference', 'reduce']) {
      const { ctx, page } = await context(390, 844, motion);
      const nav = page.locator('.bottom-nav');
      async function inspect(section, screen) {
        await page.locator(screen).waitFor();
        await page.waitForTimeout(motion === 'reduce' ? 0 : 360);
        const state = await nav.evaluate(el => {
          const buttons = [...el.querySelectorAll('button')];
          const slider = el.querySelectorAll('.nav-slider');
          const s = slider[0].getBoundingClientRect();
          return { section: el.dataset.section, current: buttons.map(b => b.getAttribute('aria-current')),
            sliderCount: slider.length, sliderX: s.x, buttonXs: buttons.map(b => b.getBoundingClientRect().x),
            transition: getComputedStyle(slider[0]).transitionDuration };
        });
        const index = { scanner: 0, search: 1, saved: 2 }[section];
        assert.equal(state.section, section);
        assert.equal(state.sliderCount, 1);
        assert.deepEqual(state.current, [0, 1, 2].map(i => i === index ? 'page' : null));
        assert.ok(Math.abs(state.sliderX - state.buttonXs[index]) < 3, `${motion}/${section}: ${JSON.stringify(state)}`);
        if (motion === 'reduce') assert.equal(state.transition, '0s');
        else assert.notEqual(state.transition, '0s');
        detail.push(`${motion}/${section}`);
      }
      try {
        await inspect('scanner', '#UI-001');
        const startingX = await nav.locator('.nav-slider').evaluate(el => el.getBoundingClientRect().x);
        await nav.getByRole('button', { name: 'Поиск' }).click();
        if (motion === 'no-preference') {
          await page.waitForTimeout(80);
          const movingX = await nav.locator('.nav-slider').evaluate(el => el.getBoundingClientRect().x);
          const targetX = await nav.getByRole('button', { name: 'Поиск' }).evaluate(el => el.getBoundingClientRect().x);
          assert.ok(movingX > startingX + 2 && movingX < targetX - 2,
            `ordinary tab transition did not visibly move: ${JSON.stringify({ startingX, movingX, targetX })}`);
        }
        await inspect('search', '#UI-008');
        await nav.getByRole('button', { name: 'Сохранённое' }).click();
        await inspect('saved', '#UI-016');
        await nav.getByRole('button', { name: 'Поиск' }).click();
        await nav.getByRole('button', { name: 'Главная' }).click();
        await inspect('scanner', '#UI-001');
      } finally { await ctx.close(); }
    }
    return detail;
  });

  await checked('AIR-021', false, 'Partial: rendered candidate actions and keyboard focus checked; search and recovery branches plus consistent 200% text remain unverified.', async () => {
    const { ctx, page } = await context();
    try {
      await photoResults(page);
      const actions = page.locator('#UI-006 button:visible');
      const sizes = await actions.evaluateAll(nodes => nodes.map(el => ({ label: el.getAttribute('aria-label') || el.textContent.trim(),
        width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })));
      assert.ok(sizes.length >= 5 && sizes.every(x => x.label && x.width >= 44 && x.height >= 44), JSON.stringify(sizes));
      const photoActions = sizes.filter(x => /снимок|Галерея/.test(x.label));
      assert.equal(photoActions.length, 2);
      assert.ok(photoActions.every(x => x.width >= 48 && x.height >= 52), JSON.stringify(photoActions));
      await page.locator('#UI-006 .candidate-list button').first().focus();
      const focus = await page.locator('#UI-006 .candidate-list button').first().evaluate(el => ({
        active: document.activeElement === el, outline: getComputedStyle(el).outlineStyle,
        width: getComputedStyle(el).outlineWidth }));
      assert.ok(focus.active && focus.outline !== 'none' && focus.width !== '0px', JSON.stringify(focus));
      await page.keyboard.press('Enter');
      await page.locator('#UI-007').waitFor();
      return { sizes, focus };
    } finally { await ctx.close(); }
  });

  await checked('AIR-028', false, 'Partial: primary buttons in Home, Saved and photo recovery checked; camera, waiting, card and consistent 200% text are not fully observable here.', async () => {
    const { ctx, page } = await context();
    const styles = [];
    async function collect(screen) {
      const entry = await page.locator(`${screen} .primary`).first().evaluate(el => {
        const s = getComputedStyle(el); return { family: s.fontFamily, size: s.fontSize, weight: s.fontWeight, line: s.lineHeight };
      });
      styles.push(entry);
    }
    try {
      await collect('#UI-001');
      await page.locator('.bottom-nav').getByRole('button', { name: 'Сохранённое' }).click();
      await collect('#UI-016');
      await photoResults(page);
      await page.locator('#UI-006').getByRole('button', { name: 'Ни одно не подходит' }).click();
      await collect('#UI-009');
      assert.ok(styles.length === 3 && styles.every(s => JSON.stringify(s) === JSON.stringify(styles[0])), JSON.stringify(styles));
      return styles;
    } finally { await ctx.close(); }
  });

  await checked('AIR-029', false, 'Partial: direct Home entries, grouping and short Chromium viewport checked; approved mascot size comparison and physical safe areas remain unverified.', async () => {
    const { ctx, page } = await context(320, 568);
    try {
      const home = await page.locator('#UI-001').evaluate(el => {
        const scene = el.querySelector('.hero .mascot-scene').getBoundingClientRect();
        const actions = el.querySelector('.actions').getBoundingClientRect();
        const buttons = [...el.querySelectorAll('.actions button')].map(b => b.getBoundingClientRect().toJSON());
        const nav = document.querySelector('.bottom-nav').getBoundingClientRect();
        return { scene: scene.toJSON(), actions: actions.toJSON(), buttons, nav: nav.toJSON(),
          hintCount: [...el.querySelectorAll('*')].filter(x => x.children.length === 0 && /Этикетка целиком|нужная бутылка по центру/i.test(x.textContent)).length,
          scrollHeight: document.querySelector('.app-content').scrollHeight,
          clientHeight: document.querySelector('.app-content').clientHeight };
      });
      assert.equal(home.buttons.length, 3);
      assert.equal(home.hintCount, 0);
      assert.ok(home.scene.bottom <= home.actions.top + 12 && home.actions.top < home.buttons[0].top + 1, JSON.stringify(home));
      assert.ok(home.buttons.every(b => b.height >= 48), JSON.stringify(home));
      await page.locator('#UI-001 .split-actions button').last().scrollIntoViewIfNeeded();
      const finalAction = await page.locator('#UI-001 .split-actions button').last().boundingBox();
      const navTop = (await page.locator('.bottom-nav').boundingBox()).y;
      assert.ok(finalAction.y + finalAction.height <= navTop + 1, `short viewport action hidden behind nav: ${JSON.stringify({ finalAction, navTop })}`);
      const [chooser] = await Promise.all([
        page.waitForEvent('filechooser'),
        page.locator('#UI-001 .split-actions button').first().click(),
      ]);
      assert.equal(await chooser.element().getAttribute('aria-label'), 'Загрузить фотографию этикетки');
      await page.getByRole('button', { name: 'По названию' }).first().click();
      await page.locator('#UI-008').waitFor();
      await page.locator('.bottom-nav').getByRole('button', { name: 'Главная' }).click();
      await page.locator('#UI-001').waitFor();
      await page.locator('#UI-001 .scan-button').click();
      await page.locator('#UI-002, #UI-003').first().waitFor();
      if (await page.locator('#UI-002').count()) assert.match(await page.locator('.camera-header').innerText(), /Нужная бутылка по центру/);
      return home;
    } finally { await ctx.close(); }
  });

  await checked('AIR-043', true, '', async () => {
    const sourceUrl = 'https://vino-svoe.example/wines/first';
    const a = { ...first, sourceUrl };
    const b = { ...second };
    const c = { ...first, id: 'saved-unsafe', name: 'Сохранённое без источника', sourceUrl: 'javascript:alert(1)' };
    const branches = [];
    for (const token of [undefined, 'b'.repeat(32)]) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
      const feedback = [];
      let photoSearches = 0;
      try {
        await ctx.addInitScript(wine => localStorage.setItem('wine-demo-saved-v1', JSON.stringify([wine])), c);
        await ctx.route('**/v1/feedback**', route => { feedback.push(route.request().url()); return route.fulfill({ status: 500 }); });
        await ctx.route('**/v2/catalog**', route => route.fulfill({ json: { demo: false, catalogVersion: 'fixture', candidates: [a, b] } }));
        await ctx.route('**/v1/recommendations**', route => route.fulfill({ json: { demo: false, candidates: [] } }));
        await ctx.route('**/v1/photos', route => route.fulfill({ status: 201, json: receipt }));
        await ctx.route('**/v1/search', route => route.fulfill({ json: {
          demo: false, candidates: ++photoSearches === 3 ? [] : [a, b],
          ...(token ? { feedbackToken: token } : {}),
        } }));
        await ctx.route(sourceUrl, route => route.fulfill({ contentType: 'text/html', body: '<title>Source</title>' }));
        const page = await ctx.newPage();
        page.on('request', request => { if (new URL(request.url()).pathname === '/v1/feedback') feedback.push(request.url()); });
        await page.goto('http://127.0.0.1:5192/');
        async function noAnnotation(screen) {
          await page.locator(screen).waitFor();
          assert.equal(await page.locator('.photo-feedback, .feedback-correction, .correction').count(), 0);
          assert.equal(feedback.length, 0);
        }
        async function upload() {
          await page.locator('input[aria-label="Загрузить фотографию этикетки"]').setInputFiles({
            name: 'fixture.png', mimeType: 'image/png',
            buffer: await readFile(resolve(root, 'apps/web/public/assets/concept-bottle.png')),
          });
        }
        await upload();
        await noAnnotation('#UI-006');
        await page.locator('#UI-006 .candidate-list button').first().click();
        await noAnnotation('#UI-007');
        const link = page.locator('#UI-007 .result-source');
        assert.equal(await link.getAttribute('href'), sourceUrl);
        assert.equal(await link.getAttribute('target'), '_blank');
        assert.match(await link.getAttribute('rel'), /\bnoopener\b/);
        assert.match(await link.getAttribute('rel'), /\bnoreferrer\b/);
        const [popup] = await Promise.all([page.waitForEvent('popup'), link.click()]);
        assert.equal(popup.url(), sourceUrl);
        assert.equal(await popup.evaluate(() => window.opener), null);
        assert.equal(await page.locator('#UI-007 h2').innerText(), a.name);
        await popup.close();
        await noAnnotation('#UI-007');
        await page.locator('#UI-007').getByRole('button', { name: 'Назад' }).click();
        await noAnnotation('#UI-006');
        await page.locator('#UI-006 .candidate-list button').nth(1).click();
        await noAnnotation('#UI-007');
        assert.equal(await page.locator('.result-source').count(), 0);
        await page.locator('.bottom-nav').getByRole('button', { name: 'Сохранённое' }).click();
        await noAnnotation('#UI-016');
        await page.locator('#UI-016 .candidate-list button').first().click();
        await noAnnotation('#UI-007');
        assert.equal(await page.locator('.result-source').count(), 0);
        await page.locator('.bottom-nav').getByRole('button', { name: 'Главная' }).click();
        await upload();
        await noAnnotation('#UI-006');
        await page.locator('#UI-006').getByRole('button', { name: 'Ни одно не подходит' }).click();
        await noAnnotation('#UI-009');
        await page.locator('#UI-009').getByRole('button', { name: 'Найти по названию' }).click();
        await noAnnotation('#UI-008');
        await page.getByLabel(/Название вина/).fill('Первое');
        await page.locator('#UI-008 .candidate-list button').first().waitFor();
        await noAnnotation('#UI-008');
        await page.locator('#UI-008 .candidate-list button').first().click();
        await noAnnotation('#UI-007');
        await page.locator('.bottom-nav').getByRole('button', { name: 'Главная' }).click();
        await upload();
        await noAnnotation('#UI-009');
        await page.locator('#UI-009').getByRole('button', { name: 'Найти по названию' }).click();
        await noAnnotation('#UI-008');
        await page.getByLabel(/Название вина/).fill('Первое');
        await page.locator('#UI-008 .candidate-list button').first().click();
        await noAnnotation('#UI-007');
        assert.equal(photoSearches, 3);
        assert.equal(feedback.length, 0);
        branches.push(token ? 'token-present' : 'token-absent');
      } finally { await ctx.close(); }
    }
    return branches;
  });
} catch (error) {
  // Infrastructure failure must be visible to the report consumer.
  results.push({ id: 'BROWSER-RUNNER', status: 'error', reason: String(error?.stack || error) });
} finally {
  await browser?.close().catch(() => {});
  await server?.close().catch(() => {});
}

console.log(JSON.stringify({ schemaVersion: 1, runner: 'air-release-browser', revision: process.env.GIT_REVISION || 'working-tree',
  sourceDigest: await sourceDigest(), sources: evidenceSources, browser: 'Chromium (Playwright)',
  transport: 'local Vite with mocked /v1 and /v2 responses', cases: results }));
if (results.some(result => ['failed', 'error'].includes(result.status))) process.exitCode = 1;

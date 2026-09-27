#!/usr/bin/env node
// Rendered Air regression evidence for historical DESIGN IDs. Mocked HTTP proves
// UI behavior and layout only; it does not prove ML quality or physical devices.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const root = resolve(import.meta.dirname, '../..');
const sources = ['apps/web/design-release.browser.mjs', 'apps/web/src/App.tsx',
  'apps/web/src/air.css', 'apps/web/src/v2.css', 'apps/web/design-specs.md',
  'apps/web/public/assets/concept-bottle.png'];
const ids = ['DESIGN-001', 'DESIGN-002', 'DESIGN-004', 'DESIGN-006', 'DESIGN-008',
  'DESIGN-009', 'DESIGN-010', 'DESIGN-011', 'DESIGN-013', 'DESIGN-014',
  'DESIGN-015', 'DESIGN-016', 'DESIGN-018', 'DESIGN-020', 'DESIGN-022',
  'DESIGN-023', 'DESIGN-025', 'DESIGN-026'];
const wine = { id: 'long', name: 'Коллекционное игристое вино из виноградников южного склона с выдержкой в бутылке и редким купажом',
  winery: 'Первая винодельня', year: 2024, image: '/assets/concept-bottle.png',
  description: 'Описание первого вина.', sugar: 'сухое', alcoholPercent: 12,
  region: ['Кубань'], sourceUrl: 'https://vino-svoe.ru/wines/fixture' };
const other = { ...wine, id: 'other', name: 'Мерло', winery: 'Вторая винодельня', year: 2023 };
const receipt = { id: 'a'.repeat(32), createdAt: '2026-09-28T00:00:00Z',
  bytes: 1, mime: 'image/png', width: 1, height: 1 };
const cases = [];
let browser;
let server;
let baseUrl;

async function digest() {
  const hash = createHash('sha256');
  for (const source of sources) hash.update(source).update('\0').update(await readFile(resolve(root, source))).update('\0');
  return hash.digest('hex');
}
async function check(id, run) {
  const start = performance.now();
  try {
    const detail = await run();
    cases.push({ id, status: 'passed', reason: 'Rendered Chromium assertions passed.', detail,
      durationMs: Math.round(performance.now() - start) });
  } catch (error) {
    cases.push({ id, status: 'failed', reason: String(error?.stack || error),
      durationMs: Math.round(performance.now() - start) });
  }
}
async function partial(id, reason, run) {
  const start = performance.now();
  try {
    const detail = await run();
    cases.push({ id, status: 'skipped', reason, detail,
      durationMs: Math.round(performance.now() - start) });
  } catch (error) {
    cases.push({ id, status: 'failed', reason: String(error?.stack || error),
      durationMs: Math.round(performance.now() - start) });
  }
}
function skip(id, reason, detail) {
  cases.push({ id, status: 'skipped', reason, detail, durationMs: 0 });
}
async function fixturePage(width = 390, height = 844, search = [wine, other]) {
  const context = await browser.newContext({ viewport: { width, height }, permissions: ['camera'] });
  await context.route('**/v2/catalog**', route => route.fulfill({ json: {
    demo: false, catalogVersion: 'design-fixture', candidates: [wine, other] } }));
  await context.route('**/v1/recommendations**', route => route.fulfill({ json: { demo: false, candidates: [] } }));
  await context.route('**/v1/photos', route => route.fulfill({ status: 201, json: receipt }));
  await context.route('**/v1/search', route => route.fulfill({ json: { demo: false, candidates: search } }));
  const page = await context.newPage();
  await page.addInitScript(() => { window.rect = el => el.getBoundingClientRect().toJSON(); });
  await page.goto(baseUrl);
  await page.locator('#UI-001').waitFor();
  return { context, page };
}
async function withPage(width, height, run) {
  const { context, page } = await fixturePage(width, height);
  try { return await run(page); } finally { await context.close(); }
}
async function photoResults(page) {
  await page.locator('input[aria-label="Загрузить фотографию этикетки"]').setInputFiles({
    name: 'fixture.png', mimeType: 'image/png',
    buffer: await readFile(resolve(root, 'apps/web/public/assets/concept-bottle.png')) });
  await page.locator('#UI-006 .candidate-list button').first().waitFor();
}
async function catalog(page) {
  await page.locator('#UI-001').getByRole('button', { name: 'По названию' }).click();
  await page.locator('#UI-008').getByRole('button', { name: 'Открыть каталог' }).click();
  await page.locator('#UI-008 .candidate-list button').first().waitFor();
}
try {
  server = await createServer({ server: { host: '127.0.0.1', port: 0, strictPort: true } });
  await server.listen();
  baseUrl = `http://127.0.0.1:${server.httpServer.address().port}/`;
  browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });

  await partial('DESIGN-001', 'Rendered palette sample passed, but recovery surfaces and interaction states are not yet measured.', () => withPage(390, 844, async page => {
    const home = await page.evaluate(() => {
      const style = selector => getComputedStyle(document.querySelector(selector));
      return { paper: style('.app').backgroundColor, cta: style('.scan-button').backgroundColor,
        ink: style('#UI-001 h1').color, warm: style('#UI-001').backgroundImage };
    });
    assert.equal(home.paper, 'rgb(254, 253, 250)');
    assert.equal(home.cta, 'rgb(143, 61, 66)');
    assert.ok(home.warm.includes('linear-gradient'), JSON.stringify(home));
    await page.locator('.bottom-nav').getByRole('button', { name: 'Поиск' }).click();
    const search = await page.locator('#UI-008').evaluate(el => ({ background: getComputedStyle(el).backgroundColor,
      ink: getComputedStyle(el.querySelector('h2')).color }));
    assert.equal(search.background, 'rgba(0, 0, 0, 0)');
    assert.ok(home.ink && search.ink);
    return { home, search };
  }));

  await partial('DESIGN-002', 'Rendered scan target and direct camera entry passed; 200% text and approved symbol identity remain unverified.', () => withPage(320, 568, async page => {
    const scan = page.locator('#UI-001 .scan-button');
    const state = await scan.evaluate(el => ({ label: el.innerText.trim(), box: rect(el),
      glyphs: [...el.querySelectorAll('svg')].map(rect), clipped: el.scrollWidth > el.clientWidth }));
    assert.equal(state.label, 'Сканировать вино');
    assert.equal(state.glyphs.length, 2);
    assert.ok(state.box.width >= 48 && state.box.height >= 48 && !state.clipped);
    assert.ok(state.glyphs[0].right < state.glyphs[1].left && state.glyphs.every(g => g.width >= 20));
    await scan.click();
    await page.locator('#UI-002, #UI-003').first().waitFor();
    return { ...state, opened: await page.locator('#UI-002').count() ? 'camera' : 'permission recovery' };
  }));

  await partial('DESIGN-004', 'Normal-text short viewports passed; consistent 200% text reachability remains unverified.', async () => {
    const detail = [];
    for (const [width, height] of [[320, 568], [390, 640], [844, 390]]) {
      detail.push(await withPage(width, height, async page => {
        const buttons = page.locator('#UI-001 .actions button');
        assert.equal(await buttons.count(), 3);
        await buttons.last().scrollIntoViewIfNeeded();
        const m = await page.evaluate(() => ({ nav: rect(document.querySelector('.bottom-nav')),
          actions: [...document.querySelectorAll('#UI-001 .actions button')].map(rect),
          overflow: document.documentElement.scrollWidth > innerWidth }));
        assert.ok(!m.overflow && m.actions.every(a => a.left >= 0 && a.right <= width && a.height >= 48), JSON.stringify(m));
        assert.ok(m.actions[2].bottom <= m.nav.top + 1, JSON.stringify(m));
        await buttons.last().click();
        await page.locator('#UI-008').waitFor();
        return { width, height, ...m };
      }));
    }
    return detail;
  });

  await partial('DESIGN-006', 'Natural heading, local display font and base width passed; approved Air typography baseline and 200% text remain unverified.', () => withPage(320, 568, async page => {
    const state = await page.locator('#UI-001 h1').evaluate(el => ({ text: el.textContent.trim(),
      box: rect(el), font: getComputedStyle(el).fontFamily, align: getComputedStyle(el).textAlign,
      clipped: el.scrollWidth > el.clientWidth, forcedBreak: !!el.querySelector('br'),
      fontReady: document.fonts.check(`500 ${getComputedStyle(el).fontSize} ${getComputedStyle(el).fontFamily.split(',')[0]}`) }));
    assert.equal(state.text, 'Какое вино перед вами?');
    assert.ok(/Playfair/.test(state.font) && state.align === 'center' && state.fontReady, JSON.stringify(state));
    assert.ok(!state.clipped && !state.forcedBreak && state.box.left >= 0 && state.box.right <= 320);
    return state;
  }));

  skip('DESIGN-008', 'Chromium fixtures cannot establish physical camera output; accepted-stream video and device evidence are incomplete.');

  await partial('DESIGN-009', 'Ordered named rows and keyboard selection passed; broken-image fallback and enlarged-text wrapping remain unverified.', () => withPage(320, 640, async page => {
    await photoResults(page);
    const rows = page.locator('#UI-006 .candidate-list button');
    const evidence = await rows.evaluateAll(nodes => nodes.map(el => ({ name: el.getAttribute('aria-label'),
      tag: el.tagName, box: rect(el), title: el.querySelector('b')?.textContent,
      clipped: el.scrollWidth > el.clientWidth, image: !!el.querySelector('img, .missing-image') })));
    assert.deepEqual(evidence.map(r => r.name), [`${wine.name}, 2024`, `${other.name}, 2023`]);
    assert.ok(evidence.every(r => r.tag === 'BUTTON' && r.box.width >= 250 && !r.clipped && r.image), JSON.stringify(evidence));
    await rows.nth(1).focus();
    assert.equal(await rows.nth(1).evaluate(el => document.activeElement === el), true);
    await page.keyboard.press('Enter');
    await page.locator('#UI-007').waitFor();
    assert.equal(await page.locator('#UI-007 h2').innerText(), other.name);
    return evidence;
  }));

  skip('DESIGN-010', 'Dynamic shutter geometry and capture from a displayed synthetic stream still need complete browser evidence; real capture needs a device.');
  skip('DESIGN-011', 'Portrait/landscape camera controls and simulated safe area remain unmeasured; physical browser chrome and safe area need device evidence.');
  skip('DESIGN-013', 'Current CTA renders an Atlas scan SVG; audit requires an approved Air Phosphor Light symbol reference before this ID can pass.');

  await check('DESIGN-014', () => withPage(390, 844, async page => {
    assert.equal(await page.locator('#UI-001').getByText('Этикетка целиком, нужная бутылка по центру.').count(), 0);
    await page.locator('#UI-001 .scan-button').click();
    await page.locator('#UI-002, #UI-003').first().waitFor();
    assert.equal(await page.locator('#UI-002').count(), 1, 'fake Chromium camera must reach rendered camera');
    assert.equal(await page.locator('#UI-002').getByText('Нужная бутылка по центру').count(), 1);
    return { homeHint: 'absent', camera: 'framing guidance visible with synthetic stream' };
  }));

  await check('DESIGN-015', async () => {
    const detail = [];
    for (const [width, height] of [[390, 568], [1023, 700], [1024, 700], [1024, 900], [1280, 900]]) {
      detail.push(await withPage(width, height, async page => {
        const m = await page.locator('.app').evaluate(el => ({ app: rect(el),
          shell: rect(el.parentElement), border: getComputedStyle(el).borderLeftWidth,
          radius: getComputedStyle(el).borderRadius }));
        if (width >= 1024) {
          assert.ok(m.app.width < width && Math.abs(m.app.left - (width - m.app.width) / 2) < 2, JSON.stringify(m));
          assert.ok(parseFloat(m.border) > 0 && parseFloat(m.radius) > 0, JSON.stringify(m));
        } else {
          assert.ok(Math.abs(m.app.width - width) < 2 && parseFloat(m.border) === 0, JSON.stringify(m));
        }
        await page.locator('#UI-001 .scan-button').click();
        await page.locator('#UI-002').waitFor();
        const camera = await page.locator('.app').evaluate(el => ({ box: rect(el), border: getComputedStyle(el).borderLeftWidth }));
        assert.ok(Math.abs(camera.box.width - m.app.width) < 1 && camera.border === m.border, JSON.stringify(camera));
        await page.locator('.bottom-nav').getByRole('button', { name: 'Главная' }).click();
        await catalog(page);
        await page.locator('#UI-008 .candidate-list button').first().click();
        const card = await page.locator('.app').evaluate(el => ({ box: rect(el), border: getComputedStyle(el).borderLeftWidth,
          contentScrollHeight: el.querySelector('.app-content').scrollHeight,
          contentClientHeight: el.querySelector('.app-content').clientHeight }));
        assert.ok(Math.abs(card.box.width - m.app.width) < 1 && card.border === m.border, JSON.stringify(card));
        if (width >= 1024) assert.ok(card.contentScrollHeight > card.contentClientHeight, JSON.stringify(card));
        return { width, height, home: m, camera, card };
      }));
    }
    return detail;
  });

  await check('DESIGN-016', async () => {
    const detail = [];
    for (const [width, height] of [[1024, 900], [1280, 700]]) detail.push(await withPage(width, height, async page => {
      await page.locator('#UI-001 .scan-button').click();
      await page.locator('#UI-002').waitFor();
      const camera = await page.locator('.app').evaluate(el => ({ app: rect(el), content: rect(el.querySelector('.app-content')),
        camera: rect(el.querySelector('#UI-002')), video: rect(el.querySelector('video')),
        shutter: rect(el.querySelector('.shutter')), nav: rect(el.querySelector('.bottom-nav')),
        fabricatedChrome: !!el.querySelector('.fake-status-bar, .system-time, .system-home-indicator') }));
      assert.ok(camera.video.width > 0 && camera.video.height > 0 && !camera.fabricatedChrome, JSON.stringify(camera));
      assert.ok(camera.shutter.top >= camera.content.top && camera.shutter.bottom <= camera.content.bottom + 1, JSON.stringify(camera));
      assert.ok(camera.nav.top >= camera.content.bottom - 1 && camera.nav.bottom <= camera.app.bottom + 1, JSON.stringify(camera));
      await page.locator('.bottom-nav').getByRole('button', { name: 'Главная' }).click();
      await catalog(page);
      await page.locator('#UI-008 .candidate-list button').first().click();
      const card = await page.locator('.app-content').evaluate(el => ({ scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight, overflowY: getComputedStyle(el).overflowY }));
      assert.ok(card.scrollHeight > card.clientHeight && card.overflowY === 'auto', JSON.stringify(card));
      await page.locator('.app-content').evaluate(el => { el.scrollTop = el.scrollHeight; });
      assert.ok(await page.locator('.app-content').evaluate(el => el.scrollTop > 0));
      return { width, height, camera, card };
    }));
    return detail;
  });

  await check('DESIGN-018', () => withPage(390, 844, async page => {
    assert.equal(await page.locator('#UI-001 .product-footer').count(), 0);
    const detail = [];
    for (const [label, screen, section, index] of [
      ['Главная', '#UI-001', 'scanner', 0], ['Поиск', '#UI-008', 'search', 1],
      ['Сохранённое', '#UI-016', 'saved', 2], ['Главная', '#UI-001', 'scanner', 0]]) {
      await page.locator('.bottom-nav').getByRole('button', { name: label }).click();
      await page.locator(screen).waitFor();
      await page.waitForTimeout(380);
      const m = await page.locator('.bottom-nav').evaluate(el => ({ section: el.dataset.section,
        current: [...el.querySelectorAll('button')].map(x => x.getAttribute('aria-current')),
        slider: rect(el.querySelector('.nav-slider')),
        buttons: [...el.querySelectorAll('button')].map(rect),
        color: getComputedStyle(el.querySelector('button[aria-current="page"]')).color }));
      assert.equal(m.section, section);
      assert.deepEqual(m.current, [0, 1, 2].map(i => i === index ? 'page' : null));
      assert.ok(Math.abs(m.slider.left - m.buttons[index].left) < 3, JSON.stringify(m));
      assert.equal(m.color, 'rgb(137, 92, 84)');
      detail.push({ label, ...m });
    }
    return detail;
  }));

  await check('DESIGN-020', () => withPage(320, 640, async page => {
    await page.locator('.bottom-nav').getByRole('button', { name: 'Поиск' }).click();
    const submit = await page.locator('#UI-008').getByRole('button', { name: 'Искать' }).evaluate(el => el.getBoundingClientRect().toJSON());
    assert.ok(submit.width >= 48 && submit.height >= 48, `Air search submit target below audited 48×48 minimum: ${JSON.stringify(submit)}`);
    return { submit };
  }));

  await partial('DESIGN-022', 'Home mascot and no-art result states passed; logo identity, asset provenance and all approved scenes remain unverified.', () => withPage(390, 844, async page => {
    const home = await page.locator('#UI-001').evaluate(el => ({ logo: el.querySelector('.v2-logo img')?.getAttribute('src'),
      mascot: el.querySelector('.mascot-scene img')?.getAttribute('src'),
      alt: el.querySelector('.mascot-scene img')?.getAttribute('alt'),
      scene: rect(el.querySelector('.mascot-scene')), actions: rect(el.querySelector('.actions')) }));
    assert.ok(home.mascot?.endsWith('mascot-hold-2d-alpha.webp') && home.alt?.includes('Пёс-детектив'), JSON.stringify(home));
    assert.ok(home.scene.bottom <= home.actions.top + 12, JSON.stringify(home));
    await photoResults(page);
    assert.equal(await page.locator('#UI-006 .mascot-scene').count(), 0);
    await page.locator('#UI-006 .candidate-list button').first().click();
    assert.equal(await page.locator('#UI-007 .mascot-scene').count(), 0);
    return home;
  }));

  await partial('DESIGN-023', 'Rendered Air row and card surfaces passed; approved appearance baseline and unchanged catalog image path remain unverified.', () => withPage(390, 844, async page => {
    await photoResults(page);
    const list = await page.locator('#UI-006 .candidate-list').evaluate(el => ({
      first: rect(el.querySelector('button')),
      border: getComputedStyle(el.querySelector('button')).borderLeftWidth,
      radius: getComputedStyle(el.querySelector('button')).borderRadius,
      imageFit: getComputedStyle(el.querySelector('img')).objectFit,
      imageLoaded: el.querySelector('img').complete && el.querySelector('img').naturalWidth > 0 }));
    assert.ok(list.imageLoaded && list.imageFit === 'contain' && list.border === '0px' && list.radius === '0px', JSON.stringify(list));
    await page.locator('#UI-006 .candidate-list button').first().click();
    const card = await page.locator('#UI-007 .result-hero').evaluate(el => ({
      background: getComputedStyle(el).backgroundImage, imageFit: getComputedStyle(el.querySelector('img')).objectFit }));
    assert.ok(card.background.includes('radial-gradient') && card.imageFit === 'contain', JSON.stringify(card));
    return { list, card };
  }));

  await partial('DESIGN-025', 'Air card shelf and full title passed at four widths; missing-image fallback and consistent 200% text remain unverified.', async () => {
    const detail = [];
    for (const width of [320, 360, 390, 430]) detail.push(await withPage(width, 844, async page => {
      await catalog(page);
      await page.locator('#UI-008 .candidate-list button').first().click();
      const m = await page.locator('#UI-007').evaluate(el => ({ shelf: rect(el.querySelector('.result-shelf')),
        bottle: rect(el.querySelector('.result-shelf img')), facts: rect(el.querySelector('.result-facts')),
        title: rect(el.querySelector('.result-hero h2')),
        clipped: el.querySelector('.result-hero h2').scrollWidth > el.querySelector('.result-hero h2').clientWidth,
        imageLoaded: el.querySelector('.result-shelf img').complete && el.querySelector('.result-shelf img').naturalWidth > 0,
        overflow: document.documentElement.scrollWidth > innerWidth }));
      assert.equal(await page.locator('#UI-007 h2').innerText(), wine.name);
      assert.ok(m.imageLoaded && m.bottle.right < m.facts.left && m.facts.right <= width + 1, JSON.stringify(m));
      assert.ok(!m.clipped && !m.overflow && m.title.left >= 0 && m.title.right <= width + 1, JSON.stringify(m));
      return { width, ...m };
    }));
    return detail;
  });

  await partial('DESIGN-026', 'Ranked order, leader and loaded images passed; missing-image fallback and enlarged-text matrix remain unverified.', () => withPage(320, 640, async page => {
    await photoResults(page);
    const ranked = await page.locator('#UI-006 .candidate-list').evaluate(el => ({
      names: [...el.querySelectorAll('button')].map(x => x.getAttribute('aria-label')),
      leaders: el.querySelectorAll('.candidate-leader').length,
      badges: [...el.querySelectorAll('em')].map(x => x.textContent),
      images: [...el.querySelectorAll('img')].map(x => ({ box: rect(x), loaded: x.complete && x.naturalWidth > 0 })) }));
    assert.deepEqual(ranked.names, [`${wine.name}, 2024`, `${other.name}, 2023`]);
    assert.equal(ranked.leaders, 1);
    assert.deepEqual(ranked.badges, ['Наиболее похожее']);
    assert.ok(ranked.images.length === 2 && ranked.images.every(x => x.loaded && x.box.width > 0), JSON.stringify(ranked));
    await page.locator('.bottom-nav').getByRole('button', { name: 'Поиск' }).click();
    await page.locator('#UI-008').getByRole('button', { name: 'Открыть каталог' }).click();
    await page.locator('#UI-008 .candidate-list button').first().waitFor();
    assert.equal(await page.locator('#UI-008 .candidate-leader').count(), 0);
    return ranked;
  }));
} catch (error) {
  for (const id of ids.filter(id => !cases.some(entry => entry.id === id)))
    skip(id, `Browser runner unavailable: ${String(error?.message || error)}`);
  cases.push({ id: 'BROWSER-RUNNER', status: 'error', reason: String(error?.stack || error) });
} finally {
  await browser?.close().catch(() => {});
  await server?.close().catch(() => {});
}

console.log(JSON.stringify({ schemaVersion: 1, runner: 'design-release-browser',
  revision: process.env.GIT_REVISION || 'working-tree', sourceDigest: await digest(), sources,
  browser: 'Chromium (Playwright)', transport: 'local Vite with mocked /v1 and /v2 responses',
  limitations: ['Fixture responses do not establish model quality or live TEST transport.',
    'Chromium does not establish physical camera, native picker, browser chrome, or safe areas.'],
  cases }));
if (cases.some(entry => entry.status === 'failed' || entry.status === 'error')) process.exitCode = 1;

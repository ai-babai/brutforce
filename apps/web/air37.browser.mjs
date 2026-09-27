// FE-088: real Chromium DOM, local Vite with isolated catalog/search fixtures.
// Run from apps/web: node air37.browser.mjs
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const server = await createServer({ server: { host: '127.0.0.1', port: 5191, strictPort: true } });
await server.listen();
const browser = await chromium.launch();
const url = 'https://vino-svoe.ru/wines/portveyn-belyy-alushta';
const original = { id: 'port', name: 'Портвейн белый Алушта 2021 — коллекционное вино с очень длинным полным названием',
  winery: 'Массандра', image: '/assets/concept-bottle.png', description: 'Аромат сухофруктов и орехов.',
  sugar: 'сладкое', alcoholPercent: 17, region: ['Крым'], sourceUrl: url };
const other = { ...original, id: 'other', name: 'Другой портвейн', year: 2021 };
const measures = () => {
  const box = selector => document.querySelector(selector)?.getBoundingClientRect().toJSON();
  const styles = selector => {
    const node = document.querySelector(selector);
    if (!node) return null;
    const s = getComputedStyle(node);
    return { family: s.fontFamily, background: s.backgroundColor, border: s.borderWidth, display: s.display,
      grid: s.gridTemplateColumns, safeTop: s.paddingTop };
  };
  return { shelf: box('.result-shelf'), bottle: box('.result-shelf img'), facts: box('.result-facts'),
    title: box('.result-hero h2'), hero: box('.result-hero'), top: box('#UI-007 .top'),
    back: box('#UI-007 .top button'), save: box('.save-header-action'), nav: box('.bottom-nav'),
    source: box('.result-source'), overflow: document.documentElement.scrollWidth > innerWidth,
    titleClipped: document.querySelector('.result-hero h2').scrollWidth > document.querySelector('.result-hero h2').clientWidth,
    font: styles('.result-fact'), heading: styles('.result-hero h2'), fact: styles('.result-fact'),
    bottleStyle: styles('.result-shelf img'),
    overview: styles('.result-overview'), description: styles('.result-description'),
    separator: { afterOverview: getComputedStyle(document.querySelector('.result-overview div:last-child')).borderBottomWidth,
      beforeDescription: getComputedStyle(document.querySelector('.result-description')).borderTopWidth } };
};

try {
  for (const [width, height] of [[320, 640], [390, 844], [430, 932]]) {
    const context = await browser.newContext({ viewport: { width, height } });
    let wines = [original, other];
    let feedbackCalls = 0;
    await context.route('**/v2/catalog**', route => route.fulfill({ json: { demo: false, candidates: wines, catalogVersion: 'air37-local' } }));
    await context.route('**/v1/recommendations**', route => route.fulfill({ json: { demo: false, candidates: [] } }));
    await context.route('**/v1/feedback**', route => { feedbackCalls++; return route.fulfill({ status: 400 }); });
    await context.route('https://vino-svoe.ru/**', route => route.fulfill({ body: 'Исходная карточка', contentType: 'text/html' }));
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:5191/');
    await page.getByRole('button', { name: /По названию/i }).click();
    await page.getByRole('button', { name: /Открыть каталог/i }).click();
    await page.mouse.move(0, 0);
    const listSurface = await page.locator('.candidate-list img').first().evaluate(el => ({
      background: getComputedStyle(el).backgroundColor,
      imageFit: getComputedStyle(el).objectFit,
      rowBackground: getComputedStyle(el.closest('button')).backgroundColor,
    }));
    assert.deepEqual(listSurface, { background: 'rgba(0, 0, 0, 0)', imageFit: 'contain', rowBackground: 'rgba(0, 0, 0, 0)' }, `${width}: list alpha surfaces`);
    await page.getByRole('button', { name: /Портвейн белый Алушта/i }).click();
    const m = await page.evaluate(measures);
    assert.ok(m.bottle.right < m.facts.left, `${width}: bottle is left of facts`);
    assert.ok(m.facts.right <= width && m.shelf.right <= width, `${width}: facts within shelf`);
    assert.ok(m.hero.left >= 0 && m.hero.right <= width, `${width}: hero within viewport`);
    assert.ok(!m.overflow && !m.titleClipped, `${width}: title/viewport not clipped`);
    assert.ok(m.back.width >= 44 && m.save.width >= 44 && m.top.top >= 0, `${width}: header actions`);
    assert.equal(m.nav.height, 62, `${width}: Air-36 navigation retained`);
    assert.match(m.font.family, /Onest/); assert.match(m.heading.family, /Onest/);
    assert.equal(m.fact.background, 'rgba(0, 0, 0, 0)', `${width}: facts have no badge`);
    assert.equal(m.fact.border, '0px', `${width}: facts have no border`);
    assert.deepEqual(m.separator, { afterOverview: '0px', beforeDescription: '1px' }, `${width}: exactly one divider`);
    assert.equal(m.bottleStyle.background, 'rgba(0, 0, 0, 0)', `${width}: alpha bottle not flattened`);
    assert.equal(await page.locator('.result-winery').textContent(), 'Массандра');
    assert.equal(await page.locator('.result-overview dd').nth(1).textContent(), 'Год не указан');
    assert.deepEqual(await page.locator('.result-facts dt').allTextContents(), ['Сахар', 'Алкоголь', 'Регион']);
    assert.deepEqual(await page.locator('.result-facts dd').allTextContents(), ['сладкое', '17%', 'Крым']);
    assert.equal(await page.locator('.result-facts svg').count(), 0);
    assert.equal(await page.locator('.result-description').evaluate(el => el.open), false);
    await page.getByText('О вкусе и сочетаниях').click();
    assert.equal(await page.locator('.result-description').evaluate(el => el.open), true);
    const source = page.locator('.result-source');
    assert.equal(await source.getAttribute('href'), url);
    assert.equal(await source.getAttribute('target'), '_blank');
    assert.equal(await source.getAttribute('rel'), 'noopener noreferrer');
    const [popup] = await Promise.all([page.waitForEvent('popup'), source.click()]);
    assert.equal(popup.url(), url);
    await popup.close();
    assert.equal(feedbackCalls, 0, `${width}: source click cannot submit feedback`);
    await page.addStyleTag({ content: '#UI-007 .result-hero h2{font-size:64px}#UI-007 .result-fact dd{font-size:36px}#UI-007 .result-winery,#UI-007 .result-source{font-size:26px}#UI-007 .result-description summary{font-size:28px}' });
    const enlarged = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth > innerWidth,
      clipped: document.querySelector('.result-hero h2').scrollWidth > document.querySelector('.result-hero h2').clientWidth,
      back: document.querySelector('#UI-007 .top button').getBoundingClientRect().width,
      save: document.querySelector('.save-header-action').getBoundingClientRect().width }));
    assert.ok(!enlarged.overflow && !enlarged.clipped && enlarged.back >= 44 && enlarged.save >= 44,
      `${width}: enlarged text remains readable and actions reachable ${JSON.stringify(enlarged)}`);
    await page.getByRole('button', { name: 'Сохранить вино' }).click();
    assert.equal(await page.getByRole('button', { name: 'Удалить из сохранённых' }).count(), 1);
    await page.getByRole('button', { name: 'Назад' }).click();
    assert.equal(await page.getByRole('button', { name: /Другой портвейн/i }).count(), 1);
    await page.getByRole('button', { name: /Другой портвейн/i }).click();
    assert.equal(await page.locator('.result-winery').textContent(), 'Массандра · 2021');
    assert.equal(await page.locator('.result-overview dd').nth(1).textContent(), '2021');
    await page.goBack();
    await page.getByRole('button', { name: /Портвейн белый Алушта/i }).waitFor();
    wines = [{ ...original, id: 'without', sourceUrl: undefined, description: '   ', sugar: undefined,
      alcoholPercent: undefined, region: undefined }];
    await page.reload();
    await page.getByRole('button', { name: /По названию/i }).click();
    await page.getByRole('button', { name: /Открыть каталог/i }).click();
    await page.getByRole('button', { name: /Портвейн белый Алушта/i }).click();
    assert.equal(await page.locator('.result-source, .result-description, .result-facts, .tabs, .correction').count(), 0);
    if (width === 390) {
      await page.addStyleTag({ content: '#UI-007.page{--safe-area-top:24px}' });
      const inset = await page.evaluate(() => ({ top: document.querySelector('#UI-007 .top').getBoundingClientRect().top,
        nav: document.querySelector('.bottom-nav').getBoundingClientRect().height,
        overflow: document.documentElement.scrollWidth > innerWidth }));
      assert.ok(inset.top >= 24 && !inset.overflow, `390 simulated top inset: ${JSON.stringify(inset)}`);
      assert.equal(inset.nav, 62);
    }
    console.log(`${width}x${height}: AIR-041..045 passed; shelf ${Math.round(m.shelf.width)}px, bottle ${Math.round(m.bottle.width)}px, top ${Math.round(m.top.top)}px`);
    await context.close();
  }
} finally { await browser.close(); await server.close(); }

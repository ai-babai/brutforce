// FE-080/081: observable geometry and actions in the real product DOM (local mocked HTTP).
// Run from apps/web: node air36.browser.mjs. Requires locally installed Playwright Chromium.
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const server = await createServer({ server: { host: '127.0.0.1', port: 5191, strictPort: true } });
await server.listen();
const browser = await chromium.launch();
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y2UKH4AAAAASUVORK5CYII=', 'base64');

try {
  for (const [width, height] of [[320, 568], [390, 844], [430, 932], [844, 390]]) {
    const context = await browser.newContext({ viewport: { width, height } });
    await context.addInitScript(() => Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true, value: { getUserMedia: () => new Promise(() => {}) },
    }));
    const page = await context.newPage();
    let response = 'candidates';
    await page.route('**/v1/photos', route => route.fulfill({ json: {
      id: '0123456789abcdef0123456789abcdef', createdAt: '2026-09-26T00:00:00Z', bytes: 10,
      mime: 'image/png', width: 1, height: 1,
    } }));
    await page.route('**/v1/search', route => route.fulfill({ status: response === 'error' ? 503 : 200,
      json: { demo: false, candidates: response === 'empty' ? [] : [{ id: 'wine-a', name: 'Красностоп',
        winery: 'Винодельня', year: 2022, image: '', description: 'Описание' }] },
    }));
    await page.route('**/v2/catalog**', route => route.fulfill({ json: {
      demo: false, candidates: [], catalogVersion: 'local-browser-check',
    } }));
    await page.goto('http://127.0.0.1:5191/');
    const nav = page.getByRole('navigation', { name: 'Основная навигация' });
    for (const [name, section] of [['Главная', 'scanner'], ['Поиск', 'search'], ['Сохранённое', 'saved']]) {
      await nav.getByRole('button', { name }).click();
      const result = await nav.evaluate(el => ({ height: el.getBoundingClientRect().height,
        pill: el.querySelector('.nav-slider').getBoundingClientRect().height,
        targets: [...el.querySelectorAll('button')].map(b => b.getBoundingClientRect().height),
        current: [...el.querySelectorAll('button[aria-current="page"]')].map(b => b.textContent),
        section: el.dataset.section }));
      assert.equal(result.height, 62, `${width}x${height} nav height`);
      assert.equal(result.pill, 51);
      assert.ok(result.targets.every(size => size >= 48));
      assert.deepEqual(result.current, [name]);
      assert.equal(result.section, section);
    }
    await nav.getByRole('button', { name: 'Главная' }).click();
    await page.getByRole('button', { name: /Сканировать вино/ }).click();
    const camera = await page.evaluate(() => ({ shutter: document.querySelector('.shutter').getBoundingClientRect().bottom,
      gallery: document.querySelector('.camera-gallery-action').getBoundingClientRect().height,
      nav: document.querySelector('.bottom-nav').getBoundingClientRect().top }));
    assert.ok(camera.shutter < camera.nav, `${width}x${height} shutter is clear of nav`);
    assert.ok(camera.gallery >= 48);
    await nav.getByRole('button', { name: 'Главная' }).click();
    for (const [state, heading] of [['candidates', 'Проверьте найденное вино'],
      ['empty', 'Ничего не найдено'], ['error', 'Не удалось получить ответ']]) {
      response = state;
      await page.locator('input[aria-label="Загрузить фотографию этикетки"]').setInputFiles({
        name: `${state}.png`, mimeType: 'image/png', buffer: image,
      });
      await page.getByRole('heading', { name: heading }).waitFor();
      const result = await page.evaluate(() => {
        const photo = document.querySelector('.air-comparison .photo.compact, .air-recovery-photo .photo.compact');
        const thumb = photo.querySelector('img').getBoundingClientRect();
        const caption = photo.querySelector('span').getBoundingClientRect();
        const actions = [...photo.parentElement.querySelectorAll('.air-photo-action')];
        return { gap: caption.left - thumb.right, width: photo.getBoundingClientRect().width,
          textRight: caption.right, actions: actions.map(button => button.getBoundingClientRect().height),
          overflow: document.documentElement.scrollWidth > innerWidth };
      });
      assert.equal(result.gap, 8, `${width}x${height} ${state} photo gap`);
      assert.ok(result.width < width / 2, `${state} photo button hugs its contents`);
      assert.ok(result.textRight <= width);
      assert.ok(result.actions.length === 2 && result.actions.every(size => size >= 48));
      assert.equal(result.overflow, false);
      await page.getByRole('button', { name: 'Открыть исходную фотографию' }).click();
      assert.equal(await page.getByRole('dialog', { name: 'Исходная фотография' }).isVisible(), true);
      await page.getByRole('button', { name: 'Закрыть фотографию' }).click();
    }
    if (width === 390) {
      await page.addStyleTag({ content: '.bottom-nav{height:86px;min-height:86px;padding-bottom:29px}.bottom-nav .nav-slider{bottom:29px}' });
      const inset = await nav.evaluate(el => ({ nav: el.getBoundingClientRect().height,
        pill: el.querySelector('.nav-slider').getBoundingClientRect().height }));
      assert.deepEqual(inset, { nav: 86, pill: 51 }, 'simulated 24px bottom inset');
      await page.addStyleTag({ content: '.bottom-nav button{font-size:20px;line-height:28px}.bottom-nav button span{line-height:28px}.air-recovery-photo .photo.compact span{font-size:24px}' });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'enlarged text overflow');
    }
    console.log(`${width}x${height}: AIR-039/040 browser geometry and actions passed`);
    await context.close();
  }
} finally {
  await browser.close();
  await server.close();
}

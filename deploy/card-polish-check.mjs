// Air 3.7 visual fixtures: transparent list imagery, shelf layout, long text and safe area.
// API and real catalog checks remain in browser-smoke.mjs.
export async function checkCardPolish({ browser, contextOptions, baseURL, capture, check, sample }) {
  const metrics = [];
  const longName = 'Коллекционное игристое вино из виноградников южного склона с выдержкой в бутылке и редким купажом';
  const normal = { ...sample, id: 'polish-normal', name: 'Abrau Estates Каберне по-белому', winery: 'Абрау-Дюрсо',
    sugar: 'сладкое', alcoholPercent: 17, region: ['Крым'], description: 'Аромат сухофруктов и орехов.' };
  const long = { ...normal, id: 'polish-long', name: longName };
  const missing = { ...normal, id: 'polish-missing', name: 'Вино без фотографии', image: '', imageVariants: [] };
  for (const width of [320, 360, 390, 430, 1440]) {
    await check(`Air 3.7 ${width}px card geometry (explicit UI fixtures)`, async () => {
      const context = await browser.newContext({ ...contextOptions, viewport: { width, height: 900 } });
      const page = await context.newPage();
      page.setDefaultTimeout(10_000);
      page.setDefaultNavigationTimeout(15_000);
      try {
        await page.route('**/v2/catalog?*', route => route.fulfill({ json: { demo: false, catalogVersion: 'visual-fixture', candidates: [normal, long, missing] } }));
        await page.route('**/v1/recommendations', route => route.fulfill({ json: { demo: false, candidates: [] } }));
        await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
        await page.getByRole('button', { name: /По названию/ }).click();
        await page.getByLabel(/Название вина/).fill('вино');
        const rows = page.locator('.candidate-list > button');
        await rows.first().waitFor();
        await page.evaluate(() => document.fonts.ready);
        await page.mouse.move(0, 0);
        const tiles = await rows.evaluateAll(elements => elements.map((element, index) => {
          const image = element.querySelector('img,.missing-image');
          const box = image.getBoundingClientRect();
          return { index, rowBackground: getComputedStyle(element).backgroundColor,
            imageBackground: getComputedStyle(image).backgroundColor, fit: getComputedStyle(image).objectFit,
            width: box.width, height: box.height, leader: element.classList.contains('candidate-leader'),
            badge: Boolean(element.querySelector('em')), overflow: element.scrollWidth > element.clientWidth + 1 };
        }));
        for (const tile of tiles) {
          const leader = tile.index === 0;
          const expected = width <= 390 && leader ? [70, 122] : leader ? [76, 132] : [56, 98];
          if (tile.rowBackground !== 'rgba(0, 0, 0, 0)' || tile.imageBackground !== 'rgba(0, 0, 0, 0)' ||
            tile.width !== expected[0] || tile.height !== expected[1] || tile.fit !== 'contain' || tile.overflow ||
            tile.leader !== leader || tile.badge !== leader)
            throw new Error('Air 3.7 list tile: ' + JSON.stringify(tile));
        }
        const badgeWidth = await page.locator('.candidate-leader em').evaluate(element => element.getBoundingClientRect().width);
        if (badgeWidth >= 180) throw new Error('Leader badge stretches across the row');
        if (width === 390) await capture(page, 'polish-search-390');
        const enlargedTiles = await rows.evaluateAll(elements => {
          const text = elements.flatMap(element => [...element.querySelectorAll('b,small,em')]);
          text.forEach(element => element.style.fontSize = `${parseFloat(getComputedStyle(element).fontSize) * 2}px`);
          const overflow = elements.map(element => element.scrollWidth > element.clientWidth + 1);
          text.forEach(element => element.style.removeProperty('font-size'));
          return overflow;
        });
        if (enlargedTiles.some(Boolean)) throw new Error('200% list text overflows: ' + JSON.stringify(enlargedTiles));
        await rows.first().click();
        const measure = () => page.locator('#UI-007').evaluate(element => {
          const rect = selector => element.querySelector(selector)?.getBoundingClientRect();
          const top = rect('.top'), hero = rect('.result-hero'), shelf = rect('.result-shelf');
          const image = rect('.result-shelf > img'), facts = rect('.result-facts');
          const title = element.querySelector('.result-hero h2');
          const buttons = [...element.querySelectorAll('.top button')].map(button => button.getBoundingClientRect());
          return { top: top.top - element.getBoundingClientRect().top, hero: { left: hero.left, right: hero.right },
            shelf: { right: shelf.right }, image: { right: image.right, height: image.height },
            facts: { left: facts.left, right: facts.right, values: [...element.querySelectorAll('.result-fact dd')].map(node => node.getBoundingClientRect().left) },
            title: { left: title.getBoundingClientRect().left, right: title.getBoundingClientRect().right,
              clipped: title.scrollWidth > title.clientWidth + 1, family: getComputedStyle(title).fontFamily },
            pageWidth: element.getBoundingClientRect().width, overflow: document.documentElement.scrollWidth > innerWidth + 1,
            imageFit: getComputedStyle(element.querySelector('.result-shelf > img')).objectFit,
            imageBackground: getComputedStyle(element.querySelector('.result-shelf > img')).backgroundColor,
            factBackground: getComputedStyle(element.querySelector('.result-fact')).backgroundColor,
            factBorder: getComputedStyle(element.querySelector('.result-fact')).borderWidth,
            font: getComputedStyle(element.querySelector('.result-fact')).fontFamily,
            nav: document.querySelector('.bottom-nav').getBoundingClientRect().height,
            buttons: buttons.map(box => ({ width: box.width, height: box.height })) };
        });
        const assertLayout = (m, phase) => {
          if (m.image.right >= m.facts.left || m.facts.right > m.shelf.right + 1 ||
            m.hero.left < -1 || m.hero.right > width + 1 || m.overflow || m.title.clipped ||
            m.title.right > width + 1 || m.image.height !== 255 || m.imageFit !== 'contain' ||
            m.imageBackground !== 'rgba(0, 0, 0, 0)' || m.factBackground !== 'rgba(0, 0, 0, 0)' ||
            m.factBorder !== '0px' || !m.font.includes('Onest') || !m.title.family.includes('Onest') ||
            Math.abs(m.nav - 62) > 1 || m.buttons.some(box => box.width < 44 || box.height < 44))
            throw new Error(`${phase} Air 3.7 shelf: ${JSON.stringify(m)}`);
        };
        const normalLayout = await measure();
        assertLayout(normalLayout, 'normal');
        await page.addStyleTag({ content: '#UI-007 .result-hero h2{font-size:64px}#UI-007 .result-fact dd{font-size:36px}#UI-007 .result-winery,#UI-007 .result-source{font-size:26px}#UI-007 .result-description summary{font-size:28px}' });
        const normalEnlarged = await measure();
        assertLayout(normalEnlarged, 'enlarged normal card');
        if (await page.locator('.result-facts dt').allTextContents().then(values => values.join('')) !== 'СахарАлкогольРегион')
          throw new Error('Shelf facts missing or misordered');
        if (await page.locator('.result-overview dt').count() < 5) throw new Error('Overview facts missing');
        if (await page.locator('.result-description').evaluate(element => element.open)) throw new Error('Description must start collapsed');
        await page.locator('.result-description summary').click();
        if (!await page.locator('.result-description').evaluate(element => element.open)) throw new Error('Description did not expand');
        if (await page.locator('.tabs, .correction').count()) throw new Error('Old tabs or web feedback controls reappeared');
        if (width === 390) await capture(page, 'polish-hero-390');
        await page.locator('#UI-007').evaluate(element => element.style.setProperty('--safe-area-top', '24px'));
        const inset = await measure();
        if (inset.top <= normalLayout.top || inset.top > normalLayout.top + 24)
          throw new Error(`Safe area not applied exactly once: ${JSON.stringify({ baseline: normalLayout.top, inset })}`);
        await page.locator('#UI-007').evaluate(element => element.style.removeProperty('--safe-area-top'));
        await page.getByRole('button', { name: 'Сохранить вино', exact: true }).click();
        if (await page.getByRole('button', { name: 'Удалить из сохранённых' }).getAttribute('aria-pressed') !== 'true')
          throw new Error('Save toggle failed');
        await page.getByRole('button', { name: 'Назад', exact: true }).click();
        if (await page.getByLabel(/Название вина/).inputValue() !== 'вино') throw new Error('Back lost query');
        await rows.nth(1).click();
        await page.getByRole('heading', { name: longName, exact: true }).waitFor();
        const enlarged = await measure();
        assertLayout(enlarged, 'enlarged long title');
        if (width === 320) await capture(page, 'polish-long-200pct-320');
        await page.locator('.result-hero h2').evaluate(element => element.scrollIntoView({ block: 'end' }));
        const scrollEnd = await page.locator('.result-hero h2').evaluate(element => ({
          bottom: element.getBoundingClientRect().bottom,
          navTop: document.querySelector('.bottom-nav').getBoundingClientRect().top,
        }));
        if (scrollEnd.bottom > scrollEnd.navTop + 1) throw new Error('Long title cannot be scrolled above navigation');
        metrics.push({ width, tiles, badgeWidth, enlargedTiles, scrollEnd, normal: normalLayout,
          normalEnlarged, simulatedInset24: inset, enlarged });
      } finally { await context.close(); }
    });
  }
  return metrics;
}

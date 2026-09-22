// FE-057 visual contract. Small explicit UI fixtures; not an API/data-quality test.
export async function checkCardPolish({ browser, contextOptions, baseURL, capture, check, sample }) {
  const metrics = [];
  const longName = 'Коллекционное игристое вино из виноградников южного склона с выдержкой в бутылке и редким купажом';
  const normal = { ...sample, id: 'polish-normal', name: 'Abrau Estates Каберне по-белому', winery: 'Абрау-Дюрсо' };
  const long = { ...normal, id: 'polish-long', name: longName };
  const missing = { ...normal, id: 'polish-missing', name: 'Вино без фотографии', image: '', imageVariants: [] };
  for (const width of [320, 360, 390, 430, 1440]) {
    await check(`DESIGN023–026 ${width}px card geometry (explicit UI fixtures)`, async () => {
      const context = await browser.newContext({ ...contextOptions, viewport: { width, height: 900 } });
      const page = await context.newPage();
      page.setDefaultTimeout(10_000);
      try {
        await page.route('**/v2/catalog?*', route => route.fulfill({ json: { demo: false, catalogVersion: 'visual-fixture', candidates: [normal, long, missing] } }));
        await page.route('**/v1/recommendations', route => route.fulfill({ json: { demo: false, candidates: [] } }));
        await page.goto(baseURL);
        await page.getByRole('button', { name: /По названию/ }).click();
        await page.getByLabel(/Название вина/).fill('вино');
        const rows = page.locator('.candidate-list > button');
        await rows.first().waitFor();
        await page.evaluate(() => document.fonts.ready);
        const tiles = await rows.evaluateAll(elements => elements.map((e, i) => {
          const pic = e.querySelector('img,.missing-image');
          const s = getComputedStyle(e), ps = getComputedStyle(pic), r = pic.getBoundingClientRect();
          return { i, background: s.backgroundColor, photoBackground: ps.backgroundColor, width: r.width, height: r.height, contain: ps.objectFit, leader: e.classList.contains('candidate-leader'), badge: Boolean(e.querySelector('em')), overflow: e.scrollWidth > e.clientWidth + 1 };
        }));
        for (const t of tiles) {
          if (t.background !== 'rgb(255, 255, 255)' || t.photoBackground !== 'rgb(255, 255, 255)' || t.width !== (t.i ? 56 : 76) || t.height !== (t.i ? 98 : 132) || t.overflow || t.leader !== (t.i === 0) || t.badge !== (t.i === 0)) throw Error('Tile geometry: '+JSON.stringify(t));
        }
        const badgeWidth = await page.locator('.candidate-leader em').evaluate(e => e.getBoundingClientRect().width);
        if (badgeWidth >= 180) throw Error('Leader badge stretches across the row');
        if (width === 390) await capture(page, 'polish-search-390');
        const enlargedTiles = await rows.evaluateAll(elements => {
          const text = elements.flatMap(e => [...e.querySelectorAll('b,small,em')]);
          const sizes = text.map(e => parseFloat(getComputedStyle(e).fontSize));
          text.forEach((e,i) => e.style.fontSize = `${sizes[i]*2}px`);
          const measured = elements.map(e => ({ overflow:e.scrollWidth>e.clientWidth+1, titleSize:parseFloat(getComputedStyle(e.querySelector('b')).fontSize) }));
          text.forEach(e => e.style.removeProperty('font-size'));
          return measured;
        });
        if (enlargedTiles.some(t => t.overflow) || enlargedTiles[0].titleSize !== 36 || enlargedTiles[1].titleSize !== 28) throw Error('200% tile text overflows: '+JSON.stringify(enlargedTiles));
        await rows.first().click();
        const measure = () => page.locator('#UI-007').evaluate(el => {
          const header = el.querySelector('.top'), hero = el.querySelector('.result-hero'), photo = hero.querySelector('img,.missing-image'), h2 = hero.querySelector('h2');
          const r = x => { const b = x.getBoundingClientRect(); return { x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom,right:b.right }; };
          const controls = [...header.querySelectorAll('button')].map(r);
          const title = r(header.querySelector('b'));
          return { paper:getComputedStyle(document.querySelector('.app')).backgroundColor, ink:getComputedStyle(el).color, headingSize:parseFloat(getComputedStyle(h2).fontSize), page:r(el), header:r(header), hero:r(hero), photo:r(photo), title:r(h2), controls, headerTitle:title, paddingTop:getComputedStyle(el).paddingTop, white:getComputedStyle(hero).backgroundColor, contain:getComputedStyle(photo).objectFit, blend:getComputedStyle(photo).mixBlendMode, headingFont:getComputedStyle(h2).fontFamily, clipping:getComputedStyle(h2).overflowY !== 'visible' && h2.scrollHeight > h2.clientHeight+1, overflow:el.scrollWidth > el.clientWidth+1, bodyOverflow:document.documentElement.scrollWidth > innerWidth };
        });
        const m = await measure();
        if (m.paper!=='rgb(254, 253, 250)' || m.ink!=='rgb(44, 42, 40)' || m.headingSize!==25 || m.paddingTop !== (width>=1024 ? '14px' : '8px') || Math.abs(m.header.y-m.page.y-(width>=1024 ? 8 : 2))>1 || Math.abs(m.hero.y-m.page.y-(width>=1024 ? 68 : 62))>1 || Math.abs(m.hero.height-254)>1 || m.photo.height!==216 || m.photo.width<125 || m.photo.width>200 || m.white!=='rgb(255, 255, 255)' || m.contain!=='contain' || m.blend!=='normal' || !m.headingFont.includes('Playfair') || m.overflow || m.bodyOverflow || m.clipping || m.controls.some(b=>b.width<44 || b.height<44)) throw Error('Hero geometry: '+JSON.stringify(m));
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        const normalEnlarged = await measure();
        if (normalEnlarged.overflow || normalEnlarged.bodyOverflow || normalEnlarged.clipping || normalEnlarged.title.right > normalEnlarged.hero.right+1) throw Error('200% ordinary title overflows');
        await page.evaluate(() => document.documentElement.style.removeProperty('font-size'));
        // Simulate a nonzero inset through the same token used by the native env fallback.
        await page.evaluate(() => document.documentElement.style.setProperty('--safe-area-top', '24px'));
        const inset = await measure();
        if (Math.abs(inset.header.height-48)>1 || Math.abs(inset.hero.y-m.hero.y-24)>1 || Math.abs(parseFloat(inset.paddingTop)-parseFloat(m.paddingTop)-24)>1) throw Error('Safe area counted twice: '+JSON.stringify(inset));
        await page.evaluate(() => document.documentElement.style.removeProperty('--safe-area-top'));
        await page.getByRole('button', { name: 'Сохранить вино', exact:true }).click();
        if (await page.getByRole('button', { name:'Удалить из сохранённых' }).getAttribute('aria-pressed') !== 'true') throw Error('Save toggle failed');
        if (width === 390) await capture(page, 'polish-hero-390');
        await page.getByRole('button', { name: 'Назад', exact:true }).click();
        if (await page.getByLabel(/Название вина/).inputValue() !== 'вино') throw Error('Back lost query');
        await rows.nth(1).click();
        await page.getByRole('heading', {name:longName,exact:true}).waitFor();
        // 200% root text size exercises the rem-based hero and header without a screenshot scale trick.
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        const enlarged = await measure();
        if (await page.locator('.result-hero h2').textContent() !== longName || enlarged.photo.height !== 216 || enlarged.title.width < 145 || enlarged.overflow || enlarged.bodyOverflow || enlarged.clipping || enlarged.headerTitle.x < enlarged.controls[0].right || (enlarged.headerTitle.right > enlarged.controls[1].x+1 && enlarged.headerTitle.bottom > enlarged.controls[1].y+1)) throw Error('Enlarged long title: '+JSON.stringify(enlarged));
        if (width === 320) await capture(page, 'polish-long-200pct-320');
        await page.locator('.result-hero h2').evaluate(e => e.scrollIntoView({ block:'end' }));
        const scrollEnd = await page.locator('.result-hero h2').evaluate(e => ({ bottom:e.getBoundingClientRect().bottom, navTop:document.querySelector('.bottom-nav').getBoundingClientRect().top }));
        if (scrollEnd.bottom > scrollEnd.navTop+1) throw Error('Long title cannot be scrolled above navigation');
        metrics.push({ width, tiles, badgeWidth, enlargedTiles, scrollEnd, normal:m, normalEnlarged, simulatedInset24:inset, enlarged });
      } finally { await context.close(); }
    });
  }
  return metrics;
}

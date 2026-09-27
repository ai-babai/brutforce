#!/usr/bin/env node
import { mkdir, stat, writeFile } from 'node:fs/promises';
import { checkCardPolish } from './card-polish-check.mjs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(new URL('../apps/web/package.json', import.meta.url));
const { chromium } = require('playwright');
const baseURL = (process.env.BASE_URL || 'http://127.0.0.1:8097').replace(/\/$/, '');
const outputDir = resolve(process.env.SMOKE_OUTPUT_DIR || resolve(root, 'temp/browser-smoke'));
const user = process.env.TEST_HTTP_USER;
const password = process.env.TEST_HTTP_PASSWORD;
const expectedRevision = process.env.EXPECTED_REVISION;
const expectedCandidate = process.env.EXPECTED_CANDIDATE_ID || expectedRevision;
const expectedCatalog = process.env.EXPECTED_CATALOG_VERSION;
// An explicitly approved, independently identified wine photo (never a UI asset).
const photoSample = process.env.SMOKE_PHOTO_SAMPLE;
const photoSlug = process.env.SMOKE_PHOTO_EXPECTED_SLUG;
const checks = [];
const evidence = [];
const actionTimeout = 15_000;
const apiTimeout = 20_000;
let revision;
let catalogVersion;

const check = async (name, work) => {
  console.error(`[smoke] start: ${name}`);
  try { await work(); checks.push({ name, status: 'passed' }); console.error(`[smoke] pass: ${name}`); }
  catch (error) {
    checks.push({ name, status: 'failed', error: error instanceof Error ? error.message : String(error) });
    console.error(`[smoke] fail: ${name}`);
    throw error;
  }
};
const bounded = async (promise, description, timeout = apiTimeout) => {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${description} timed out after ${timeout}ms`)), timeout); }),
    ]);
  } finally { clearTimeout(timer); }
};
const configurePage = page => {
  page.setDefaultTimeout(actionTimeout);
  page.setDefaultNavigationTimeout(actionTimeout);
  return page;
};
const runURL = process.env.GITHUB_SERVER_URL && process.env.GITHUB_REPOSITORY && process.env.GITHUB_RUN_ID
  ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}` : undefined;
const result = (status, error) => ({ revision: expectedRevision || revision || null, candidateId: expectedCandidate || null, observedRevision: revision || null, catalogVersion: catalogVersion || null, status, at: new Date().toISOString(), checks, evidence, ...(runURL ? { githubRunURL: runURL } : {}), ...(error ? { error } : {}) });

await mkdir(outputDir, { recursive: true });
let browser;
try {
  if (Boolean(user) !== Boolean(password)) throw new Error('Set both TEST_HTTP_USER and TEST_HTTP_PASSWORD, or neither.');
  browser = await chromium.launch({ headless: true });
  const contextOptions = user ? { httpCredentials: { username: user, password } } : {};
  const releaseContext = await browser.newContext(contextOptions);
  await check('release revision', async () => {
    const response = await releaseContext.request.get(`${baseURL}/release.json`, {timeout:apiTimeout});
    if (!response.ok()) throw new Error(`/release.json returned ${response.status()}`);
    const data = await response.json();
    if (!data || typeof data.revision !== 'string' || !data.revision) throw new Error('/release.json has no revision');
    revision = data.revision;
    if (expectedRevision && revision !== expectedRevision) throw new Error(`revision ${revision} does not match EXPECTED_REVISION`);
  });
  let catalog;
  await check('active catalog version and bounded first page', async () => {
    const response = await releaseContext.request.get(`${baseURL}/v2/catalog`, {timeout:apiTimeout});
    if (!response.ok()) throw new Error(`catalog returned ${response.status()}`);
    catalog = await response.json();
    catalogVersion = catalog.catalogVersion;
    if (!catalogVersion || !catalog.candidates?.length || catalog.candidates.length > 24)
      throw new Error('catalog version or bounded first page is invalid');
    if (expectedCatalog && catalogVersion !== expectedCatalog) throw new Error('catalog does not match EXPECTED_CATALOG_VERSION');
  });
  const capture = async (page, name) => {
    const path = resolve(outputDir, `${name}.png`);
    await page.waitForFunction(() => [...document.images].filter(image => {
      const r = image.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight;
    }).every(image => image.complete && image.naturalWidth > 0), null, {timeout: 10_000});
    const broken = await page.locator('img').evaluateAll(images => images.filter(image => image.complete && !image.naturalWidth).map(image => image.getAttribute('src')));
    if (broken.length) throw new Error('Images failed to load: '+broken.join(', '));
    await page.screenshot({ path, fullPage: true, animations: 'disabled' });
    evidence.push(path);
  };
  const visible = (locator, description) => locator.waitFor({ state: 'visible', timeout: 10_000 })
    .catch(() => { throw new Error(`${description} is not visible`); });
  let realRecommendationsObserved = 0;
  const feedbackCalls = (page) => {
    const calls = [];
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/v1/feedback') calls.push(request.method());
    });
    return async () => {
      if (calls.length) throw new Error(`web sent photo feedback: ${calls.join(', ')}`);
      if (await page.locator('.correction, .photo-feedback, .feedback-correction').count())
        throw new Error('web exposed photo feedback controls');
    };
  };
  const requireWinePhoto = async (realCatalog = true) => {
    if (!photoSample || realCatalog && !photoSlug)
      throw new Error(`BLOCKED: supply an explicitly approved local wine photo via SMOKE_PHOTO_SAMPLE${realCatalog ? ' and its independently verified catalog slug via SMOKE_PHOTO_EXPECTED_SLUG' : ''}; no verified smoke sample was provided`);
    if (resolve(photoSample) === resolve(root, 'apps/web/public/assets/app-192.png'))
      throw new Error('BLOCKED: app icon is not a photograph of a catalog wine');
    const file = await stat(photoSample).catch(() => null);
    if (!file?.isFile() || !file.size) throw new Error('BLOCKED: approved wine photo sample is missing or empty');
    return file;
  };
  const checkCard = async (page, context, wine, label, demo) => {
    await visible(page.getByRole('heading', {name:wine.name, exact:true}), `${label} title`);
    const shelf = page.locator('.result-shelf');
    const photo = shelf.locator('img');
    await visible(photo, `${label} bottle`);
    await photo.evaluate(image => image.decode());
    const image = await photo.evaluate(el => ({src:el.currentSrc, fit:getComputedStyle(el).objectFit, srcset:el.srcset}));
    if (image.fit !== 'contain') throw new Error(`${label} bottle must fit inside shelf`);
    if (!demo) {
      const validPaths = wine.imageVariants?.map(v => new URL(v.path, baseURL).href) ?? [];
      if (!validPaths.includes(image.src) || !image.srcset) throw new Error(`${label} image differs from accepted catalog variants`);
    }
    const layout = await page.locator('#UI-007').evaluate(el => {
      const rect = selector => el.querySelector(selector)?.getBoundingClientRect();
      const bottle = rect('.result-shelf img'), facts = rect('.result-facts'), hero = rect('.result-hero');
      const title = el.querySelector('.result-hero h2');
      return {bottleRight:bottle.right, factsLeft:facts?.left, shelfRight:rect('.result-shelf').right,
        heroLeft:hero.left, heroRight:hero.right, overflow:document.documentElement.scrollWidth > innerWidth + 1,
        clipped:title.scrollWidth > title.clientWidth + 1,
        controls:[...el.querySelectorAll('.top button')].map(button => button.getBoundingClientRect().width),
        navHeight:document.querySelector('.bottom-nav')?.getBoundingClientRect().height};
    });
    if (layout.factsLeft !== undefined && layout.bottleRight >= layout.factsLeft ||
      layout.shelfRight > page.viewportSize().width + 1 || layout.heroLeft < -1 ||
      layout.heroRight > page.viewportSize().width + 1 || layout.overflow || layout.clipped ||
      layout.controls.some(width => width < 44) || Math.abs(layout.navHeight - 62) > 1)
      throw new Error(`${label} Air 3.7 shelf/header geometry: ${JSON.stringify(layout)}`);
    if (wine.sugar || wine.region?.length || wine.alcoholPercent || wine.alcoholMinPercent || wine.alcoholMaxPercent)
      await visible(shelf.locator('.result-facts'), `${label} shelf facts`);
    await visible(page.locator('.result-overview'), `${label} overview`);
    if (wine.description.trim()) {
      const description = page.locator('.result-description');
      if (await description.evaluate(el => el.open)) throw new Error(`${label} description must start collapsed`);
      await description.locator('summary').click();
      await visible(description.locator('p'), `${label} expanded description`);
    }
    if (await page.locator('#UI-007 .tabs, #UI-007 .correction, #UI-007 .photo-feedback').count())
      throw new Error(`${label} reintroduced tabs or web feedback`);
    const source = page.locator('.result-source');
    if (wine.sourceUrl) {
      await visible(source, `${label} direct source`);
      const attributes = await source.evaluate(el => ({href:el.getAttribute('href'), target:el.target, rel:el.rel}));
      if (attributes.href !== wine.sourceUrl || attributes.target !== '_blank' ||
        !attributes.rel.split(/\s+/).includes('noopener') || !attributes.rel.split(/\s+/).includes('noreferrer'))
        throw new Error(`${label} direct source URL/target/rel differs from catalog`);
      // Only navigation semantics are under test; no dependency on the third-party site's uptime.
      await context.route(wine.sourceUrl, route => route.fulfill({contentType:'text/html', body:'Source navigation'}));
      const [popup] = await Promise.all([page.waitForEvent('popup'), source.click()]);
      await popup.waitForURL(wine.sourceUrl);
      await popup.close();
    } else if (await source.count()) throw new Error(`${label} invented a source link`);
    if (demo) {
      await visible(page.locator('.demo-label'), `${label} demo marker`);
    } else if (await page.locator('.demo-label').count()) throw new Error(`${label} real card labelled synthetic`);
  };
  const recommendationsReady = async (page, pending, source, label) => {
    const response = await bounded(pending, `${label} recommendations`);
    if (!response.ok()) throw new Error(`${label} recommendations returned HTTP ${response.status()}`);
    const data = await response.json();
    if (!Array.isArray(data.candidates) || data.candidates.some(item => item.id === source.id) ||
      (data.catalogVersion && data.catalogVersion !== catalogVersion))
      throw new Error(`${label} recommendations are invalid, stale or repeat source wine`);
    if (!data.candidates.length) {
      if (source.slug === undefined) throw new Error(`${label} synthetic catalog returned no recommendations`);
      await visible(page.getByText('Пока нет рекомендаций для этой карточки.', {exact:true}), `${label} honest empty recommendations`);
      return;
    }
    if (source.slug !== undefined) realRecommendationsObserved++;
    const list = page.locator('.recommendation-list > button');
    await visible(list.first(), `${label} loaded recommendations`);
    await page.waitForFunction(n => document.querySelectorAll('.recommendation-list > button').length === n, data.candidates.length);
    for (const [index, item] of data.candidates.entries())
      if (!(await list.nth(index).innerText()).includes(item.name)) throw new Error(`${label} recommendations differ from API order`);
    if (await page.getByText('Подбираем рекомендации', {exact:true}).isVisible())
      throw new Error(`${label} recommendations still loading`);
  };
  const recommendationResponse = (page, wine) => page.waitForResponse(response =>
    new URL(response.url()).pathname === '/v1/recommendations' &&
    response.request().postDataJSON()?.wineId === wine.id, {timeout:apiTimeout});
  const polishMetrics = await checkCardPolish({ browser, contextOptions, baseURL, capture, check, sample: catalog.candidates[0] });
  await writeFile(resolve(outputDir, 'card-polish-metrics.json'), JSON.stringify(polishMetrics, null, 2));
  const textFlow = async (viewport, prefix) => {
    const context = await browser.newContext({ viewport, ...contextOptions });
    const page = configurePage(await context.newPage());
    const noFeedback = feedbackCalls(page);
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: /По названию/i }).click();
    await page.getByLabel(/Название вина/i).fill('Каберне');
    await page.getByRole('button', { name: 'Искать' }).click();
    await visible(page.locator('.candidate-list > button').first(), `${prefix} inline text list`);
    await capture(page, `${prefix}-text-results`);
    const card = page.getByRole('button', { name: /Каберне Совиньон/i }).first();
    const lookup = await context.request.get(`${baseURL}/v2/catalog`, {params:{q:'Каберне'}, timeout:apiTimeout});
    if (!lookup.ok()) throw new Error(`${prefix} Cabernet lookup returned HTTP ${lookup.status()}`);
    const label = await card.getAttribute('aria-label');
    const chosen = (await lookup.json()).candidates.find(item => label === item.name || label.startsWith(`${item.name},`));
    if (!chosen) throw new Error(`${prefix} Cabernet record missing from catalog`);
    const pending = recommendationResponse(page, chosen);
    await card.click();
    await checkCard(page, context, chosen, `${prefix} text card`, true);
    await visible(page.getByRole('heading', { name: /Вам также может подойти/i }), `${prefix} recommendations`);
    await recommendationsReady(page, pending, chosen, `${prefix} text card`);
    await noFeedback();
    await capture(page, `${prefix}-text-card-recommendations`);
    return { context, page, noFeedback };
  };
  await check('CAT015 CAT017 CAT020 mobile live search keeps input and clears to catalog', async () => {
    const context = await browser.newContext({viewport:{width:390,height:844}, ...contextOptions});
    try {
      const page = configurePage(await context.newPage());
      await page.goto(baseURL, {waitUntil:'networkidle'});
      await page.getByRole('button', {name:/По названию/i}).click();
      const input = page.getByLabel(/Название вина/i);
      const searchGeometry = async () => {
        const geometry = await page.locator('.search-field').evaluate(field => {
          const box = field.getBoundingClientRect();
          return {height:box.height, width:box.width, controls:[...field.children].map(el => {
            const r=el.getBoundingClientRect(); return {top:r.top-box.top,bottom:r.bottom-box.top,width:r.width,height:r.height};
          })};
        });
        if (geometry.height > 64 || geometry.controls.some(c => c.top < -1 || c.bottom > geometry.height + 1))
          throw new Error('search input/clear/submit must share one row: '+JSON.stringify(geometry));
        if (geometry.controls.slice(1).some(c => c.width < 44 || c.height < 44))
          throw new Error('search button tap target is smaller than 44px');
      };
      await searchGeometry();
      const fetchQuery = async (q, action = () => input.fill(q)) => {
        const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/v2/catalog' && new URL(r.url()).searchParams.get('q') === q);
        await action();
        const response = await pending;
        if (!response.ok()) throw new Error(`live query returned ${response.status()}`);
        const body = await response.json();
        if (body.catalogVersion !== catalogVersion || body.candidates.length > 24) throw new Error('live query changed catalog or page bounds');
        if (!await input.isVisible() || !await input.evaluate(el => el === document.activeElement)) throw new Error('live query lost editable input focus');
        await searchGeometry();
        await page.waitForFunction(n => document.querySelectorAll('.candidate-list > button').length === n, body.candidates.length);
        return body;
      };
      const first = await fetchQuery('К');
      if (!first.candidates.length) throw new Error('first-letter live search returned no known Cabernet candidate');
      await fetchQuery('Каберне');
      await capture(page, 'mobile-live-search');
      const cleared = await fetchQuery('', () => page.getByRole('button', {name:'Очистить поиск',exact:true}).click());
      if (cleared.candidates[0]?.id !== catalog.candidates[0].id) throw new Error('clear did not restore initial catalog');
      const chosen = cleared.candidates[0];
      await page.locator('.candidate-list > button').first().click();
      await visible(page.getByRole('heading', {name:chosen.name, exact:true}), 'chosen live-search card');
      await page.getByRole('button', {name:'Назад',exact:true}).click();
      await visible(input, 'restored search input');
      if (await input.inputValue() !== '') throw new Error('Back lost query');
      await capture(page, 'mobile-live-search-back');
    } finally { await context.close(); }
  });
  await check('CAT021 mobile refinement keeps card and image in place while response is pending', async () => {
    const context = await browser.newContext({viewport:{width:390,height:760}, ...contextOptions});
    try {
      const page = configurePage(await context.newPage());
      await page.goto(baseURL, {waitUntil:'networkidle'});
      await page.getByRole('button', {name:/По названию/i}).click();
      const input = page.getByLabel(/Название вина/i);
      const firstResponse = page.waitForResponse(response =>
        new URL(response.url()).pathname === '/v2/catalog' && new URL(response.url()).searchParams.get('q') === 'Кабер');
      await input.fill('Кабер');
      const first = await (await firstResponse).json();
      if (!first.candidates.length) throw new Error('CAT021 needs a matching first page');
      await page.waitForFunction(count => document.querySelectorAll('.candidate-list > button').length === count, first.candidates.length);
      await page.evaluate(() => {
        window.__stableSearchCard = document.querySelector('.candidate-list > button');
        window.__stableSearchImage = window.__stableSearchCard?.querySelector('img');
      });
      const stable = () => page.evaluate(() => {
        const card = document.querySelector('.candidate-list > button');
        const image = card?.querySelector('img');
        return {count:document.querySelectorAll('.candidate-list > button').length,
          sameCard:card === window.__stableSearchCard, sameImage:image === window.__stableSearchImage,
          connected:window.__stableSearchCard?.isConnected,
          listTop:document.querySelector('.candidate-list')?.getBoundingClientRect().top,
          cardTop:card?.getBoundingClientRect().top};
      });
      const before = await stable();
      if (!await page.evaluate(() => Boolean(window.__stableSearchImage)))
        throw new Error('CAT021 needs a real first-card image');
      let releaseResponse;
      let requestArrived;
      const held = new Promise(resolve => { releaseResponse = resolve; });
      const arrived = new Promise(resolve => { requestArrived = resolve; });
      let refined;
      await page.route('**/v2/catalog?**', async route => {
        if (new URL(route.request().url()).searchParams.get('q') !== 'Каберн') return route.continue();
        const response = await route.fetch();
        refined = await response.json();
        requestArrived();
        await held;
        await route.fulfill({response});
      });
      try {
        await input.fill('Каберн');
        const debouncing = await stable();
        await bounded(arrived, 'refined catalog request');
        const pending = await stable();
        for (const [phase, state] of [['debounce', debouncing], ['pending', pending]]) {
          if (state.count !== before.count || !state.sameCard || !state.sameImage || !state.connected ||
            Math.abs(state.listTop - before.listTop) > 0.5 || Math.abs(state.cardTop - before.cardTop) > 0.5)
            throw new Error(`${phase} moved or remounted prior results: ${JSON.stringify(state)}`);
        }
        if (await page.getByRole('button', {name:'Показать ещё'}).count()) throw new Error('stale cursor remains available');
        if (!await page.getByRole('status', {name:/прежние результаты/i}).isVisible())
          throw new Error('pending search does not identify previous results');
        if (refined.candidates[0]?.id !== first.candidates[0]?.id)
          throw new Error('CAT021 fixture no longer has a common first card');
        const response = page.waitForResponse(r => new URL(r.url()).pathname === '/v2/catalog' && new URL(r.url()).searchParams.get('q') === 'Каберн');
        releaseResponse();
        await response;
        await page.waitForFunction(count => document.querySelectorAll('.candidate-list > button').length === count, refined.candidates.length);
        await page.getByRole('status', {name:`Показано ${refined.candidates.length}`}).waitFor();
        const after = await stable();
        if (!after.sameCard || !after.sameImage || !after.connected ||
          Math.abs(after.listTop - before.listTop) > 0.5 || Math.abs(after.cardTop - before.cardTop) > 0.5)
          throw new Error('common first card or image moved/remounted after replacement: '+JSON.stringify(after));
      } finally { releaseResponse(); }
    } finally { await context.close(); }
  });
  await check('CAT018 mobile IME searches visible text before composition ends', async () => {
    const context = await browser.newContext({viewport:{width:390,height:640}, isMobile:true, hasTouch:true, ...contextOptions});
    try {
      const page = configurePage(await context.newPage());
      const queries = [];
      page.on('request', request => {
        if (new URL(request.url()).pathname === '/v2/catalog')
          queries.push(new URL(request.url()).searchParams.get('q'));
      });
      await page.goto(baseURL, {waitUntil:'networkidle'});
      await page.getByRole('button', {name:/По названию/i}).click();
      const input = page.getByLabel(/Название вина/i);
      await input.focus();
      await input.evaluate(element => { element.addEventListener('compositionend', () => { window.__imeEnded = true; }); });
      const cdp = await context.newCDPSession(page);
      const pendingResponse = page.waitForResponse(response =>
        new URL(response.url()).pathname === '/v2/catalog' && new URL(response.url()).searchParams.get('q') === 'Каб');
      for (const text of ['К', 'Ка', 'Каб'])
        await cdp.send('Input.imeSetComposition', {text, selectionStart:text.length, selectionEnd:text.length});
      const response = await pendingResponse;
      if (!response.ok()) throw new Error(`IME query returned ${response.status()}`);
      const matches = (await response.json()).candidates;
      if (!matches.length) throw new Error('IME query returned no known Cabernet candidate');
      await page.waitForFunction(n => document.querySelectorAll('.candidate-list > button').length === n, matches.length);
      if (await input.inputValue() !== 'Каб' || !await input.evaluate(element => element === document.activeElement))
        throw new Error('IME query lost visible text or input focus');
      if (await page.evaluate(() => window.__imeEnded)) throw new Error('IME composition ended before live results');
      await cdp.send('Input.insertText', {text:'Каб'});
      await page.waitForTimeout(350);
      if (queries.length !== 1 || queries[0] !== 'Каб') throw new Error(`IME query was duplicated or changed: ${JSON.stringify(queries)}`);
      await capture(page, 'mobile-ime-live-search');
    } finally { await context.close(); }
  });
  await check('name search finds reordered words with a typo', async () => {
    const exact = await releaseContext.request.get(`${baseURL}/v2/catalog`, {
      params: {q:'Каберне Совиньон', limit:60}, timeout:apiTimeout,
    });
    if (!exact.ok()) throw new Error(`exact name query returned ${exact.status()}`);
    const exactItems = (await exact.json()).candidates;
    if (!exactItems?.length) throw new Error('name-search smoke needs the existing Cabernet Sauvignon records');
    const context = await browser.newContext({viewport:{width:390,height:844}, ...contextOptions});
    try {
      const page = configurePage(await context.newPage());
      await page.goto(baseURL, {waitUntil:'networkidle'});
      await page.getByRole('button', {name:/По названию/i}).click();
      const query = 'совиньон кабрене';
      await page.getByLabel(/Название вина/i).fill(query);
      const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/v2/catalog' && new URL(r.url()).searchParams.get('q') === query);
      await page.getByRole('button', {name:'Искать',exact:true}).click();
      const response = await pending;
      if (!response.ok()) throw new Error(`typo query returned ${response.status()}`);
      const found = await bounded(response.json(), 'typo search JSON');
      if (found.catalogVersion !== catalogVersion || !found.candidates?.some(item => item.id === exactItems[0].id))
        throw new Error('reordered words with a typo did not find the known wine');
      if (found.candidates.length > 24) throw new Error('search returned an unbounded page');
      const first = page.locator('.candidate-list > button').first();
      await visible(first, 'typo search result');
      if (!(await first.innerText()).includes(found.candidates[0].name)) throw new Error('UI changed the API relevance order');
      await capture(page, 'mobile-name-search-typo');
    } finally { await context.close(); }
  });
  if (catalog.demo === false) {
    if (!catalog.nextCursor) throw new Error('real catalog smoke requires a second page');
    const response = await releaseContext.request.get(`${baseURL}/v2/catalog?cursor=${encodeURIComponent(catalog.nextCursor)}`, {timeout:apiTimeout});
    if (!response.ok()) throw new Error('second catalog page unavailable');
    const second = await response.json();
    if (!second.candidates?.length || second.catalogVersion !== catalogVersion) throw new Error('second page is invalid');
    const seen = new Set(catalog.candidates.map(item => item.id));
    if (second.candidates.some(item => seen.has(item.id))) throw new Error('catalog pages overlap');
    const query = second.candidates[0].name;
    for (const [name, width, height, dpr] of [['desktop', 1440, 900, 1], ['mobile', 390, 844, 2], ['narrow', 320, 740, 3]]) {
      await check(`${name} real catalog, pagination, search, image and source`, async () => {
        const context = await browser.newContext({viewport:{width,height}, deviceScaleFactor:dpr, ...contextOptions});
        try {
        const page = configurePage(await context.newPage());
        const noFeedback = feedbackCalls(page);
        await page.goto(baseURL, {waitUntil:'networkidle'});
        await page.getByRole('button', {name:/По названию/i}).click();
        await page.getByRole('button', {name:'Открыть каталог', exact:true}).click();
        await page.waitForFunction(n => document.querySelectorAll('.candidate-list > button').length === n, catalog.candidates.length);
        await capture(page, `${name}-catalog-first-page`);
        await page.getByRole('button', {name:'Показать ещё', exact:true}).click();
        await page.waitForFunction(n => document.querySelectorAll('.candidate-list > button').length === n, catalog.candidates.length + second.candidates.length);
        await page.getByLabel(/Название вина/i).fill(query);
        const searchResponse = page.waitForResponse(r => r.url().includes('/v2/catalog?') && new URL(r.url()).searchParams.get('q') === query && r.ok());
        await page.getByRole('button', {name:'Искать', exact:true}).click();
        const search = await (await searchResponse).json();
        if (!search.candidates.some(item => item.id === second.candidates[0].id)) throw new Error('search did not find the item beyond page one');
        const chosen = search.candidates[0];
        const first = page.locator('.candidate-list > button').first();
        await visible(first, 'catalog search result');
        if (!(await first.innerText()).includes(chosen.name)) throw new Error('UI did not display current search response');
        if (!chosen.sourceUrl) throw new Error('real catalog card has no direct source URL');
        const pending = recommendationResponse(page, chosen);
        await first.click();
        await checkCard(page, context, chosen, `${name} real card`, false);
        await visible(page.getByRole('heading', {name:/Вам также может подойти/i}), 'real recommendations');
        await recommendationsReady(page, pending, chosen, `${name} real card`);
        await noFeedback();
        await capture(page, `${name}-real-card-source`);
        } finally { await context.close(); }
      });
    }
    if (!realRecommendationsObserved) throw new Error('No real catalog wine produced working non-empty recommendations');
    await check('real photo upload, recognition, card and recommendations', async () => {
      const file = await requireWinePhoto();
      const detail = await releaseContext.request.get(`${baseURL}/v2/catalog/${encodeURIComponent(photoSlug)}`, {timeout:apiTimeout});
      if (!detail.ok()) throw new Error(`BLOCKED: expected photo slug ${photoSlug} is not in the active display catalog (HTTP ${detail.status()})`);
      const known = await detail.json();
      if (known.demo || !known.candidate?.id || known.canonicalId !== photoSlug ||
        known.candidate.slug !== photoSlug || known.catalogVersion !== catalogVersion)
        throw new Error('BLOCKED: expected photo slug is not a canonical real catalog card');
      const context = await browser.newContext({viewport:{width:390,height:844}, ...contextOptions});
      try {
      const page = configurePage(await context.newPage());
      const noFeedback = feedbackCalls(page);
      await page.goto(baseURL, {waitUntil:'networkidle'});
      const uploadResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/v1/photos');
      const searchResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/v1/search', {timeout:35_000});
      await page.getByLabel(/Загрузить фотографию этикетки/i).setInputFiles(photoSample);
      const upload = await bounded(uploadResponse, 'real photo upload');
      if (upload.status() !== 201) throw new Error(`photo upload returned HTTP ${upload.status()}, expected 201`);
      const receipt = await upload.json();
      if (!/^[a-f0-9]{32}$/.test(receipt.id) || receipt.bytes !== file.size)
        throw new Error('uploaded private photo receipt does not match sample bytes');
      const response = await searchResponse;
      if (response.status() !== 200) throw new Error(`photo recognition returned HTTP ${response.status()}, expected 200`);
      if (response.request().postDataJSON()?.photoId !== receipt.id)
        throw new Error('recognition did not use the uploaded private photo receipt');
      const data = await bounded(response.json(), 'recognition JSON');
      if (data.demo !== false || data.catalogVersion !== catalogVersion || data.recognizedSlug !== photoSlug ||
        data.candidates?.[0]?.id !== known.candidate.id || data.candidates[0].sourceUrl !== known.candidate.sourceUrl)
        throw new Error('photo recognition did not return the verified wine in the active real catalog');
      const cards = page.locator('#UI-006 .candidate-list > button');
      await visible(cards.first(), 'real photo recognition candidates');
      if (!(await cards.first().innerText()).includes(known.candidate.name))
        throw new Error('photo UI first candidate differs from recognition response');
      if (await page.getByRole('note', {name:'Reference-режим'}).count())
        throw new Error('real photo recognition labelled as reference demo');
      await capture(page, 'mobile-real-photo-results');
      const pending = recommendationResponse(page, known.candidate);
      await cards.first().click();
      await checkCard(page, context, known.candidate, 'mobile recognized wine', false);
      await recommendationsReady(page, pending, known.candidate, 'mobile recognized wine');
      await noFeedback();
      await capture(page, 'mobile-real-photo-card');
      } finally { await context.close(); }
    });
  } else {
  await check('desktop text search, card, recommendations', async () => {
    const { context } = await textFlow({ width: 1440, height: 900 }, 'desktop');
    await context.close();
  });
  await check('mobile demo text search, photo upload, card, recommendations', async () => {
    const { context, page, noFeedback } = await textFlow({ width: 390, height: 844 }, 'mobile');
    try {
      const file = await requireWinePhoto(false);
      await page.getByRole('button', { name: /Сканировать ещё/i }).click();
      const uploadResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/v1/photos');
      const searchResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/v1/search', {timeout:35_000});
      await page.getByLabel(/Загрузить фотографию этикетки/i).setInputFiles(photoSample);
      const upload = await bounded(uploadResponse, 'demo photo upload');
      if (upload.status() !== 201) throw new Error(`demo photo upload returned HTTP ${upload.status()}, expected 201`);
      const receipt = await upload.json();
      if (!/^[a-f0-9]{32}$/.test(receipt.id) || receipt.bytes !== file.size)
        throw new Error('demo photo receipt does not match sample bytes');
      const response = await bounded(searchResponse, 'demo photo search');
      if (!response.ok() || response.request().postDataJSON()?.photoId !== receipt.id)
        throw new Error(`demo photo search did not use receipt successfully (HTTP ${response.status()})`);
      const data = await response.json();
      if (data.demo !== true || !data.candidates?.length || data.catalogVersion && data.catalogVersion !== catalogVersion)
        throw new Error('demo photo response has no marked synthetic candidates from active catalog');
      const first = page.locator('#UI-006 .candidate-list > button').first();
      await visible(first, 'mobile demo photo list');
      if (!(await first.innerText()).includes(data.candidates[0].name)) throw new Error('demo photo UI order differs from API');
      await visible(page.getByRole('note', {name:'Reference-режим'}), 'mobile photo demo disclosure');
      await capture(page, 'mobile-photo-results');
      const pending = recommendationResponse(page, data.candidates[0]);
      await first.click();
      await checkCard(page, context, data.candidates[0], 'mobile demo photo card', true);
      await recommendationsReady(page, pending, data.candidates[0], 'mobile demo photo card');
      await noFeedback();
      await capture(page, 'mobile-photo-card-recommendations');
    } finally { await context.close(); }
  });
  }
  await writeFile(resolve(outputDir, 'result.json'), `${JSON.stringify(result('passed'))}\n`);
  console.log(JSON.stringify(result('passed')));
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  await writeFile(resolve(outputDir, 'result.json'), `${JSON.stringify(result('failed', message))}\n`);
  console.error(JSON.stringify(result('failed', message)));
  process.exitCode = 1;
} finally { await browser?.close(); }

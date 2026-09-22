#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises';
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
  const recommendationsReady = async (page) => {
    const list = page.locator('.recommendation-list');
    await visible(list.getByRole('button').first(), 'loaded recommendation cards');
    if (await list.getByRole('button', {name: /Каберне Совиньон/i}).count())
      throw new Error('Recommendation repeats the source wine');
    if (await page.getByText('Подбираем рекомендации', {exact:true}).isVisible())
      throw new Error('Recommendations still loading');
  };
  const textFlow = async (viewport, prefix) => {
    const context = await browser.newContext({ viewport, ...contextOptions });
    const page = configurePage(await context.newPage());
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: /По названию/i }).click();
    await page.getByLabel(/Название вина/i).fill('Каберне');
    await page.getByRole('button', { name: 'Искать' }).click();
    await visible(page.getByRole('heading', { name: /Есть несколько похожих этикеток/i }), `${prefix} text list`);
    await capture(page, `${prefix}-text-results`);
    await page.getByRole('button', { name: /Каберне Совиньон/i }).first().click();
    await visible(page.getByRole('heading', { name: 'Каберне Совиньон' }), `${prefix} text card`);
    await page.getByRole('tab', {name:'Источник', exact:true}).click();
    await visible(page.getByText('Эта карточка создана для демо-каталога.', {exact:true}), `${prefix} demo source disclosure`);
    await page.getByRole('tab', {name:'Обзор', exact:true}).click();
    await visible(page.getByRole('heading', { name: /Вам также может подойти/i }), `${prefix} recommendations`);
    await recommendationsReady(page);
    await capture(page, `${prefix}-text-card-recommendations`);
    return { context, page };
  };
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
        const page = configurePage(await context.newPage());
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
        await first.click();
        await visible(page.getByRole('heading', {name:chosen.name, exact:true}), 'real wine detail');
        const photo = page.locator('.result-hero > img');
        await visible(photo, 'real wine photo');
        await photo.evaluate(image => image.decode());
        const image = await photo.evaluate(el => ({src:el.currentSrc, fit:getComputedStyle(el).objectFit, srcset:el.srcset}));
        const validPaths = chosen.imageVariants.map(v => new URL(v.path, baseURL).href);
        if (!validPaths.includes(image.src) || image.fit !== 'contain' || !image.srcset)
          throw new Error('image selection or contain contract failed');
        if (await page.locator('.demo-label').count()) throw new Error('real card is labelled synthetic');
        if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error('horizontal overflow');
        await page.getByRole('tab', {name:'Источник', exact:true}).click();
        if (await page.getByRole('link', {name:'Открыть исходную запись'}).getAttribute('href') !== chosen.sourceUrl)
          throw new Error('source link differs from accepted catalog');
        await visible(page.getByText('Не удалось загрузить рекомендации.', {exact:true}), 'unavailable reference recommendations');
        await capture(page, `${name}-real-card-source`);
        await context.close();
      });
    }
    await check('real catalog upload does not invent model results', async () => {
      const context = await browser.newContext({viewport:{width:390,height:844}, ...contextOptions});
      const page = configurePage(await context.newPage());
      await page.goto(baseURL, {waitUntil:'networkidle'});
      const searchResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/v1/search');
      await page.getByLabel(/Загрузить фотографию этикетки/i).setInputFiles(resolve(root, 'apps/web/public/assets/app-192.png'));
      const response = await searchResponse;
      if (response.status() !== 503) throw new Error(`reference model returned HTTP ${response.status()}, expected 503`);
      const requestData = response.request().postDataJSON();
      const apiResponse = await context.request.post(`${baseURL}/v1/search`, {data:requestData, timeout:apiTimeout});
      if (apiResponse.status() !== 503) throw new Error(`repeated reference request returned HTTP ${apiResponse.status()}, expected 503`);
      const data = await bounded(apiResponse.json(), 'recognition error JSON');
      if (data.error?.code !== 'recognition_unavailable') throw new Error('reference model must return recognition_unavailable');
      await visible(page.getByRole('heading', {name:'Сервис временно недоступен',exact:true}), 'honest unavailable model state');
      await capture(page, 'mobile-model-unavailable');
      await context.close();
    });
  } else {
  await check('desktop text search, card, recommendations', async () => {
    const { context } = await textFlow({ width: 1440, height: 900 }, 'desktop');
    await context.close();
  });
  await check('mobile text search, upload, card, recommendations', async () => {
    const { context, page } = await textFlow({ width: 390, height: 844 }, 'mobile');
    await page.getByRole('button', { name: /Сканировать ещё/i }).click();
    await page.getByLabel(/Загрузить фотографию этикетки/i).setInputFiles(resolve(root, 'apps/web/public/assets/app-192.png'));
    await visible(page.getByRole('heading', { name: /Есть несколько похожих этикеток/i }), 'mobile photo list');
    await visible(page.getByRole('note', {name:'Reference-режим'}), 'mobile photo demo disclosure');
    await capture(page, 'mobile-photo-results');
    await page.getByRole('button', { name: /Каберне Совиньон/i }).first().click();
    await visible(page.getByRole('heading', { name: 'Каберне Совиньон' }), 'mobile photo card');
    await visible(page.getByRole('heading', { name: /Вам также может подойти/i }), 'mobile photo recommendations');
    await recommendationsReady(page);
    await capture(page, 'mobile-photo-card-recommendations');
    await context.close();
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

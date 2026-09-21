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
const checks = [];
const evidence = [];
let revision;

const check = async (name, work) => {
  try { await work(); checks.push({ name, status: 'passed' }); }
  catch (error) {
    checks.push({ name, status: 'failed', error: error instanceof Error ? error.message : String(error) });
    throw error;
  }
};
const runURL = process.env.GITHUB_SERVER_URL && process.env.GITHUB_REPOSITORY && process.env.GITHUB_RUN_ID
  ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}` : undefined;
const result = (status, error) => ({ revision: expectedRevision || revision || null, observedRevision: revision || null, status, at: new Date().toISOString(), checks, evidence, ...(runURL ? { githubRunURL: runURL } : {}), ...(error ? { error } : {}) });

await mkdir(outputDir, { recursive: true });
let browser;
try {
  if (Boolean(user) !== Boolean(password)) throw new Error('Set both TEST_HTTP_USER and TEST_HTTP_PASSWORD, or neither.');
  browser = await chromium.launch({ headless: true });
  const contextOptions = user ? { httpCredentials: { username: user, password } } : {};
  const releaseContext = await browser.newContext(contextOptions);
  await check('release revision', async () => {
    const response = await releaseContext.request.get(`${baseURL}/release.json`);
    if (!response.ok()) throw new Error(`/release.json returned ${response.status()}`);
    const data = await response.json();
    if (!data || typeof data.revision !== 'string' || !data.revision) throw new Error('/release.json has no revision');
    revision = data.revision;
    if (expectedRevision && revision !== expectedRevision) throw new Error(`revision ${revision} does not match EXPECTED_REVISION`);
  });
  const capture = async (page, name) => {
    const path = resolve(outputDir, `${name}.png`);
    await page.screenshot({ path, fullPage: true });
    evidence.push(path);
  };
  const visible = (locator, description) => locator.waitFor({ state: 'visible', timeout: 10_000 })
    .catch(() => { throw new Error(`${description} is not visible`); });
  const textFlow = async (viewport, prefix) => {
    const context = await browser.newContext({ viewport, ...contextOptions });
    const page = await context.newPage();
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: /По названию/i }).click();
    await page.getByLabel(/Название вина/i).fill('Каберне');
    await page.getByRole('button', { name: 'Искать' }).click();
    await visible(page.getByRole('heading', { name: /Есть несколько похожих этикеток/i }), `${prefix} text list`);
    await visible(page.getByText('Демо-режим'), `${prefix} demo disclosure`);
    await capture(page, `${prefix}-text-results`);
    await page.getByRole('button', { name: /Каберне Совиньон/i }).first().click();
    await visible(page.getByRole('heading', { name: 'Каберне Совиньон' }), `${prefix} text card`);
    await visible(page.getByRole('heading', { name: /Вам также может подойти/i }), `${prefix} recommendations`);
    await capture(page, `${prefix}-text-card-recommendations`);
    return { context, page };
  };
  await check('desktop text search, card, recommendations', async () => {
    const { context } = await textFlow({ width: 1440, height: 900 }, 'desktop');
    await context.close();
  });
  await check('mobile text search, upload, card, recommendations', async () => {
    const { context, page } = await textFlow({ width: 390, height: 844 }, 'mobile');
    await page.getByRole('button', { name: /Сканировать ещё/i }).click();
    await page.getByLabel(/Загрузить фотографию этикетки/i).setInputFiles(resolve(root, 'apps/web/public/assets/app-192.png'));
    await visible(page.getByRole('heading', { name: /Есть несколько похожих этикеток/i }), 'mobile photo list');
    await visible(page.getByText(/Фото не распознаётся/i), 'mobile photo demo disclosure');
    await capture(page, 'mobile-photo-results');
    await page.getByRole('button', { name: /Каберне Совиньон/i }).first().click();
    await visible(page.getByRole('heading', { name: 'Каберне Совиньон' }), 'mobile photo card');
    await visible(page.getByRole('heading', { name: /Вам также может подойти/i }), 'mobile photo recommendations');
    await capture(page, 'mobile-photo-card-recommendations');
    await context.close();
  });
  await writeFile(resolve(outputDir, 'result.json'), `${JSON.stringify(result('passed'))}\n`);
  console.log(JSON.stringify(result('passed')));
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  await writeFile(resolve(outputDir, 'result.json'), `${JSON.stringify(result('failed', message))}\n`);
  console.error(JSON.stringify(result('failed', message)));
  process.exitCode = 1;
} finally { await browser?.close(); }

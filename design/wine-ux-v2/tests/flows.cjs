// Design acceptance checks. No recognition, real camera or platform gallery is tested.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const base=process.env.DESIGN_URL||'http://localhost:8768/';
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('favicon.ico'))errors.push(`${r.status()} ${r.url()}`)});
 const state=()=>page.locator('#phone-content .product-screen').getAttribute('data-state');
 let run=0;
 const open=async(scene)=>{await page.goto(`${base}?mascotPreview=1&scene=${scene}&qa=${++run}#flows`);await page.locator('#phone-content img').evaluateAll(xs=>Promise.all(xs.map(i=>i.decode())));};
 const click=async(go)=>page.locator(`#phone-content [data-go="${go}"]`).first().click();
 const check=async(s)=>assert.equal(await state(),s);
 // Every accepted illustration is present; operational data/camera has no decorative mascot.
 for(const width of [320,390]){
  await page.setViewportSize({width,height:844});
  for(const scene of ['start','loading','waiting','missing','offline','search','result','candidates','permission','badphoto','gallery','preview','settings']){
   await open(scene);await check(scene);
   assert.equal(await page.locator('.v2-mascot-scene,.mascot-secondary-scene').count(),['start','loading','waiting','missing','offline','search'].includes(scene)?1:0,scene);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),scene+' document overflow');
   assert(await page.locator('#phone-content').evaluate(e=>e.scrollWidth<=e.clientWidth+1),scene+' phone overflow');
  }
 }
 // Cancel stops a pending transition and goes home. Snapshot is optional to inspect, not a required step.
 await open('waiting');await click('cancel');await check('start');await page.waitForTimeout(1400);await check('start');
 assert(await page.locator('.resume-photo').isVisible());await click('preview');await check('preview');await click('start');await check('start');await click('retry');await page.waitForTimeout(1400);await check('result');
 await open('offline');await click('retry');await click('cancel');await check('start');await page.waitForTimeout(1400);await check('start');
 // Offline snapshot returns to offline, then recovery reuses it.
 await open('offline');await click('preview');await check('preview');await click('offline');await check('offline');await click('retry');await page.waitForTimeout(1400);await check('result');
 // Inspecting photo during a retry must not revert the recovered outcome to network error.
 await open('offline');await click('retry');await click('preview');await click('loading');await page.waitForTimeout(1400);await check('result');
 // Manual path has no fabricated user photograph and preserves query/results across back navigation.
 await open('start');await click('search');await page.locator('#wine-query').fill('Демо каберне');await page.locator('#product-search button').click();
 assert.equal(await page.locator('.mascot-secondary-scene').count(),0);await page.locator('[data-year="2023"]').click();await check('result');assert.equal(await page.locator('[data-go=preview]').count(),0);await click('search');assert.equal(await page.locator('#wine-query').inputValue(),'Демо каберне');assert(await page.locator('[data-year="2023"]').isVisible());
 await page.locator('#wine-query').fill('Неизвестная этикетка');await page.locator('#product-search button').click();await check('missing');assert.equal(await page.locator('.preserved-photo').count(),0);await click('search');assert.equal(await page.locator('#wine-query').inputValue(),'Неизвестная этикетка');
 // Candidate selection and optional photograph preserve the selected vintage.
 await open('candidates');await page.locator('[data-year="2022"]').click();await check('result');await click('preview');await click('result');assert.match(await page.locator('.result-identity').innerText(),/2022/);await click('candidates');await check('candidates');await click('search');await check('search');
 await open('badphoto');await click('camera');await page.locator('.shutter').click();await page.waitForTimeout(1400);await check('result');
 // New scenario selectors are navigable; no cancelled screen remains in the current catalog.
 await page.goto(base+'#flows');await page.locator('[data-view=flows]').click();
 assert.equal(await page.locator('[data-report-screen=cancelled]').count(),0);
 for(const id of ['happy','vintage','shelf','slow','missing','badphoto','permission','network','wrong','back','manual','stop']){if(await page.locator('.camera-screen').count())await click('start');await page.locator('#mobile-scenario').selectOption(id);assert.equal(await page.locator('.step-list li.current').count(),1,id);}
 for(const [id,outcome] of Object.entries({happy:'result',vintage:'candidates',shelf:'result',slow:'waiting',missing:'missing',badphoto:'badphoto',permission:'result',network:'offline'})){
  if(await page.locator('.camera-screen').count())await click('start');
  await page.locator('#mobile-scenario').selectOption(id);if(!(await page.locator('.camera-screen').count()))await page.locator('#play-scenario').click();
  if(id==='happy'||id==='permission')await page.locator('.scan-primary').click();
  if(id==='permission'){await click('gallery');await click('galleryscan');}else await page.locator('.shutter').click();
  await page.waitForTimeout(1400);await check(outcome);
  if(id==='badphoto'){await click('camera');await page.locator('.shutter').click();await page.waitForTimeout(1400);await check('result');}
 }
 for(const tab of ['references','components','flows','decisions','sources']){await page.locator(`[data-view=${tab}]`).click();assert(await page.locator('#'+tab).isVisible());}
 assert.deepEqual(errors,[]);console.log('PASS: accepted art, mobile fit, cancellation, offline recovery, preview return, manual query, candidate identity, report navigation');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

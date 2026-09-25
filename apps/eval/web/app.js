const basePath=new URL('.',document.currentScript.src).pathname;
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let suite=null, suites=[], runs=[], allRuns=[], imageURLs=new Map(), imagePromises=new Map();
async function api(path,options={}){const r=await fetch(basePath+path.replace(/^\//,''),options);if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return r}
function badge(c){return `<span class="badge ${esc(c.origin_kind)}">${esc(c.origin_kind)}</span>${c.reference_derived?'<span class="badge ref">из каталожного референса</span>':''}`}
async function image(caseID,img){
  const key=`${suite.version}:${suite.suite_hash}:${caseID}`,version=suite.version;
  if(imageURLs.has(key)){img.alt=caseID;img.src=imageURLs.get(key);return}
  if(!imagePromises.has(key))imagePromises.set(key,(async()=>{let r=await api(`/api/baskets/${version}/cases/${encodeURIComponent(caseID)}/image`);let u=URL.createObjectURL(await r.blob());imageURLs.set(key,u);return u})());
  try{const url=await imagePromises.get(key);img.alt=caseID;img.src=url}catch(e){img.alt='Изображение недоступно';imagePromises.delete(key)}
}
const imageObserver='IntersectionObserver' in window?new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting){imageObserver.unobserve(entry.target);image(entry.target.dataset.img,entry.target)}}},{rootMargin:'500px'}):null;
function groupCount(cases){return new Set(cases.map(c=>c.scene_group_id).filter(Boolean)).size}
function statsHTML(){const origins={real:0,ai:0,augmentation:0};for(const c of suite.cases)origins[c.origin_kind]++;$('#summary').innerHTML=`<div class="summary"><div class="stat"><strong>${suite.cases.length}</strong>кейсов</div><div class="stat"><strong>${groupCount(suite.cases)}</strong>групп исходных сцен</div><div class="stat"><strong>${suite.baskets.length}</strong>корзин</div><div class="stat"><strong>${origins.real}</strong>реальных</div><div class="stat"><strong>${origins.ai}</strong>AI</div><div class="stat"><strong>${origins.augmentation}</strong>аугментаций</div><div class="stat"><strong>${runs.length}</strong>прогонов</div></div>`}
function renderGallery(){let byBasket=suite.baskets.map(b=>{let cs=suite.cases.filter(c=>c.basket_ids.includes(b.basket_id));let pending=b.readiness!=='ready'||cs.length<(b.target_count||0);return `<section class="basket"><h2>${esc(b.basket_id)} · ${esc(b.title)}</h2><p>${esc(b.description)} <span class="badge">${esc(b.track)}</span> <span class="badge ${pending?'pending':''}">${cs.length}/${b.target_count||cs.length} · ${esc(b.readiness||'составляется')}</span> <span class="badge">${groupCount(cs)} групп сцен</span></p><div class="cards">${cs.map(c=>`<div class="card" data-case="${esc(c.case_id)}" role="button" tabindex="0" aria-label="Открыть кейс ${esc(c.case_id)}"><img data-img="${esc(c.case_id)}" alt="" loading="lazy"><div class="card-body"><strong>${esc(c.case_id)}</strong><br>${badge(c)}<br><small>SHA-256 ${esc(c.image_sha256.slice(0,12))}…</small></div></div>`).join('')}</div></section>`}).join('');$('#gallery').innerHTML=byBasket;document.querySelectorAll('[data-img]').forEach(el=>imageObserver?imageObserver.observe(el):image(el.dataset.img,el));document.querySelectorAll('[data-case]').forEach(el=>{el.onclick=()=>showCase(el.dataset.case);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showCase(el.dataset.case)}}})}
function ratio(s){if(!s)return '—';return `${s.correct_top1}/${s.graded}${s.ungraded?` · ${s.ungraded} без оценки`:''}`}
function shortRunLabel(r){
  const id=r.run_id;
  if(id.startsWith('test-endpoint-'))return id.includes('archive')?'Тест архива':'Тест API';
  if(id.startsWith('ds-v1-'))return 'DeepSeek v1';
  if(id.startsWith('qwen-v1-'))return 'Qwen v1';
  if(id.startsWith('ds-matcher-v2-'))return 'DeepSeek текст v2';
  if(id.startsWith('qwen-matcher-v2-'))return 'Qwen текст v2';
  if(id.startsWith('rrf60-'))return 'DeepSeek + Qwen RRF';
  if(id.startsWith('paddle-v1-'))return 'PaddleOCR v1';
  const vision=id.match(/^vr-v([12])-(?:context-)?(.+?)-(?:service|retrieval)(?:-metadata-r1)?$/);
  if(vision){
    const branch={all:'все',label:'этикетка',label_ocr:'этикетка + OCR',ocr:'OCR',whole:'вся цель',whole_label:'цель + этикетка',whole_ocr:'цель + OCR'}[vision[2]]||vision[2].replaceAll('_',' + ');
    const revision=id.includes('metadata-r1')?' · r1':vision[1]==='2'?' · ист.':'';
    return `v${vision[1]} · ${branch}${revision}`;
  }
  return r.submission.solution.name.length>22?`${r.submission.solution.name.slice(0,21)}…`:r.submission.solution.name;
}
function matrixCell(score){
  if(!score)return '<td class="run-cell pending" title="Нет результата в этом прогоне" aria-label="Нет результата в этом прогоне">—</td>';
  const outcome=caseOutcome(score);
  const text=!score.graded?'н/о':score.status==='not_run'?'н/з':score.status==='error'?'ош':score.status==='timeout'?'тайм':score.correct?'✓':'×';
  return `<td class="run-cell ${!score.graded?'pending':score.correct?'pass':'fail'}" title="${esc(outcome)}" aria-label="${esc(outcome)}">${esc(text)}</td>`;
}
function matrixBasketCell(r,b){
  if(r.submission.track!==b.track)return '<td class="run-cell pending" title="Другой трек" aria-label="Другой трек">—</td>';
  const score=r.by_basket?.[b.basket_id];
  if(!score)return '<td class="run-cell pending" title="Нет оценки по корзине" aria-label="Нет оценки по корзине">—</td>';
  const full=ratio(score);
  return `<td class="run-cell basket-score" title="${esc(full)}" aria-label="${esc(full)}"><strong>${score.correct_top1}/${score.graded}</strong>${score.ungraded?`<small>+${score.ungraded} н/о</small>`:''}</td>`;
}
function renderMatrix(){
  const head=`<tr><th class="case-col" scope="col">Корзина / кейс</th>${runs.map((r,i)=>{
    const full=`${r.submission.solution.name} ${r.submission.solution.version} · ${r.submission.track} · ${r.run_id}`;
    const track=r.submission.track==='retrieval'?'R':'S';
    return `<th class="run-col" scope="col"><button class="run-head" data-run="${esc(r.run_id)}" title="${esc(full)}" aria-label="Открыть прогон ${esc(full)}"><span class="run-number" aria-hidden="true">${i+1} ${track}</span><span class="run-name" aria-hidden="true">${esc(shortRunLabel(r))}</span></button></th>`;
  }).join('')}</tr>`;
  const rows=suite.baskets.map(b=>{
    const cs=suite.cases.filter(c=>c.basket_ids.includes(b.basket_id));
    const basket=`<tr class="basket-row"><th class="case-col" scope="row"><strong>${esc(b.basket_id)}</strong> ${esc(b.title)} <span class="badge">${esc(b.track)}</span></th>${runs.map(r=>matrixBasketCell(r,b)).join('')}</tr>`;
    const cases=cs.map(c=>`<tr class="case-row"><th class="case-col" scope="row"><a href="#" data-case-link="${esc(c.case_id)}">${esc(c.case_id)}</a> ${badge(c)}</th>${runs.map(r=>matrixCell(r.cases.find(x=>x.case_id===c.case_id))).join('')}</tr>`).join('');
    return basket+cases;
  }).join('');
  $('#matrix').innerHTML=`<p class="matrix-hint">${runs.length} прогонов · S = service, R = retrieval · ✓ верно, × неверно, н/о без оценки, н/з не запущен, ош ошибка, тайм таймаут. «ист.» — исходная отправка label-context-v2 с ошибочной версией решения в метаданных; r1 — исправленная запись. Прокрутите таблицу вправо; откройте заголовок для полных деталей.</p><div class="matrix-wrap"><table class="run-grid" style="width:${205+60*runs.length}px"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`;
  document.querySelectorAll('[data-case-link]').forEach(el=>el.onclick=e=>{e.preventDefault();showCase(el.dataset.caseLink)});
  document.querySelectorAll('[data-run]').forEach(el=>el.onclick=()=>showRun(el.dataset.run));
}
function caseOutcome(score){
  if(!score.graded)return 'без оценки';
  if(score.correct)return 'верно';
  if(score.status==='ok')return 'неверное совпадение';
  if(score.status==='timeout')return 'таймаут';
  if(score.status==='error')return 'ошибка выполнения';
  if(score.status==='not_run')return 'не запущен';
  return esc(score.status);
}
function openDetail(html){
  const dialog=$('#detail');
  if(dialog.open)dialog.close();
  dialog.innerHTML=`<div class="detail-head"><button type="button" data-close-detail aria-label="Закрыть детали">Закрыть ×</button></div>${html}`;
  dialog.querySelector('[data-close-detail]').onclick=()=>dialog.close();
  dialog.showModal();
}
function showCase(id){
  const c=suite.cases.find(x=>x.case_id===id);
  const res=runs.filter(r=>r.cases.some(x=>x.case_id===id)).map(r=>({run:r.run_id,solution:r.submission.solution.name,score:r.cases.find(x=>x.case_id===id)}));
  openDetail(`<h2>${esc(id)}</h2><div class="detail-grid"><img id="detail-img" alt=""><div>${badge(c)}<p>Корзины: ${c.basket_ids.map(esc).join(', ')}</p><p>Трек: ${esc(c.tracks.join(', '))}</p><p>Группа исходной сцены: <code>${esc(c.scene_group_id||'не указана')}</code></p><p class="correlation-note">Варианты одного снимка связаны; число кейсов не равно числу независимых сцен.</p><p>SHA-256: <code>${esc(c.image_sha256)}</code></p><h3>Результаты</h3>${res.length?res.map(x=>`<p><strong>${esc(x.solution)} · ${esc(x.run)}</strong>: ${caseOutcome(x.score)}</p>`).join(''):'<p>Прогонов пока нет.</p>'}</div></div>`);
  image(id,$('#detail-img'));
}
function statTable(groups,track){
  const ranking=track==='retrieval';
  return `<div class="matrix-wrap"><table><thead><tr><th>Группа</th><th>Top-1</th>${ranking?'<th>Top-5</th><th>Top-20</th><th>MRR</th>':''}<th>Без оценки</th></tr></thead><tbody>${Object.entries(groups||{}).map(([name,v])=>`<tr><td>${esc(name)}</td><td>${v.correct_top1}/${v.graded}</td>${ranking?`<td>${v.correct_top5}/${v.graded}</td><td>${v.correct_top20}/${v.graded}</td><td>${Number(v.mrr).toFixed(3)}</td>`:''}<td>${v.ungraded}</td></tr>`).join('')}</tbody></table></div>`
}
function showRun(id){
  const r=runs.find(x=>x.run_id===id), ranking=r.submission.track==='retrieval';
  openDetail(`<h2>${esc(r.run_id)}</h2><p>${esc(r.submission.solution.name)} ${esc(r.submission.solution.version)} · ${esc(r.submission.track)} · ${esc(r.received_at)}</p><div class="summary"><div class="stat"><strong>${ratio(r.overall)}</strong>top-1 / оценено</div>${ranking?`<div class="stat"><strong>${r.overall.correct_top5}/${r.overall.graded}</strong>top-5</div><div class="stat"><strong>${r.overall.correct_top20}/${r.overall.graded}</strong>top-20</div><div class="stat"><strong>${r.overall.mrr.toFixed(3)}</strong>MRR</div>`:''}</div><h3>По происхождению</h3>${statTable(r.by_origin,r.submission.track)}<h3>Независимость от каталога</h3>${statTable(r.by_reference,r.submission.track)}<p>Пропущено: ${r.overall.missing}. Без оценки: ${r.overall.ungraded}. Независимых групп сцен: ${r.unique_scene_groups}.</p>`);
}
function selectSuite(version){
  suite=suites.find(s=>s.version===version);
  if(!suite)return;
  runs=allRuns.filter(r=>r.submission?.suite_version===suite.version&&r.submission?.suite_hash===suite.suite_hash);
  $('#suite-version').value=suite.version;
  $('#suite').textContent=`SHA ${suite.suite_hash.slice(0,12)}…`;
  $('#header-version').textContent=`Открытый стенд · ${suite.version}`;
  $('#role').textContent='публичный просмотр';
  if($('#detail').open)$('#detail').close();
  statsHTML();renderGallery();renderMatrix();
}
async function load(){try{
  suites=await(await api('/api/baskets')).json();
  if(!suites.length)throw new Error('Нет доступных версий корзин');
  allRuns=await(await api('/api/runs')).json();
  suites.sort((a,b)=>b.version.localeCompare(a.version,undefined,{numeric:true}));
  const picker=$('#suite-version');
  picker.replaceChildren(...suites.map(s=>new Option(s.version,s.version)));
  const requested=new URLSearchParams(location.search).get('suite');
  selectSuite(suites.some(s=>s.version===requested)?requested:suites[0].version);
  picker.onchange=()=>{selectSuite(picker.value);const url=new URL(location.href);url.searchParams.set('suite',picker.value);history.replaceState(null,'',url)};
}catch(e){$('#notice').textContent=`Не удалось загрузить данные: ${e.message}`}}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#gallery').hidden=b.dataset.tab!=='gallery';$('#matrix').hidden=b.dataset.tab!=='matrix';if($('#detail').open)$('#detail').close()});$('#download').onclick=async()=>{try{let r=await api(`/api/baskets/${suite.version}/download`);let u=URL.createObjectURL(await r.blob());let a=document.createElement('a');a.href=u;a.download=`lct-eval-${suite.version}.zip`;a.click();setTimeout(()=>URL.revokeObjectURL(u),30000)}catch(e){alert(e.message)}};load();

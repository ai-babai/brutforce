function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function gateRow(name,g){const tr=el('tr');tr.append(el('th',name),el('td',g?.status||'missing',`status ${g?.status||'missing'}`),el('td',g?.summary||g?.note||''));return tr}
function failureText(f){if(typeof f==='string')return f;return [f.slug&&`slug: ${f.slug}`,f.path&&`path: ${f.path}`,f.message].filter(Boolean).join(' · ')}
function caseTable(title,cases){const section=el('section');section.append(el('h3',title));const table=el('table');for(const c of cases){const tr=el('tr');const detail=[c.section&&`Раздел: ${c.section}`,c.summary,...(c.failures||[]).map(failureText)].filter(Boolean).join(' · ');tr.append(el('th',c.id+' · '+c.title),el('td',c.status,`status ${c.status}`),el('td',detail));table.append(tr)}section.append(table);return section}
fetch('status.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(data=>{
 document.querySelector('#updated').textContent='Снимок: '+data.updatedAt+' · обновите страницу для нового состояния';
 for(const [env,value]of Object.entries(data.environments)){const shown=typeof value==='string'?value.slice(0,12):value?.candidateId?.slice(0,12)||value?.revision?.slice(0,12);document.querySelector('#env').append(el('p',env.toUpperCase()+': '+(shown||'не выкатили')))}
 for(const r of data.releases){const card=el('article');const cid=r.candidateId||r.revision;card.append(el('h2','Кандидат '+cid.slice(0,12)));
  card.append(el('p',`App ${r.revision.slice(0,12)} · Data ${r.catalogVersion||'demo-v1'} / ${r.catalogManifestSHA256?.slice(0,12)||'встроенный demo'} · Model ${r.mode}/${r.modelVersion||'reference-demo-v1'}`));
  const a=el('a','Проверки и сборка GitHub');a.href=r.ciURL;card.append(a);
  const app=el('table');for(const name of ['ci','test','browser'])app.append(gateRow(name,r.gates[name]));const appSection=caseTable('App',[]);appSection.append(app);card.append(appSection);
  const report=r.gates.data?.report;if(report){card.append(el('p',`Data report: ${report.completedAt} · validator ${report.validatorVersion?.slice(0,12)}${r.gates.data.reusedFrom?' · переиспользован из '+r.gates.data.reusedFrom:''}`));card.append(caseTable('Data',(report.cases||[]).filter(c=>/^DQ00[1-8]$|^DQ011$/.test(c.id))))}
  else card.append(caseTable('Data',[{id:'DQ001–DQ011',title:'Отчёт для встроенного demo не применялся',status:r.synthetic?'n/a':'missing'}]));
  card.append(caseTable('Placement',r.gates.placement?.cases||[{id:'DQ009–DQ010',title:'Проверки целевой среды',status:r.gates.placement?.status||'pending'}]));
  card.append(el('p',r.approval?'PROD разрешил '+r.approval.actor+' · '+r.approval.at:'Разрешения на PROD нет'));document.querySelector('#releases').append(card)
 }
 if(!data.releases.length)document.querySelector('#releases').append(el('p','Кандидатов пока нет.'));
}).catch(()=>document.querySelector('#updated').textContent='Не удалось получить журнал. Готовность неизвестна; выкатку не разрешать.');

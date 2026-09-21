function el(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
fetch('status.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(data=>{
 document.querySelector('#updated').textContent='Снимок: '+data.updatedAt+' · обновите страницу для нового состояния';
 for(const [env,sha]of Object.entries(data.environments))document.querySelector('#env').append(el('p',env.toUpperCase()+': '+(sha?.slice(0,12)||'не выкатили')));
 for(const r of data.releases){const card=el('article');card.append(el('h2',r.revision.slice(0,12)),el('p','Режим: '+r.mode+' · качество модели: не измерено'));
 const a=el('a','Проверки и сборка GitHub');a.href=r.ciURL;card.append(a);
 const table=el('table');for(const [name,g]of Object.entries(r.gates)){const tr=el('tr');tr.append(el('th',name),el('td',g.status),el('td',g.summary||g.note||''));table.append(tr);}card.append(table);
 card.append(el('p',r.approval?'Разрешил '+r.approval.actor+' · '+r.approval.at:'Разрешения на PROD нет'));
 const details=el('details');details.append(el('summary','Полный отчёт'),el('pre',JSON.stringify(r,null,2)));card.append(details);document.querySelector('#releases').append(card);
 }
 if(!data.releases.length)document.querySelector('#releases').append(el('p','Пакетов пока нет.'));
}).catch(()=>document.querySelector('#updated').textContent='Не удалось получить журнал. Готовность неизвестна; выкатку не разрешать.');

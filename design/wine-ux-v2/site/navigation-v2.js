// Report navigation is separate from the product's in-screen actions.
(()=>{
 const standalone=new URLSearchParams(location.search).get('mascotPreview')==='1';
 const screens=[['start','Главная'],['camera','Камера'],['gallery','Галерея'],['loading','Поиск'],['waiting','Долгое ожидание'],['candidates','Похожие вина'],['result','Карточка'],['preview','Исходное фото'],['missing','Не нашли'],['badphoto','Плохое фото'],['permission','Доступ к камере'],['settings','Настройки доступа'],['offline','Нет сети'],['cancelled','Отмена'],['search','По названию']];
 const outcomes={happy:'result',vintage:'candidates',shelf:'camera',slow:'waiting',missing:'missing',badphoto:'badphoto',permission:'permission',network:'offline',wrong:'result',back:'preview'};
 const views=['references','components','flows','decisions','sources'];
 const oldNav=navTo;
 navTo=function(id){if(!views.includes(id))return;oldNav(id);if(!standalone){document.querySelector('#'+id).scrollIntoView({block:'start'});}};
 const controls=document.createElement('div');controls.className='screen-browser';controls.innerHTML=`<div><strong>Все экраны 2.0</strong><span>Открывайте любой экран напрямую или проходите сценарий кнопками внутри телефона.</span></div><div class="screen-buttons">${screens.map(([id,name])=>`<button data-report-screen="${id}" aria-pressed="false">${name}</button>`).join('')}</div><div class="screen-browser-status"><span id="visible-screen-label"></span><button id="play-scenario">Пройти сценарий с начала →</button></div>`;
 document.querySelector('#scenario-picker').after(controls);
 const scenarioSelect=document.createElement('label');scenarioSelect.className='mobile-report-select';scenarioSelect.innerHTML=`Сценарий <select id="mobile-scenario">${scenarios.map(s=>`<option value="${s.id}">${esc(s.label)}</option>`).join('')}</select>`;document.querySelector('#scenario-picker').before(scenarioSelect);
 controls.querySelector('.screen-buttons').insertAdjacentHTML('beforebegin',`<label class="mobile-report-select">Экран <select id="mobile-screen">${screens.map(([id,name])=>`<option value="${id}">${name}</option>`).join('')}</select></label>`);
 document.querySelector('#mobile-screen').onchange=e=>openScreen(e.target.value);
 document.querySelector('#mobile-scenario').onchange=e=>document.querySelector(`[data-scenario="${e.target.value}"]`).click();
 const originalRender=renderPhone;
 document.addEventListener('click',e=>{if(e.target.closest('#phone-content button'))requestAnimationFrame(()=>{if(!standalone)document.querySelector('.prototype-stage').scrollIntoView({block:'start'});});},true);
 renderPhone=function(){originalRender();document.querySelector('#mobile-screen').value=screen;document.querySelector('#mobile-scenario').value=scenario.id;document.querySelectorAll('[data-report-screen]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.reportScreen===screen)));document.querySelector('#visible-screen-label').textContent='На экране: '+(screens.find(s=>s[0]===screen)?.[1]||'Карточка');if(!standalone){const u=new URL(location.href);u.searchParams.set('screen',screen);u.searchParams.set('scenario',scenario.id);history.replaceState(null,'',u);}};
 let stepIndex=0,stepScenario='';
 const originalScenario=renderScenario;
 renderScenario=function(){originalScenario();if(stepScenario!==scenario.id){stepIndex=0;stepScenario=scenario.id;}const matches=scenario.steps.map((s,i)=>s[0]===screen?i:-1).filter(i=>i>=0);if(matches.length&&!matches.includes(stepIndex))stepIndex=matches.find(i=>i>=stepIndex)??matches[0];document.querySelectorAll('.step-list li').forEach((li,i)=>{const [id,label]=scenario.steps[i];const active=i===stepIndex&&matches.includes(i);li.classList.toggle('current',active);li.innerHTML=`<button data-step-screen="${id}" aria-current="${active?'step':'false'}">${esc(label)}</button>`;li.querySelector('button').onclick=()=>{stepIndex=i;setScreen(id);};});if(!matches.length){const li=document.createElement('li');li.className='current';li.textContent='Дополнительный экран: '+(screens.find(s=>s[0]===screen)?.[1]||'Карточка');document.querySelector('.step-list').append(li);}};
 for(const id of ['missing','badphoto']){const s=scenarios.find(s=>s.id===id);if(!s.steps.some(x=>x[0]==='loading'))s.steps.splice(1,0,['loading','Поиск']);}
 const contextFor={start:'happy',camera:'happy',gallery:'happy',loading:'happy',waiting:'slow',candidates:'vintage',result:'happy',catalog:'happy',preview:'back',missing:'missing',badphoto:'badphoto',permission:'permission',settings:'permission',offline:'network',cancelled:'slow',search:'missing'};
 function openScreen(id){scenario=scenarios.find(s=>s.id===contextFor[id])||scenarios[0];stepIndex=0;setScreen(id);}
 function reveal(id){openScreen(id);navTo('flows');if(!standalone)document.querySelector('.screen-browser').scrollIntoView({block:'start'});}
 document.querySelectorAll('[data-report-screen]').forEach(b=>b.onclick=()=>openScreen(b.dataset.reportScreen));
 document.querySelectorAll('[data-scenario]').forEach(b=>b.onclick=()=>{scenario=scenarios.find(s=>s.id===b.dataset.scenario);selectedYear='2023';detailTab='overview';searched=false;setScreen(outcomes[scenario.id]||'start');});
 document.querySelector('#play-scenario').onclick=()=>{stepIndex=0;selectedYear='2023';detailTab='overview';searched=false;setScreen(scenario.steps[0][0]);};
 document.addEventListener('click',e=>{const b=e.target.closest('[data-brand-screen]');if(b){e.preventDefault();reveal(b.dataset.brandScreen);}});
 // Delegation also covers component examples re-rendered by filters.
 document.addEventListener('click',e=>{const b=e.target.closest('[data-component-try],[data-v2-go]');if(b)reveal(b.dataset.componentTry||b.dataset.v2Go);});
 const initial=new URLSearchParams(location.search);const initialScenario=scenarios.find(s=>s.id===initial.get('scenario'));if(initialScenario)scenario=initialScenario;
 if(!standalone&&screens.some(s=>s[0]===initial.get('screen')))screen=initial.get('screen');
 renderPhone();renderScenario();
})();

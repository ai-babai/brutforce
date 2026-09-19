(function(){
  const app=document.querySelector('#app');
  const params=new URLSearchParams(location.search);
  let scene=['start','waiting','missing'].includes(params.get('scene'))?params.get('scene'):'start';
  const variation=params.get('variation')==='overlap'?'overlap':'landscape';
  const icon=name=>`<span class="ui-icon" aria-hidden="true">${(window.ATLAS_ICONS||{})[name]||''}</span>`;
  const mascot='<img class="mascot" src="assets/detective-alpha.png" alt="Пёс-детектив внимательно изучает этикетку">';
  const bottle='<img class="stage-bottle" src="v1/assets/concept-bottle.png" alt="Демонстрационная бутылка вина">';
  const vines=`<svg class="vine left" viewBox="0 0 88 124" fill="none" aria-hidden="true"><path d="M45 124C49 91 45 56 24 19M31 36C14 39 9 50 8 63M39 63C58 57 69 44 72 28M43 89C23 82 15 72 12 60" stroke="currentColor"/><circle cx="22" cy="17" r="3" fill="currentColor"/><circle cx="72" cy="27" r="3" fill="currentColor"/></svg><svg class="vine right" viewBox="0 0 88 124" fill="none" aria-hidden="true"><path d="M45 124C49 91 45 56 24 19M31 36C14 39 9 50 8 63M39 63C58 57 69 44 72 28M43 89C23 82 15 72 12 60" stroke="currentColor"/><circle cx="22" cy="17" r="3" fill="currentColor"/><circle cx="72" cy="27" r="3" fill="currentColor"/></svg>`;
  const topbar=(back=false)=>`<header class="topbar"><div class="brand">своё вино<i></i></div>${back?`<button class="top-action" data-scene="start" aria-label="На главную">${icon('x')}</button>`:'<span></span>'}</header>`;
  function scanButton(label='Сканировать вино',sub='Наведите на этикетку'){
    return `<button class="primary" data-route="camera">${icon('camera')}<span><strong>${label}</strong><small>${sub}</small></span><span class="scan-mark">${icon('scan')}</span></button>`;
  }
  function start(){return `<div class="app-shell ${variation}">${topbar()}<section class="scene start-scene"><div class="intro"><p class="kicker">Ваш винный детектив</p><h1>Что за вино<br>перед вами?</h1><p>Сфотографируйте этикетку.<br>Откроем карточку вина.</p></div><div class="world">${vines}${bottle}${mascot}</div><div class="action-panel">${scanButton()}<div class="entry-alternatives"><button data-route="gallery">${icon('photo')} Выбрать фото</button><button data-route="search">${icon('search')} По названию</button></div></div></section></div>`}
  function waiting(){return `<div class="app-shell ${variation}">${topbar(true)}<section class="scene"><div class="waiting-head"><p class="kicker">Ищем совпадение</p><h1>Нужно чуть<br>больше времени</h1><p>Поиск ещё идёт. Снимок остаётся здесь.</p></div><div class="search-stage"><div class="photo"><img src="v1/assets/concept-bottle.png" alt="Сохранённый снимок этикетки"><span class="photo-tag">Ваш снимок</span></div><img class="mascot" src="assets/search-alpha.png" alt="Пёс-детектив сравнивает снимок с заметками"></div><div class="status" role="status"><i class="pulse"></i>Продолжаем поиск</div><div class="waiting-actions"><button class="secondary" data-route="result">Демо: получить результат</button><button class="text-button" data-scene="start">Отменить поиск</button></div></section></div>`}
  function missing(){return `<div class="app-shell ${variation}">${topbar(true)}<section class="scene"><div class="missing-layout"><div class="copy"><p class="kicker">Совпадения нет</p><h1>Не нашли<br>это вино</h1><p>Попробуйте название или другое фото. Возможно, карточки пока нет в каталоге.</p></div><div class="missing-photo"><img src="v1/assets/concept-bottle.png" alt="Сохранённый снимок этикетки"><span>Ваш снимок</span></div><div class="missing-figure">${mascot}</div></div><div class="missing-actions"><button class="primary" data-route="search">${icon('search')}<span><strong>Найти по названию</strong></span><i></i></button><button class="secondary" data-route="camera">Переснять этикетку</button></div></section></div>`}
  function notify(){parent.postMessage({type:'composition-scene',scene},location.origin)}
  function render(){app.innerHTML=scene==='waiting'?waiting():scene==='missing'?missing():start();document.documentElement.dataset.scene=scene;notify()}
  app.addEventListener('click',e=>{
    const trigger=e.target.closest('[data-scene],[data-route]');if(!trigger)return;
    if(trigger.dataset.route){location.href=`v1/index.html?mascotPreview=1&scene=${trigger.dataset.route}&mode=off#flows`;return}
    scene=trigger.dataset.scene;const next=new URL(location.href);next.searchParams.set('scene',scene);history.replaceState(null,'',next);render();
  });
  render();
})();

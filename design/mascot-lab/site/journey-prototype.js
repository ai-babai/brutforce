(function(){
  const app=document.querySelector('#app');
  const allowed=['home','loading','cellar','missing','result','camera'];
  const requested=new URLSearchParams(location.search).get('scene');
  let scene=allowed.includes(requested)?requested:'home';
  const icon=name=>`<span class="ui-icon" aria-hidden="true">${(window.ATLAS_ICONS||{})[name]||''}</span>`;
  const topbar=(closable=false)=>`<header class="topbar"><div class="wordmark">своё вино<i></i></div>${closable?`<button class="close" data-scene="home" aria-label="Вернуться на главную">${icon('x')}</button>`:'<span></span>'}</header>`;
  const shell=content=>`<div class="phone">${content}</div>`;

  function home(){return shell(`${topbar()}<section class="scene"><div class="home-copy"><p class="eyebrow">Поиск по этикетке</p><h1>Что за вино<br>перед вами?</h1><p class="lead">Сфотографируйте этикетку.<br>Откроем карточку вина.</p></div><div class="home-actions"><button class="scan" data-scene="camera">${icon('camera')}<span class="scan-copy"><strong>Сканировать вино</strong><small>Наведите на этикетку</small></span><span class="scan-mark">${icon('scan')}</span></button><div class="alternatives"><button data-route="gallery">${icon('photo')} Выбрать фото</button><button data-route="search">${icon('search')} По названию</button></div></div><div class="helper-space" data-helper><img class="helper-dog" src="assets/journey/peek.png" alt="Пёс-помощник выглядывает из-за карточки"><aside class="helper-card"><strong>Подскажу с кадром</strong><p>Держите название и год в центре — так их легче сверить.</p><button class="dismiss" data-dismiss>Понятно</button></aside></div></section>`)}
  function loading(){return shell(`${topbar(true)}<section class="scene"><div class="waiting-copy"><p class="eyebrow">Один момент</p><h1>Ищем вино</h1><p class="lead">Сопоставляем снимок с каталогом</p></div><div class="loading-vignette"><img class="loading-dog" src="assets/search-alpha.png" alt="Пёс сидит с блокнотом и изучает снимок"></div><div class="quiet-status" role="status"><i></i>Ищем совпадение</div><div class="bottom-actions"><button class="text-action" data-scene="home">Отменить поиск</button></div></section>`)}
  function cellar(){return shell(`${topbar(true)}<section class="scene"><div class="cellar-copy"><p class="eyebrow">Поиск продолжается</p><h1>Ищем совпадение</h1><p class="lead">Иногда этикетку нужно сверить чуть внимательнее.</p></div><img class="cellar-scene" src="assets/journey/cellar.png" alt="Пёс изучает винную этикетку в погребе"><div class="cellar-footer"><button class="origin-row" data-enlarge aria-label="Увеличить исходный демонстрационный снимок"><img src="v1/assets/concept-bottle.png" alt=""><span><strong>Исходный снимок</strong><small>Демонстрационная этикетка</small></span>${icon('zoom-in')}</button><div class="cellar-controls"><button class="text-action" data-scene="home">Отменить</button><button class="secondary" data-scene="result">Демо: результат</button></div></div></section><button class="lightbox" data-lightbox hidden aria-label="Закрыть увеличенный снимок"><img src="v1/assets/concept-bottle.png" alt="Демонстрационная бутылка вина крупным планом"><span>Закрыть</span></button>`)}
  function missing(){return shell(`${topbar(true)}<section class="scene missing-scene"><div class="missing-copy"><p class="eyebrow">Совпадения нет</p><h1>Не нашли совпадение</h1><p class="lead">Возможно, этого вина пока нет в каталоге. Попробуйте название или другое фото.</p></div><div class="counter-space"><img class="counter-dog" src="assets/journey/counter.png" alt="Пёс поднимается из-за стойки и предлагает помощь"></div><div class="help-panel"><button class="primary" data-route="search">${icon('search')} Найти по названию</button><button class="secondary" data-scene="camera">Переснять этикетку</button><button class="photo-access" data-route="gallery">${icon('photo')} Выбрать другой снимок</button><button class="missing-original" data-enlarge>Посмотреть исходный снимок</button></div></section><button class="lightbox" data-lightbox hidden aria-label="Закрыть исходный снимок"><img src="v1/assets/concept-bottle.png" alt="Исходная демонстрационная бутылка"><span>Закрыть</span></button>`)}
  function embedded(){return `<iframe class="embedded" title="${scene==='camera'?'Камера':'Карточка вина'}" src="v1/index.html?mascotPreview=1&scene=${scene}&mode=off#flows"></iframe>`}
  function notify(){if(parent!==window)parent.postMessage({type:'journey-scene',scene},location.origin)}
  function render(){app.innerHTML=scene==='home'?home():scene==='loading'?loading():scene==='cellar'?cellar():scene==='missing'?missing():embedded();document.documentElement.dataset.scene=scene;notify()}
  function setScene(next){scene=next;const url=new URL(location.href);url.searchParams.set('scene',scene);history.replaceState(null,'',url);render()}
  app.addEventListener('click',event=>{
    const target=event.target.closest('[data-scene],[data-route],[data-dismiss],[data-enlarge],[data-lightbox]');
    if(!target)return;
    if(target.dataset.dismiss!==undefined){target.closest('[data-helper]').remove();return}
    if(target.dataset.enlarge!==undefined){app.querySelector('[data-lightbox]').hidden=false;return}
    if(target.dataset.lightbox!==undefined){target.hidden=true;return}
    if(target.dataset.route){location.href=`v1/index.html?mascotPreview=1&scene=${target.dataset.route}&mode=off#flows`;return}
    setScene(target.dataset.scene);
  });
  render();
})();

(function(){
  const app=document.querySelector('#app');
  const allowed=['home','loading','cellar','missing','cancelled','result','camera'];
  const params=new URLSearchParams(location.search);
  const requested=params.get('scene');
  const artStyle=params.get('art')==='3d'?'3d':'2d';
  const theme=params.get('theme')==='atlas'?'atlas':'svoe';document.documentElement.dataset.theme=theme;
  const homeVariants=['counter','hold','bottle'];
  const requestedHome=params.get('home');
  let scene=allowed.includes(requested)?requested:'home';
  let homeVariant=homeVariants.includes(requestedHome)?requestedHome:'counter';
  let tipOpen=true;
  const sourcePhoto='v1/assets/concept-bottle.png';
  const icon=name=>`<span class="ui-icon" aria-hidden="true">${(window.ATLAS_ICONS||{})[name]||''}</span>`;
  const wordmark=theme==='svoe'?'<img class="official-logo" src="assets/svoe-v5/svoe-vino-logo.svg" alt="Своё Вино">':'<span class="wordmark">своё<span>вино</span></span>';
  const topbar=(action='none')=>`<header class="topbar">${wordmark}${action==='none'?'<span class="quiet-badge">Поиск по этикетке</span>':`<button class="close" data-scene="${action==='cancel'?'cancelled':'home'}" aria-label="${action==='cancel'?'Отменить поиск':'Вернуться на главную'}">${icon('x')}</button>`}</header>`;
  const shell=content=>`<div class="phone">${content}</div>`;
  const photoRow=()=>`<button class="origin-row" data-enlarge aria-label="Увеличить исходный демонстрационный снимок"><img src="${sourcePhoto}" alt=""><span><strong>Исходный снимок</strong><small>Демонстрационная этикетка</small></span>${icon('zoom-in')}</button>`;
  const lightbox=()=>`<button class="lightbox" data-lightbox hidden aria-label="Закрыть исходный снимок"><img src="${sourcePhoto}" alt="Исходная демонстрационная бутылка"><span>Закрыть</span></button>`;

  function homeArt(){
    if(homeVariant==='bottle')return `<div class="home-art home-art-bottle"><img src="${sourcePhoto}" alt="Демонстрационная бутылка вина"><span>Базовая композиция без маскота</span></div>`;
    const label=homeVariant==='hold'?'Пёс держит бутылку вина':'Пёс рядом с бутылкой на винной стойке';
    return `<div class="home-art"><img src="assets/integration/home-${homeVariant}${artStyle==='2d'?'-2d':''}.png" alt="${label}"></div>`;
  }
  function homeTip(){
    if(!tipOpen)return `<aside class="start-tip is-compact"><button data-tip-open>${icon('focus-2')}<span>Как снять этикетку</span>${icon('chevron-down')}</button></aside>`;
    return `<aside class="start-tip"><span class="tip-icon">${icon('focus-2')}</span><div><strong>Нужная бутылка по центру</strong><p>Поверните этикетку к камере. Соседние бутылки могут быть в кадре.</p><button class="dismiss" data-dismiss>Понятно</button></div></aside>`;
  }
  function home(){return shell(`<section class="scene home-scene">${topbar()}<div class="home-copy"><h1>Что за вино<br>перед вами?</h1><p class="lead">Сфотографируйте этикетку.<br>Откроем карточку вина.</p></div>${homeArt()}<div class="home-actions"><button class="scan" data-scene="camera">${icon('camera')}<span class="scan-copy"><strong>Сканировать вино</strong><small>Наведите на этикетку</small></span><span class="scan-mark">${icon('scan')}</span></button><div class="alternatives"><button data-route="gallery">${icon('photo')} Выбрать фото</button><button data-route="search">${icon('search')} По названию</button></div></div><div class="tip-slot">${homeTip()}</div><footer class="scanner-footer">Информация о российских винах</footer></section>`)}
  function loading(){return shell(`${topbar('cancel')}<section class="scene loading-scene"><div class="waiting-copy"><p class="eyebrow">Один момент</p><h1>Ищем вино</h1><p class="lead">Сопоставляем снимок с каталогом</p></div><img class="loading-cellar" src="assets/journey/cellar.png" alt="Пёс сверяет винную этикетку в погребе"><div class="loading-footer"><div class="quiet-status" role="status"><i></i>Ищем совпадение</div>${photoRow()}<button class="text-action" data-scene="cancelled">Отменить поиск</button></div></section>${lightbox()}`)}
  function cellar(){return shell(`${topbar('cancel')}<section class="scene cellar-state"><div class="cellar-copy"><p class="eyebrow">Поиск продолжается</p><h1>Ищем совпадение</h1><p class="lead">Иногда этикетку нужно сверить чуть внимательнее.</p></div><img class="cellar-scene" src="assets/journey/cellar.png" alt="Пёс изучает винную этикетку в погребе"><div class="cellar-footer">${photoRow()}<div class="cellar-controls"><button class="text-action" data-scene="cancelled">Отменить</button><button class="secondary" data-scene="result">Демо: результат</button></div></div></section>${lightbox()}`)}
  function cancelled(){return shell(`${topbar('home')}<section class="scene cancelled-scene"><div class="cancelled-copy"><p class="eyebrow">Поиск остановлен</p><h1>Снимок остался у вас</h1><p class="lead">Можно повторить поиск с этим фото или снять этикетку заново.</p></div><div class="cancelled-photo"><img src="${sourcePhoto}" alt="Сохранённый демонстрационный снимок бутылки"><button data-enlarge>${icon('zoom-in')} Посмотреть снимок</button></div><div class="cancelled-actions"><button class="primary" data-scene="loading">${icon('refresh')} Повторить поиск</button><button class="secondary" data-scene="camera">Снять новое фото</button><button class="photo-access" data-route="gallery">${icon('photo')} Выбрать другой снимок</button></div></section>${lightbox()}`)}
  function missing(){return shell(`${topbar('home')}<section class="scene missing-scene"><div class="missing-copy"><p class="eyebrow">Совпадения нет</p><h1>Не нашли совпадение</h1><p class="lead">Возможно, этого вина пока нет в каталоге. Попробуйте название или другое фото.</p></div><div class="counter-space"><img class="counter-dog" src="assets/journey/counter.png" alt="Пёс поднимается из-за стойки и предлагает помощь"></div><div class="help-panel"><button class="primary" data-route="search">${icon('search')} Найти по названию</button><button class="secondary" data-scene="camera">Переснять этикетку</button><button class="photo-access" data-route="gallery">${icon('photo')} Выбрать другой снимок</button><button class="missing-original" data-enlarge>Посмотреть исходный снимок</button></div></section>${lightbox()}`)}
  function embedded(){return `<iframe class="embedded" title="${scene==='camera'?'Камера':'Карточка вина'}" src="baseline/index.html?mascotPreview=1&scene=${scene}&mode=off#flows"></iframe>`}
  function notify(){if(parent!==window)parent.postMessage({type:'journey-scene',scene,home:homeVariant},location.origin)}
  function render(){app.innerHTML=scene==='home'?home():scene==='loading'?loading():scene==='cellar'?cellar():scene==='missing'?missing():scene==='cancelled'?cancelled():embedded();document.documentElement.dataset.scene=scene;document.documentElement.dataset.home=homeVariant;notify()}
  function setScene(next){scene=next;const url=new URL(location.href);url.searchParams.set('scene',scene);url.searchParams.set('home',homeVariant);history.replaceState(null,'',url);render()}
  app.addEventListener('click',event=>{
    const target=event.target.closest('[data-scene],[data-route],[data-dismiss],[data-tip-open],[data-enlarge],[data-lightbox]');
    if(!target)return;
    if(target.dataset.dismiss!==undefined){tipOpen=false;render();return}
    if(target.dataset.tipOpen!==undefined){tipOpen=true;render();return}
    if(target.dataset.enlarge!==undefined){const modal=app.querySelector('[data-lightbox]');if(modal)modal.hidden=false;return}
    if(target.dataset.lightbox!==undefined){target.hidden=true;return}
    if(target.dataset.route){location.href=`baseline/index.html?mascotPreview=1&scene=${target.dataset.route}&mode=off#flows`;return}
    setScene(target.dataset.scene);
  });
  render();
})();

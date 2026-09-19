/* Verified source-to-prototype mapping for the standalone V2 report. */
(()=>{
const components=document.querySelector('#components');
const system=document.querySelector('#v2-system');
if(!components||!system)return;

const sourceRoot='assets/v2/sources/';
const icon=name=>`<span class="ui-icon" aria-hidden="true">${(window.ATLAS_ICONS||{})[name]||''}</span>`;
const rows=[
  {
    id:'header',number:'01',title:'Тёплая шапка',screen:'start',button:'Открыть главную',
    image:'mobile-wine-detail-header-390x844.jpg',alt:'Мобильная карточка вина на сайте Своё Вино с капсульной шапкой',crop:'brand-source-header',
    specimen:`<div class="brand-demo-header"><img src="assets/v2/svoe-vino-logo.svg" alt=""><small>Поиск по этикетке</small></div>`,
    observed:'На мобильной карточке логотип, поиск и меню собраны в одну тёплую капсулу. Проверенное правило CSS: #EFDBC64D и blur(10px).',
    adapted:'Та же роль у шапки главной: узнаваемый логотип и входной контекст, затем предметная сцена и сканирование.',
    limit:'Мы не переносим меню разделов каталога: в коротком сканере оно не нужно.'
  },
  {
    id:'search',number:'02',title:'Поиск как отдельный лёгкий слой',screen:'search',button:'Открыть поиск',
    image:'mobile-wine-detail-header-390x844.jpg',alt:'Круглая кнопка поиска в мобильной шапке Своего Вина',crop:'brand-source-search',
    specimen:`<div class="brand-demo-search"><span>Название или винодельня</span><b>${icon('search')}</b></div>`,
    observed:'На снимке видна кнопка поиска в шапке. Отдельно по CSS плавающего мобильного поиска проверены кнопка 48 px, #FFFFFFE6 и blur(5px); состояние dock этим снимком не подтверждается.',
    adapted:'На нашем экране это почти белое поле с отдельной бордовой кнопкой: ввод остаётся контрастным и заметным.',
    limit:'Основное поле поиска не выдаётся за копию плавающего dock Своего Вина: назначение и ширина здесь другие.'
  },
  {
    id:'type',number:'03',title:'Засечковый заголовок, данные без декора',screen:'result',button:'Открыть результат',
    image:'mobile-wine-detail-header-390x844.jpg',alt:'Название вина и бутылка на мобильной карточке Своего Вина',crop:'brand-source-detail',
    specimen:`<div class="brand-demo-detail"><small>Демо-винодельня</small><strong>Каберне<br>Совиньон</strong><span>Красное сухое · 2023</span></div>`,
    observed:'Название вина набрано крупным Playfair; служебные сведения спокойнее и набраны системным шрифтом. Бутылка остаётся главным объектом.',
    adapted:'В карточке результата Playfair создаёт иерархию, а тип, год, регион и источник остаются ясными данными на плотной поверхности.',
    limit:'Рейтинг, магазинные действия и сведения, которых нет в найденной записи, не добавлены.'
  },
  {
    id:'cards',number:'04',title:'Плотная кремовая карточка',screen:'candidates',button:'Открыть варианты',
    image:'desktop-home-story-glass-1440x1000.png',alt:'Главная Своего Вина с крупным стеклянным модулем и плотными карточками внутри',crop:'brand-source-cards',
    specimen:`<div class="brand-demo-candidate"><i></i><span><small>Демо-винодельня</small><strong>Каберне Совиньон</strong><em>Красное сухое · 2023</em></span><b>01</b></div>`,
    observed:'На главной стекло организует крупный модуль, но вложенные материалы читаются как самостоятельные плотные карточки. В каталоге используются кремовые поверхности.',
    adapted:'Кандидаты и факты вина непрозрачны: изображение, название и год не теряют контраст на фоне страницы.',
    limit:'Мы заимствуем разделение слоёв, а не карусель историй и не декоративный фон виноградника.'
  },
  {
    id:'cta',number:'05',title:'Одно плотное главное действие',screen:'start',button:'Открыть сканирование',
    image:'desktop-home-story-glass-1440x1000.png',alt:'Бордовая кнопка Почитать внутри модуля Своего Вина',crop:'brand-source-cta',
    specimen:`<button class="brand-demo-cta" type="button" data-brand-screen="start">Сканировать вино ${icon('scan')}</button>`,
    observed:'На исходном модуле главное действие — непрозрачная бордовая кнопка. Стекло остаётся у контейнера, а не снижает контраст действия.',
    adapted:'Сканирование получает тот же приоритет: сплошной #8F3D42, высота 80 px на главной, ясная камера и рамка этикетки.',
    limit:'Текст и размер адаптированы под съёмку; кнопка «Почитать» не является продуктовым образцом сканера.'
  },
  {
    id:'sheet',number:'06',title:'Sheet отделяется от содержимого',screen:'waiting',button:'Открыть ожидание',
    image:'mobile-age-sheet-390x844.jpg',alt:'Мобильный нижний лист подтверждения возраста на сайте Своё Вино',crop:'brand-source-sheet',
    specimen:`<div class="brand-demo-wait"><span class="spinner"></span><div><strong>Ищем совпадения</strong><small>Фото остаётся на экране</small></div></div>`,
    observed:'Подтверждение возраста — отдельный белый bottom sheet поверх затемнённого и размытого сайта. Это блокирующее действие с явной границей слоя.',
    adapted:'В ожидании мы сохраняем фотографию и помещаем статус с отменой в обычный экран, не закрывая предмет поиска.',
    limit:'Bottom sheet и overlay здесь намеренно не реализованы: поиск не требует блокирующего подтверждения.'
  }
];

const section=document.createElement('section');
section.className='brand-map';
section.setAttribute('aria-labelledby','brand-map-title');
section.innerHTML=`<header class="brand-map-intro"><p class="eyebrow">Проверенная связь источника и макета</p><h2 id="brand-map-title">Своё Вино → наши экраны</h2><p>Слева — реальные снимки публичного сайта. В центре — конкретный элемент системы 2.0. Справа — что перенесено и где проходит граница.</p></header><div class="brand-map-list">${rows.map(row=>`<article class="brand-map-row" id="brand-map-${row.id}"><div class="brand-map-title"><span>${row.number}</span><h3>${row.title}</h3></div><div class="brand-map-visuals"><figure><figcaption>Реальный экран · vino-svoe.ru</figcaption><a class="brand-source ${row.crop}" href="${sourceRoot}${row.image}" target="_blank" rel="noopener" aria-label="Открыть исходный снимок: ${row.alt}"><img src="${sourceRoot}${row.image}" alt="${row.alt}" loading="lazy">${icon('zoom-in')}</a></figure><figure><figcaption>Наша адаптация · система 2.0</figcaption><div class="brand-specimen brand-specimen-${row.id}">${row.specimen}</div></figure></div><div class="brand-map-copy"><dl><div><dt>Наблюдали</dt><dd>${row.observed}</dd></div><div><dt>Перенесли</dt><dd>${row.adapted}</dd></div><div><dt>Граница</dt><dd>${row.limit}</dd></div></dl><button type="button" data-brand-screen="${row.screen}">${row.button} ${icon('arrow-up-right')}</button></div></article>`).join('')}</div><p class="brand-map-footnote">Снимки сделаны 19 сентября 2026 года; CSS перепроверен 20 сентября и используются как визуальные источники. Компоновка наших экранов — проектное решение, не официальный интерфейс «Своего Вина».</p>`;
components.insertBefore(section,system);

})();

const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reddit='https://www.reddit.com/r/wine/comments/1ryejgt/do_you_actually_use_vivinocellartracker_or_not/';
const apps=[
 {id:'vivino',name:'Vivino',role:'Узнать вино по этикетке',core:true,scale:'Android: 10 млн+ установок',focus:'Скан → карточка → личная память',take:'Камера как главный вход. Сразу после фото — название, производитель и год. Подробности ниже, а исправление ошибки рядом с результатом.',praise:'Пользователи ценят быстрый поиск бутылки и историю впечатлений. Похвала простому UX часто относится к ранним версиям.',pain:'В обсуждениях 2026 критикуют торговую перегрузку, платные ограничения и ошибки характеристик. Не копируем весь современный экран.',apply:'Вход, распознавание, краткая карточка',links:[['Отзывы: март 2026',reddit],['Критика: июль 2026','https://www.reddit.com/r/wine/comments/1v1261r/what_happened_to_vivino/']],store:'https://apps.apple.com/us/app/vivino-drink-the-right-wine/id414461255'},
 {id:'wine-searcher',name:'Wine-Searcher',core:true,role:'Проверить точное вино и винтаж',scale:'Android: 1 млн+ установок',focus:'Идентификация → факты → доступность',take:'Держать год, производителя и формат бутылки рядом с названием. Отличать совпадение по бренду от совпадения конкретного вина.',praise:'В отзывах стора ценят поиск цен и продавцов. Для нас полезнее точность идентификации, чем торговый сценарий.',pain:'Цена зависит от региона, объёма и предложения. Не переносим цену без контекста и не делаем покупки частью обязательного пути сканера.',apply:'Выбор среди кандидатов, точный винтаж',links:[['Отзывы в App Store','https://apps.apple.com/us/app/wine-searcher/id599836194?see-all=reviews']],store:'https://apps.apple.com/us/app/wine-searcher/id599836194'},
 {id:'cellartracker',name:'CellarTracker',core:true,role:'Сохранить знание о конкретном вине',scale:'Android appV2: 50 тыс.+',focus:'Вино / винтаж / экземпляр / заметка',take:'Разделить факты каталога и мнение человека. Поля не должны меняться от пользовательской оценки; отсутствующие данные остаются неизвестными.',praise:'Пользователи хвалят содержательные заметки и учёт коллекции. Сила продукта — накопленная база и точная структура данных.',pain:'В обсуждении редизайна 2025 отмечают лишние шаги. Для первого скана не нужна форма коллекционера на десятки полей.',apply:'Структура карточки и происхождение фактов',links:[['Пользователи: март 2026',reddit],['Редизайн: 2025','https://www.reddit.com/r/wine/comments/1lmla61/cellartracker_app_ui_redesign/']],store:'https://apps.apple.com/us/app/cellartracker-1-wine-tracker/id6446102275'},
 {id:'oeni',name:'Oeni',core:true,role:'Понять содержимое своей коллекции',scale:'Android: 500 тыс.+ установок',focus:'Обзор → бутылка → полезное действие',take:'Чётко группировать сведения: что это за вино, что о нём известно и что можно сделать дальше. Оставить один главный следующий шаг.',praise:'В сторах отмечают понятный ввод и наглядную коллекцию. Это референс иерархии и добавления, а не доказанный лидер распознавания российских вин.',pain:'Есть отзывы о пробелах каталога и сортовом составе. Визуально полная карточка не должна скрывать неполноту реальных данных.',apply:'Иерархия карточки, пустые состояния',links:[['Отзывы в App Store','https://apps.apple.com/us/app/oeni-1-wine-cellar-manager/id6445827140?see-all=reviews']],store:'https://apps.apple.com/us/app/oeni-1-wine-cellar-manager/id6445827140'},
 {id:'invintory',name:'InVintory',core:true,role:'Найти нужную бутылку в своём погребе',scale:'Нишевый, преимущественно iOS',focus:'Коллекция → место → бутылка',take:'Заимствовать ясную навигацию между обзором и деталями. У каждой красивой визуализации должна быть задача: например, помочь найти бутылку.',praise:'В Reddit и сторах повторяется похвала современному интерфейсу и удобству поиска физической бутылки.',pain:'3D-погреб решает другую задачу и требует настройки коллекции. Для нашего первого скана это лишняя сложность.',apply:'Визуальная иерархия; коллекция — позднее',links:[['Сравнение приложений: 2024','https://www.reddit.com/r/wine/comments/1bpshj8/best_collection_tracking_apps/'],['Опыт пользователей: 2026',reddit]],store:'https://apps.apple.com/us/app/invintory-wine-cellar-manager/id1434754695'},
 {id:'mixel',name:'Mixel',role:'Выбрать по тому, что уже есть',scale:'Коктейли / контекстный подбор',focus:'Мой бар → доступные рецепты → действие',take:'Контекстные фильтры должны сокращать выбор. Для вина это может быть «к ужину» или «из сохранённых», когда такой сценарий действительно появится.',praise:'Хвалят подбор по ингредиентам и выразительный pixel art. Эстетика узнаваемая, но нравится не всем.',pain:'Не переносим стилизацию ценой читаемости и сложные фильтры в первый экран камеры.',apply:'Полезный следующий шаг; после ядра',links:[['Обсуждение коктейльных приложений','https://www.reddit.com/r/cocktails/comments/1fh12jg/need_help_building_the_best_cocktail_app/']],store:'https://apps.apple.com/us/app/mixel-cocktail-recipes/id1280464759'},
 {id:'highball',name:'Highball',role:'Карточка как самостоятельный объект',scale:'Небольшой iOS-продукт',focus:'Рецепт → красивая карточка → обмен',take:'Краткую карточку можно прочитать одним взглядом. В нашем результате важнее название, год и происхождение данных, чем декоративное богатство.',praise:'В отзывах ценят простоту карточек и обмен рецептами. Это узкий дизайн-референс, не показатель массовой популярности.',pain:'Красота карточки сама по себе не решает распознавание. Экспорт картинки — дополнительная возможность, не требование ЛЦТ.',apply:'Компактный результат и будущий обмен',links:[['Отзывы в App Store','https://apps.apple.com/us/app/highball-by-studio-neat/id973319934?see-all=reviews']],store:'https://apps.apple.com/us/app/highball-by-studio-neat/id973319934'},
 {id:'untappd',name:'Untappd',role:'Быстро записать впечатление',scale:'Android: 5 млн+ установок',focus:'Напиток → check-in → личная история',take:'Сохранение результата — короткое действие. Заметка и оценка могут быть необязательными, чтобы не задерживать человека у полки.',praise:'Даже критики приложения отмечают пользу меню заведений. История помогает вернуться к тому, что понравилось.',pain:'В Reddit жалуются на перегруженную ленту, рекламу и badges. Не превращаем результат скана в социальную сеть.',apply:'История сканов и заметка — после ядра',links:[['Отзывы о UX: 2023','https://www.reddit.com/r/beer/comments/184iqm4/untappd_sucks_as_an_app/']],store:'https://apps.apple.com/us/app/untappd-find-drinks-you-love/id449141888'},
 {id:'yuka',name:'Yuka',role:'Понятный ответ прямо у полки',scale:'Смежный сценарий сканирования',focus:'Скан → краткий ответ → объяснение',take:'На первом экране дать понятный результат, затем раскрывать основания. Для вина объясняем идентификацию и источник, а не придумываем единый балл качества.',praise:'В предыдущем исследовании отмечена востребованность быстрого scan → breakdown. Здесь переносим продуктовую механику, а не оценку здоровья.',pain:'Нельзя приравнивать субъективный вкус вина к универсальному баллу. Не переносим семантику «полезного алкоголя».',apply:'Первый экран результата',links:[['Google Play','https://play.google.com/store/apps/details?id=io.yuka.android']],store:'https://play.google.com/store/apps/details?id=io.yuka.android'},
 {id:'letterboxd',name:'Letterboxd',role:'Личный дневник впечатлений',scale:'Смежный формат: коллекции и списки',focus:'Объект → хочу / пробовал → заметка',take:'Разделить «хочу попробовать» и «уже пробовал». Мнение пользователя не заменяет объективные сведения о вине.',praise:'Полезен как продуктовая аналогия дневника и списков. Это наша аналогия, не вывод о превосходстве его дизайна.',pain:'Не начинаем с ленты, подписок и длинной анкеты. Сначала нужно завершить поиск вина.',apply:'Личная память — после ядра',links:[['Google Play','https://play.google.com/store/apps/details?id=com.letterboxd.letterboxd']],store:'https://play.google.com/store/apps/details?id=com.letterboxd.letterboxd'}
];
const manifest=window.ATLAS_ASSETS||{apps:[]};
let currentApp=apps[0],galleryPage=0,lightIndex=0;
function assetFor(id){const normalize=s=>s.toLowerCase().replace(/[^a-z0-9]/g,'');return manifest.apps.find(a=>normalize(a.id)===normalize(id)||normalize(a.name)===normalize(id));}
function screenshots(){return assetFor(currentApp.id)?.screenshots||[];}
function imgPath(s){return 'assets/'+s.file;}
function navTo(id){document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==id);document.querySelectorAll('[data-view]').forEach(b=>{let on=b.dataset.view===id;b.classList.toggle('active',on);b.setAttribute('aria-pressed',on)});history.replaceState(null,'','#'+id);}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>navTo(b.dataset.view)));
function renderApp(){
 document.querySelectorAll('[data-app]').forEach(b=>{let on=b.dataset.app===currentApp.id;b.classList.toggle('active',on);b.setAttribute('aria-pressed',on)});
 const a=currentApp, shots=screenshots(), pageSize=window.innerWidth<=440?2:3, start=galleryPage*pageSize, shown=shots.slice(start,start+pageSize);
 $('#app-detail').innerHTML=`<div class="app-title-row"><div><p class="eyebrow">${esc(a.role)}</p><h2>${esc(a.name)}</h2><p class="app-subtitle">${esc(a.focus)}</p></div><a class="source-link" target="_blank" rel="noopener" href="${esc(assetFor(a.id)?.sourceUrl||a.store)}">Страница приложения ↗</a></div><div class="app-meta"><span class="pill ${a.core?'core':''}">${a.core?'Основной референс':'Смежный референс'}</span><span class="pill">${esc(a.scale)}</span><span class="pill">${esc(a.apply)}</span></div><div class="gallery">${shown.map((s,i)=>`<figure class="screen-card"><button class="screen-open" data-shot="${start+i}" aria-label="Увеличить: ${esc(s.title)}"><img src="${esc(imgPath(s))}" alt="${esc(s.description||s.title)}" loading="${i?'lazy':'eager'}"><span class="zoom-hint">Увеличить ⤢</span></button><figcaption>${String(start+i+1).padStart(2,'0')} / ${esc(s.title)}<span>${esc(s.description||'Официальный промоскриншот')}</span></figcaption></figure>`).join('')}</div><div class="gallery-controls"><p>${shots.length?'Официальные промоскриншоты · '+(start+1)+'–'+Math.min(start+pageSize,shots.length)+' из '+shots.length:'Изображения для этого приложения не получены'}<br>Нажмите на экран, чтобы рассмотреть его крупнее.</p><div><button id="gallery-prev" ${galleryPage===0?'disabled':''}>← Назад</button><button id="gallery-next" ${start+pageSize>=shots.length?'disabled':''}>Далее →</button></div></div><div class="insights"><div class="take"><h3>Что берём для ЛЦТ</h3><p>${esc(a.take)}</p></div><div><h3>Что ценят пользователи</h3><p>${esc(a.praise)}</p></div><div><h3>Ограничение / антипример</h3><p>${esc(a.pain)}</p></div></div><p class="evidence">Основания: ${a.links.map(([t,u])=>`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)} ↗</a>`).join('')}<br>Публичный масштаб — из исследования 18.09.2026; установки не равны активной аудитории. Комментарии «что берём» — наша интерпретация.</p>`;
 $('#gallery-prev').onclick=()=>{galleryPage--;renderApp()};$('#gallery-next').onclick=()=>{galleryPage++;renderApp()};document.querySelectorAll('[data-shot]').forEach(b=>b.onclick=()=>openShot(Number(b.dataset.shot)));
}
apps.filter(a=>assetFor(a.id)).forEach((a,i)=>{const b=document.createElement('button');b.dataset.app=a.id;b.setAttribute('aria-pressed',i===0);b.innerHTML=`${esc(a.name)}<small>${a.core?String(i+1).padStart(2,'0'):'↗'}</small>`;b.onclick=()=>{currentApp=a;galleryPage=0;renderApp()};$(a.core?'#core-apps':'#adjacent-apps').append(b)});
function showShot(){const s=screenshots()[lightIndex];$('#large-image').src=imgPath(s);$('#large-image').alt=s.description||s.title;$('#image-title').textContent=currentApp.name+' / '+s.title;$('#image-source').href=s.url||s.originalUrl||currentApp.store;$('#image-prev').disabled=lightIndex===0;$('#image-next').disabled=lightIndex===screenshots().length-1}
function openShot(i){lightIndex=i;showShot();$('#image-dialog').showModal()}
$('#close-image').onclick=()=>$('#image-dialog').close();$('#image-prev').onclick=()=>{lightIndex--;showShot()};$('#image-next').onclick=()=>{lightIndex++;showShot()};$('#image-dialog').addEventListener('click',e=>{if(e.target===$('#image-dialog'))$('#image-dialog').close()});$('#image-dialog').addEventListener('keydown',e=>{if(e.key==='ArrowLeft'&&lightIndex>0){lightIndex--;showShot()}if(e.key==='ArrowRight'&&lightIndex<screenshots().length-1){lightIndex++;showShot()}});

const scenarios=[
 {
  "id": "happy",
  "label": "Точное совпадение",
  "title": "Узнать вино у полки",
  "context": "Уверенное совпадение сразу открывает карточку. Обязательного подтверждения фото, вина или года нет.",
  "steps": [
   [
    "start",
    "Открыть сканер"
   ],
   [
    "camera",
    "Снять этикетку"
   ],
   [
    "loading",
    "Дождаться поиска"
   ],
   [
    "result",
    "Получить карточку"
   ]
  ],
  "check": "После затвора не нужен ещё один клик, чтобы увидеть вино. Исправление доступно из карточки.",
  "level": "Подтверждено Q&A",
  "ref": "Q&A 07:59–09:47, 47:58–48:22. Shazam: одно основное действие."
 },
 {
  "id": "vintage",
  "label": "Неоднозначный ответ",
  "title": "Несколько похожих этикеток",
  "context": "Сервис не уверен в единственном результате. Показываем ближайшие варианты вместо сообщения «ничего не найдено».",
  "steps": [
   [
    "camera",
    "Снять этикетку"
   ],
   [
    "loading",
    "Поиск"
   ],
   [
    "candidates",
    "Сравнить варианты"
   ],
   [
    "result",
    "Открыть выбранное вино"
   ]
  ],
  "check": "Можно различить названия и винодельни, выбрать кандидат или «Ни одно». Проценты не выдуманы.",
  "level": "Подтверждено Q&A",
  "ref": "Q&A 48:30–49:25. Pl@ntNet / Merlin: сравнение кандидатов."
 },
 {
  "id": "shelf",
  "label": "Бутылка на полке",
  "title": "Соседние бутылки не мешают сценарию",
  "context": "В кадре могут быть части соседних бутылок. Цель поиска — центральная бутылка целиком.",
  "steps": [
   [
    "camera",
    "Поместить бутылку по центру"
   ],
   [
    "loading",
    "Найти совпадение"
   ],
   [
    "result",
    "Открыть карточку"
   ]
  ],
  "check": "Подсказка не требует пустого фона. На макете видны соседние бутылки.",
  "level": "Подтверждено Q&A",
  "ref": "Q&A 55:07–55:49. Рамка — наша UX-адаптация."
 },
 {
  "id": "slow",
  "label": "Долгий поиск",
  "title": "Ожидание не превращается в тупик",
  "context": "Сложный снимок обрабатывается дольше. Показываем сохранённое фото, статус и отмену.",
  "steps": [
   [
    "camera",
    "Снять фото"
   ],
   [
    "loading",
    "Поиск"
   ],
   [
    "waiting",
    "Продолжительное ожидание"
   ],
   [
    "result",
    "Получить карточку"
   ]
  ],
  "check": "Отмена останавливает демопереход и сохраняет снимок. Повтор не требует съёмки.",
  "level": "UX-рекомендация",
  "ref": "Q&A 26:41–29:55: точность важнее скорости. Конкретный UX ожидания — наше решение."
 },
 {
  "id": "missing",
  "label": "Нет совпадения",
  "title": "Не нашли подходящее вино",
  "context": "Не удалось найти подходящие варианты. Причину не выдаём за установленный факт.",
  "steps": [
   [
    "camera",
    "Снять фото"
   ],
   [
    "missing",
    "Увидеть отсутствие совпадения"
   ],
   [
    "search",
    "Попробовать название"
   ]
  ],
  "check": "Нет выдуманной карточки. Есть ручной поиск и новый снимок.",
  "level": "UX-рекомендация",
  "ref": "Q&A: в закрытом тесте все вина есть в каталоге. Этот сценарий нужен для реального использования."
 },
 {
  "id": "badphoto",
  "label": "Блик / плохое фото",
  "title": "Помочь переснять этикетку",
  "context": "Название закрыто бликом. Показываем конкретную подсказку, что изменить.",
  "steps": [
   [
    "camera",
    "Снять фото"
   ],
   [
    "badphoto",
    "Получить совет"
   ],
   [
    "camera",
    "Переснять"
   ]
  ],
  "check": "Пользователь понимает, как изменить свет или ракурс. Детектор качества не заявлен готовым.",
  "level": "UX-рекомендация",
  "ref": "Реальные условия съёмки из Q&A. Автоматическое выявление блика — гипотеза реализации."
 },
 {
  "id": "permission",
  "label": "Камера запрещена",
  "title": "Продолжить через галерею",
  "context": "Отказ в доступе к камере не закрывает путь к карточке.",
  "steps": [
   [
    "start",
    "Открыть сканер"
   ],
   [
    "permission",
    "Выбрать альтернативу"
   ],
   [
    "loading",
    "Отправить фото"
   ],
   [
    "result",
    "Открыть карточку"
   ]
  ],
  "check": "Выбор фото и ручной поиск доступны без повторного запроса разрешения.",
  "level": "UX-рекомендация",
  "ref": "Наше UX-решение для мобильного веба; системный диалог не имитируем."
 },
 {
  "id": "network",
  "label": "Сеть недоступна",
  "title": "Повторить с тем же снимком",
  "context": "Связь пропала после съёмки. Исходное фото остаётся в текущем поиске.",
  "steps": [
   [
    "camera",
    "Снять фото"
   ],
   [
    "offline",
    "Сбой сети"
   ],
   [
    "loading",
    "Повторить запрос"
   ],
   [
    "result",
    "Получить результат"
   ]
  ],
  "check": "Повтор запроса не требует снова фотографировать. Нет обещания офлайн-распознавания.",
  "level": "UX-рекомендация",
  "ref": "Shazam: сохранение незавершённой попытки. Здесь адаптировано как ручной повтор в текущей сессии."
 },
 {
  "id": "wrong",
  "label": "Нашлось не то",
  "title": "Исправить ошибку модели",
  "context": "Пользователь заметил неверное название или винодельню. Исправление рядом с результатом.",
  "steps": [
   [
    "result",
    "Увидеть карточку"
   ],
   [
    "candidates",
    "Нажать «Не это вино?»"
   ],
   [
    "search",
    "Найти вручную"
   ]
  ],
  "check": "Есть кандидаты, исходное фото и ручной поиск. Ошибка не запирает пользователя в карточке.",
  "level": "UX-рекомендация",
  "ref": "Жалобы на ложные совпадения у сканеров: качественный мотив из отзывов, не статистика."
 },
 {
  "id": "back",
  "label": "Сверить фото",
  "title": "Вернуться к исходному снимку",
  "context": "Фото можно сверить с карточкой по желанию, не начиная поиск заново.",
  "steps": [
   [
    "result",
    "Открыть карточку"
   ],
   [
    "preview",
    "Сверить снимок"
   ],
   [
    "result",
    "Вернуться к карточке"
   ]
  ],
  "check": "Возврат сохраняет выбранное вино. Фото не становится обязательным экраном до результата.",
  "level": "UX-рекомендация",
  "ref": "Наше решение: проверяемость ответа без лишнего шага в основном пути."
 }
];
let scenario=scenarios[0],screen='start',selectedYear='2023',loadTimer=null,photoReturn='result';
const label=()=>`<div class="sample-label"><span>ДЕМОНСТРАЦИОННАЯ ЭТИКЕТКА</span><strong>Демо-вино</strong><small>Каберне · 2023</small></div>`;
const photo=()=>`<div class="photo-demo">${label()}</div>`;
const action=(t,next,kind='')=>`<button class="mobile-action ${kind}" data-go="${next}">${t}</button>`;
const notes={
 start:['Один понятный вход',['Сканер сразу доступен: обязательная регистрация не подтверждена брифом.','Галерея и ручной поиск остаются видимыми альтернативами.','Лента и подборки не отодвигают основное действие.']],
 camera:['Подсказка в момент съёмки',['Рамка объясняет, что снимать: одну этикетку целиком.','Короткая подсказка про свет и резкость вместо длинного обучения.','Это макет камеры. Реальные системные разрешения ещё нужно спроектировать под выбранную платформу.']],
 preview:['Проверка до отправки',['Показываем исходный снимок: пользователь видит, что именно ищет сервис.','Можно переснять без сброса всего сценария.','Подсказка о бликах не обещает автоматическую диагностику качества снимка.']],
 loading:['Понятное ожидание',['Сообщаем, какое действие выполняется.','Не показываем искусственные проценты распознавания.','Можно отменить и сохранить фото. Демо-переход занимает долю секунды, это не замер модели.']],
 candidates:['Не прячем неоднозначность',['Различия вынесены в строки кандидатов: в макете это год.','Нет выдуманного «совпадение 97%». Реальную похожесть модели нельзя без калибровки назвать вероятностью.','«Ни одно» — полноценный выход, а не тупик.']],
 result:['Сначала идентичность вина',['На первом плане название, производитель и винтаж.','Кнопка исправления видна без поиска в меню.','Переход ведёт к карточке из каталога; в макете данные вымышлены.']],
 catalog:['Факты с источником',['Подробности происходят из существующей записи каталога.','Если поле неизвестно, пишем это прямо.','Оценки, гастропары и AI-текст не подменяют исходные сведения.']],
 missing:['Не нашли — не выдумываем',['Формулировка не утверждает, что вина точно нет в базе.','Два способа продолжить: название или другое фото.','Не выдаём случайную похожую бутылку за результат.']],
 badphoto:['Конкретный способ исправить',['Совет относится к снимку: развернуть этикетку, убрать блик.','Новый кадр и галерея доступны отсюда.','Автоматическая проверка качества — гипотеза реализации; до неё полезна ручная проверка фото.']],
 permission:['Отказ не превращается в тупик',['Галерея и поиск доступны без повторного запроса камеры.','Инструкция по настройкам зависит от платформы.','Не подделываем системное разрешение: экран показывает состояние после отказа.']],
 offline:['Сохраняем труд пользователя',['Снимок остаётся на экране и в текущем сценарии.','Повтор запроса — одно действие.','Межсессионное или фоновое хранение не обещаем: это отдельное решение о данных.']],
 search:['Ручной вход на равных',['Название и производитель помогают уточнить объект.','Результаты ведут к тем же карточкам, что и поиск по фото.','В макете поиск демонстрационный: произвольный каталог не подключён.']],
 settings:['Понятная следующая попытка',['Настройки зависят от iOS, Android или браузера.','После разрешения пользователь возвращается в тот же сценарий.','Демо-кнопка ниже только меняет экран макета.']]};
function renderScenario(){
 document.querySelectorAll('[data-scenario]').forEach(b=>{let on=b.dataset.scenario===scenario.id;b.classList.toggle('active',on);b.setAttribute('aria-pressed',on)});
 $('#flow-explanation').innerHTML=`<p class="eyebrow">${esc(scenario.level)}</p><h3>${esc(scenario.title)}</h3><p>${esc(scenario.context)}</p><ol class="step-list">${scenario.steps.map(([id,t])=>`<li class="${screen===id?'current':''}">${esc(t)}</li>`).join('')}</ol><div class="criterion"><strong>Как проверим</strong>${esc(scenario.check)}</div><p class="evidence">${esc(scenario.ref)}</p>`;
}
function setScreen(next){clearTimeout(loadTimer);if(next==='preview')photoReturn=['result','catalog','candidates','waiting','missing','loading'].includes(screen)?screen:'cancelled';screen=next;renderPhone();renderScenario()}
function beginScan(retry=false){selectedYear='2023';detailTab='overview';setScreen('loading');loadTimer=setTimeout(()=>setScreen(retry?'result':scenario.id==='slow'?'waiting':scenario.id==='vintage'?'candidates':scenario.id==='missing'?'missing':scenario.id==='badphoto'?'badphoto':scenario.id==='network'?'offline':'result'),1200)}
function renderPhone(){}
scenarios.forEach((s,i)=>{const b=document.createElement('button');b.dataset.scenario=s.id;b.textContent=s.label;b.setAttribute('aria-pressed',i===0);b.onclick=()=>{scenario=s;selectedYear='2023';detailTab='overview';searched=false;setScreen(s.steps[0][0])};$('#scenario-picker').append(b)});
$('#restart').onclick=()=>{selectedYear='2023';detailTab='overview';searched=false;setScreen(scenario.steps[0][0])};

$('#decision-content').innerHTML=`<div class="map-grid"><article class="decision-block"><p class="eyebrow">Сначала</p><h3>Работающий сканер</h3><ol><li><strong>Фото → карточка каталога</strong><span>Q&A: уверенное совпадение сразу открывает карточку. Фото, название, винодельня.</span></li><li><strong>Неоднозначность и исправление</strong><span>Ближайшие кандидаты при неуверенности, исправление доступно из карточки.</span></li><li><strong>Исправление и ручной поиск</strong><span>Наша UX-рекомендация: не создавать тупик при ошибке модели.</span></li><li><strong>Факты и источник</strong><span>Описание из каталога; неизвестное остаётся неизвестным.</span></li><li><strong>Восстановление после сбоев</strong><span>Галерея, разрешения, повтор запроса с тем же снимком.</span></li></ol></article><article class="decision-block optional"><p class="eyebrow">После устойчивого ядра</p><h3>Причина вернуться</h3><ol><li><strong>История сканов</strong><span>Найти бутылку, которую видел вчера.</span></li><li><strong>«Хочу попробовать»</strong><span>Сохранить без обязательной оценки.</span></li><li><strong>Личная заметка</strong><span>Впечатление отдельно от фактов.</span></li><li><strong>Сравнение двух вин</strong><span>Только по доступным полям, с видимым годом.</span></li><li><strong>Экспорт личных данных</strong><span>Если начинаем хранить историю — не запирать её внутри продукта.</span></li></ol></article><article class="decision-block later"><p class="eyebrow">Отдельные гипотезы</p><h3>Пока не усложняем</h3><ol><li><strong>3D-погреб</strong><span>Сильный InVintory-сценарий, но другая задача.</span></li><li><strong>Социальная лента</strong><span>Не нужна, чтобы распознать этикетку.</span></li><li><strong>Корзина и покупка</strong><span>Q&A: платформа информационная, покупка происходит в магазине.</span></li><li><strong>AI-сомелье</strong><span>Не должен подменять данные каталога.</span></li><li><strong>Рейтинги и гастропары</strong><span>Уже есть на платформе. Не дублируем их как отдельную бонусную механику.</span></li></ol></article></div><div class="pattern-list"><h3>Пять полезных паттернов</h3>${[
 ['Vivino','Камера → быстрый результат','Поставить поиск по фотографии в центр первого экрана.','Перегруженный торговлей результат и уверенно неверные факты.'],
 ['Wine-Searcher','Точный объект поиска','Показывать год и производителя рядом с названием.','Подмена конкретного вина похожим брендом.'],
 ['CellarTracker','Структура и происхождение','Разделить вино, винтаж, экземпляр и личную заметку.','Сложная анкета перед первым полезным результатом.'],
 ['InVintory / Oeni','Обзор → детали','Краткая карточка, ясная иерархия, последовательное раскрытие.','Дорогая визуальная механика, не помогающая распознаванию.'],
 ['Highball / Yuka','Один экран — один ответ','Понятное резюме и доступные основания.','Универсальный «балл качества вина» без смысла и доказательств.']
 ].map(([app,name,take,avoid])=>`<div class="pattern-row"><strong>${app}</strong><p><small>${name}</small>${take}</p><p><small>Не переносим</small>${avoid}</p></div>`).join('')}</div>`;
$('#source-list').innerHTML=apps.map(a=>`<div class="source-row"><strong>${esc(a.name)}</strong><div><a href="${esc(assetFor(a.id)?.sourceUrl||a.store)}" target="_blank" rel="noopener">${assetFor(a.id)?"Официальные экраны":"Страница продукта"} ↗</a>${a.links.map(([t,u])=>`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)} ↗</a>`).join('')}</div></div>`).join('')+`<div class="source-row"><strong>Наш сценарий</strong><div><a target="_blank" rel="noopener" href="https://www.vivino.com/de/wine-news/how-the-vivino-label-scanner-works">Vivino: скан и ручной fallback ↗</a><a target="_blank" rel="noopener" href="https://www.reddit.com/r/wine/comments/1qhqw0l/best_wine_tracking_app_for_small_winery_wines/">Редкие вина и неверные винтажи: январь 2026 ↗</a></div></div>`;
renderApp();renderScenario();renderPhone();if(['references','components','flows','decisions','sources'].includes(location.hash.slice(1)))navTo(location.hash.slice(1));
let smallLayout=window.innerWidth<=440;window.addEventListener('resize',()=>{const small=window.innerWidth<=440;if(small!==smallLayout){smallLayout=small;galleryPage=0;renderApp()}});

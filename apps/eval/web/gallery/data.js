const rootPath = new URL('../', document.currentScript.src).pathname;
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let token = sessionStorage.getItem('lct_eval_token') || '';
let slugPage = 1, imagePage = 1, selectedSlug = '', detailSequence = 0;
const thumbURLs = new Map();
let detailURLs = [];

async function api(path) {
  const response = await fetch(rootPath + path.replace(/^\//, ''), {headers:{Authorization:'Bearer ' + token}});
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response;
}

function filters() {
  const params = new URLSearchParams();
  for (const id of ['scenario','role','origin','model','qc']) if ($('#' + id).value) params.set(id, $('#' + id).value);
  if ($('#search').value.trim()) params.set('q', $('#search').value.trim());
  return params;
}

function setNotice(message, error=false) {
  $('#notice').textContent = message;
  $('#notice').className = error ? 'error' : '';
}

function fillFacet(id, values) {
  const select = $('#' + id), current = select.value;
  const roleLabels = {identity_reference:'Исходная бутылка',scene_reference:'Референс сцены',output:'AI-результат',augmentation:'Аугментация'};
  select.innerHTML = '<option value="">Все</option>' + values.map(value => `<option value="${esc(value)}">${esc(id === 'role' ? roleLabels[value] || value : value)}</option>`).join('');
  select.value = current;
}

function pager(selector, page, perPage, total, change) {
  const pages = Math.max(1, Math.ceil(total / perPage));
  const node = $(selector);
  node.innerHTML = `<button data-prev ${page <= 1 ? 'disabled' : ''}>Назад</button><span>${page} / ${pages}</span><button data-next ${page >= pages ? 'disabled' : ''}>Вперёд</button>`;
  node.querySelector('[data-prev]').onclick = () => change(page - 1);
  node.querySelector('[data-next]').onclick = () => change(page + 1);
}

async function loadSlugs(page=1) {
  slugPage = page;
  const params = filters();
  params.set('page', page);
  params.set('per_page', 24);
  const data = await (await api('/api/data/slugs?' + params)).json();
  $('#counts').innerHTML = `<div class="stat"><strong>${data.total_slugs}</strong>slug</div><div class="stat"><strong>${data.total_images}</strong>изображений в подборке</div>`;
  $('#slugs').innerHTML = data.items.length
    ? `<div class="slug-grid">${data.items.map(item => `<button class="slug-card" data-slug="${esc(item.slug)}"><strong>${esc(item.slug)}</strong><span class="badge">${item.total} изображений</span><span class="badge">${item.roles.output || 0} результатов</span><span class="badge">${item.qc.accepted || 0} QC принято</span><br><small>Стоимость: $${Number(item.cost_usd).toFixed(3)}</small></button>`).join('')}</div>`
    : '<p class="muted">Для выбранных фильтров изображений нет.</p>';
  document.querySelectorAll('[data-slug]').forEach(node => node.onclick = () => openSlug(node.dataset.slug));
  pager('#slug-pager', page, data.per_page, data.total_slugs, next => loadSlugs(next).catch(showError));
  setNotice('Каталог загружен. Выберите slug, чтобы увидеть связанные изображения.');
}

function showError(error) { setNotice(error.message || String(error), true); }

function showThumb(image, element) {
  if (!image.thumbnail_path) return;
  if (thumbURLs.has(image.image_id)) { element.src = thumbURLs.get(image.image_id); return; }
  api(`/api/data/images/${encodeURIComponent(image.image_id)}/thumbnail`).then(r => r.blob()).then(blob => {
    const url = URL.createObjectURL(blob);
    thumbURLs.set(image.image_id, url);
    if (element.isConnected) element.src = url;
  }).catch(() => { element.alt = 'Миниатюра недоступна'; });
}

const observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
  for (const entry of entries) if (entry.isIntersecting) {
    observer.unobserve(entry.target);
    const image = JSON.parse(entry.target.dataset.visionImage);
    showThumb(image, entry.target);
  }
}, {rootMargin:'300px'}) : null;

function imageCard(image) {
  const thumb = image.thumbnail_path
    ? `<img data-vision-image="${esc(JSON.stringify({image_id:image.image_id,thumbnail_path:image.thumbnail_path}))}" loading="lazy" alt="Миниатюра ${esc(image.image_id)}">`
    : '<div class="thumb-missing">Миниатюра ожидается</div>';
  return `<article class="card image-card" data-image-id="${esc(image.image_id)}" role="button" tabindex="0" aria-label="Открыть изображение ${esc(image.image_id)}">${thumb}<div class="card-body"><strong>${esc(image.image_id)}</strong><br><span class="badge">${esc(image.role)}</span><span class="badge ${esc(image.origin)}">${esc(image.origin)}</span><span class="badge ${image.qc?.status === 'pending' ? 'pending' : ''}">QC: ${esc(image.qc?.status || '—')}</span><br><small>${esc(image.model || image.provider || 'Источник')}</small></div></article>`;
}

async function openSlug(slug, page=1) {
  selectedSlug = slug;
  imagePage = page;
  $('#images-panel').hidden = false;
  $('#slugs').hidden = true;
  $('#slug-pager').hidden = true;
  $('#counts').hidden = true;
  $('#detail').hidden = true;
  const params = filters();
  params.delete('q');
  params.set('slug', slug);
  params.set('page', page);
  params.set('per_page', 24);
  const data = await (await api('/api/data/images?' + params)).json();
  $('#slug-title').textContent = slug;
  const accepted = data.items.filter(v => v.qc?.status === 'accepted').length;
  const cost = data.items.reduce((total, v) => total + Number(v.cost_usd || 0), 0);
  $('#image-counts').innerHTML = `<div class="stat"><strong>${data.total_images}</strong>изображений</div><div class="stat"><strong>${accepted}</strong>QC принято на странице</div><div class="stat"><strong>$${cost.toFixed(3)}</strong>стоимость на странице</div>`;
  $('#images').innerHTML = data.items.map(imageCard).join('') || '<p class="muted">Для выбранных фильтров изображений нет.</p>';
  document.querySelectorAll('[data-vision-image]').forEach(node => observer ? observer.observe(node) : showThumb(JSON.parse(node.dataset.visionImage), node));
  document.querySelectorAll('[data-image-id]').forEach(node => {
    const open = () => showDetail(node.dataset.imageId).catch(showError);
    node.onclick = open;
    node.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    };
  });
  pager('#image-pager', page, data.per_page, data.total_images, next => openSlug(slug, next).catch(showError));
  $('#images-panel').scrollIntoView({behavior:'auto'});
}

function closeSlug() {
  detailSequence++;
  for (const url of detailURLs) URL.revokeObjectURL(url);
  detailURLs = [];
  $('#images-panel').hidden = true;
  $('#detail').hidden = true;
  $('#slugs').hidden = false;
  $('#slug-pager').hidden = false;
  $('#counts').hidden = false;
  selectedSlug = '';
}

function metadata(image) {
  const source = image.source || {};
  const fields = [
    ['Роль', image.role], ['Происхождение', image.origin], ['Сценарии', (image.scenario_ids || []).join(', ')],
    ['Модель', image.model], ['Провайдер', image.provider], ['QC', image.qc?.status], ['Причина QC', image.qc?.reason],
    ['Набор', image.split], ['Группа источника', image.source_group], ['Родители', (image.parent_ids || []).join(', ')],
    ['Стоимость', image.cost_usd == null ? '' : '$' + Number(image.cost_usd).toFixed(4)],
    ['Время', image.latency_ms == null ? '' : image.latency_ms + ' мс'], ['SHA-256', image.sha256],
    ['Источник', source.title], ['Лицензия', source.license], ['Атрибуция', source.attribution],
    ['ID источника', source.source_id], ['ID продукта', source.product_id], ['ID медиа', source.media_id]
  ];
  const output = fields.filter(([,value]) => value !== '' && value != null).map(([label,value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('');
  return `<dl class="metadata">${output}</dl>${source.url ? `<p><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">Открыть источник ↗</a></p>` : ''}`;
}

function conditionBlock(title, conditions) {
  if (!conditions || Object.keys(conditions).length === 0) return '';
  return `<div><h3>${esc(title)}</h3><pre>${esc(JSON.stringify(conditions, null, 2))}</pre></div>`;
}

async function showDetail(id) {
  const sequence = ++detailSequence;
  for (const url of detailURLs) URL.revokeObjectURL(url);
  detailURLs = [];
  const image = await (await api(`/api/data/images/${encodeURIComponent(id)}`)).json();
  const refs = await Promise.all([image.identity_reference_id, image.scene_reference_id].filter(Boolean).map(async ref => {
    try { return await (await api(`/api/data/images/${encodeURIComponent(ref)}`)).json(); }
    catch { return null; }
  }));
  if (sequence !== detailSequence) return;
  const pictures = [['Результат', image], ['Исходная бутылка', refs.find(v => v?.image_id === image.identity_reference_id)], ['Референс сцены', refs.find(v => v?.image_id === image.scene_reference_id)]].filter(([,v]) => v);
  $('#detail').hidden = false;
  $('#detail').innerHTML = `<div class="detail-head"><h2>${esc(image.image_id)}</h2><button id="close-detail">Закрыть</button></div><p class="muted">${esc(image.slug || 'Общий референс сцены')}</p><div class="detail-images">${pictures.map(([label,v]) => `<figure><img data-original="${esc(v.image_id)}" alt="${esc(label)}"><figcaption>${esc(label)} · ${esc(v.image_id)}</figcaption></figure>`).join('')}</div>${metadata(image)}<div class="condition-grid">${conditionBlock('Запрошенные условия',image.requested_conditions)}${conditionBlock('Наблюдаемые условия',image.observed_conditions)}</div>`;
  $('#close-detail').onclick = () => { detailSequence++; $('#detail').hidden = true; for (const url of detailURLs) URL.revokeObjectURL(url); detailURLs = []; };
  document.querySelectorAll('[data-original]').forEach(async node => {
    try {
      const blob = await (await api(`/api/data/images/${encodeURIComponent(node.dataset.original)}/image`)).blob();
      if (sequence !== detailSequence) return;
      const url = URL.createObjectURL(blob);
      detailURLs.push(url);
      node.src = url;
    } catch { if (sequence === detailSequence) node.alt = 'Оригинал недоступен'; }
  });
  $('#detail').scrollIntoView({behavior:'auto'});
}

async function load() {
  try {
    await api('/api/auth');
    const facets = await (await api('/api/data/facets')).json();
    fillFacet('scenario', facets.scenarios || []);
    fillFacet('role', facets.roles || []);
    fillFacet('origin', facets.origins || []);
    fillFacet('model', facets.models || []);
    fillFacet('qc', facets.qc || []);
    $('#login').hidden = true;
    $('#workspace').hidden = false;
    $('#logout').hidden = false;
    await loadSlugs();
  } catch (error) {
    $('#login-error').textContent = error.message;
    if (String(error.message).startsWith('401')) { sessionStorage.removeItem('lct_eval_token'); token = ''; }
  }
}

$('#login-form').onsubmit = event => { event.preventDefault(); token = $('#token').value.trim(); sessionStorage.setItem('lct_eval_token', token); load(); };
$('#logout').onclick = () => { sessionStorage.removeItem('lct_eval_token'); location.reload(); };
$('#apply').onclick = () => { closeSlug(); loadSlugs(1).catch(showError); };
$('#search').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); $('#apply').click(); } };
$('#close-slug').onclick = closeSlug;
if (token) load();

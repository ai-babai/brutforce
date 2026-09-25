'use strict';

const byId = id => document.getElementById(id);
const statusMeta = {
  'Подтверждено': {label: 'Официально · подтверждено', kind: 'official'},
  'Устное пояснение': {label: 'Устное пояснение', kind: 'oral'},
  'Не определено': {label: 'Не выяснено', kind: 'unresolved'},
  'Расхождение': {label: 'Расхождение', kind: 'discrepancy'},
  'Наше решение': {label: 'Наш вывод', kind: 'internal'},
  official: {label: 'Официально', kind: 'official'},
  inference: {label: 'Наш вывод', kind: 'internal'},
  unresolved: {label: 'Не выяснено', kind: 'unresolved'}
};
let requirements = [];

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}

function sourceList(sources) {
  if (!Array.isArray(sources) || !sources.length) return null;
  const wrap = element('div', 'requirement-sources');
  wrap.append(element('strong', '', 'Источники: '));
  for (const source of sources) {
    if (!source || typeof source !== 'object') continue;
    const label = String(source.label || source.url || 'Источник');
    const url = String(source.url || '');
    let href;
    try {
      const parsed = new URL(url, location.href);
      if (url && (parsed.protocol === 'https:' || parsed.protocol === 'http:')) href = parsed.href;
    } catch (_) { /* Show malformed links as text. */ }
    if (!href) {
      wrap.append(element('span', '', label));
      continue;
    }
    const link = element('a', '', label);
    link.href = href;
    if (new URL(href).origin !== location.origin) {
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }
    wrap.append(link);
  }
  return wrap.childElementCount > 1 ? wrap : null;
}

function statusBadge(status) {
  const key = String(status || '');
  const meta = Object.hasOwn(statusMeta, key) ? statusMeta[key] : {label: key || 'Не указан', kind: 'other'};
  return element('span', `badge requirement-status status-${meta.kind}`, meta.label);
}

function validAnchor(id, index) {
  return /^[A-Za-z][A-Za-z0-9_-]*$/.test(String(id)) ? String(id) : `requirement-${index + 1}`;
}

function renderRequirement(item, index) {
  const article = element('article', 'requirement');
  article.id = validAnchor(item.id, index);
  const head = element('div', 'requirement-head');
  const titleBlock = element('div');
  const idLink = element('a', 'requirement-id', item.id || article.id);
  idLink.href = `#${article.id}`;
  titleBlock.append(idLink, element('h3', '', item.title || 'Без названия'));
  const badges = element('div', 'requirement-badges');
  badges.append(statusBadge(item.status));
  if (item.scope) badges.append(element('span', 'badge', item.scope));
  head.append(titleBlock, badges);
  article.append(head);
  if (item.summary) article.append(element('p', '', item.summary));
  if (item.impact) {
    const impact = element('p', 'requirement-impact');
    impact.append(element('strong', '', 'Для решения: '), document.createTextNode(String(item.impact)));
    article.append(impact);
  }
  if (item.supersedes) {
    const supersedes = element('p', 'requirement-supersedes');
    supersedes.append(element('strong', '', 'Заменяет: '), document.createTextNode(Array.isArray(item.supersedes) ? item.supersedes.join(', ') : String(item.supersedes)));
    article.append(supersedes);
  }
  const sources = sourceList(item.sources);
  if (sources) article.append(sources);
  return article;
}

function renderFilters() {
  const statusSelect = byId('requirements-status');
  const scopeSelect = byId('requirements-scope');
  const statuses = [...new Set(requirements.map(item => String(item.status || '')).filter(Boolean))];
  const scopes = [...new Set(requirements.map(item => String(item.scope || '')).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'));
  const order = ['Подтверждено', 'Устное пояснение', 'Наше решение', 'Не определено', 'Расхождение', 'official', 'inference', 'unresolved'];
  statuses.sort((a, b) => (order.indexOf(a) < 0 ? order.length : order.indexOf(a)) - (order.indexOf(b) < 0 ? order.length : order.indexOf(b)) || a.localeCompare(b, 'ru'));
  for (const status of statuses) {
    const option = element('option', '', status);
    option.value = status;
    statusSelect.append(option);
  }
  for (const scope of scopes) {
    const option = element('option', '', scope);
    option.value = scope;
    scopeSelect.append(option);
  }
  for (const id of ['requirements-search', 'requirements-status', 'requirements-scope']) byId(id).disabled = false;
}

function renderRequirements() {
  const search = byId('requirements-search').value.trim().toLocaleLowerCase('ru');
  const status = byId('requirements-status').value;
  const scope = byId('requirements-scope').value;
  const matches = requirements.filter(item => {
    if (status && item.status !== status) return false;
    if (scope && item.scope !== scope) return false;
    return !search || [item.id, item.title, item.scope, item.summary, item.impact, item.supersedes].flat().filter(Boolean).join(' ').toLocaleLowerCase('ru').includes(search);
  });
  const list = byId('requirements-list');
  list.replaceChildren(...matches.map(item => renderRequirement(item, requirements.indexOf(item))));
  byId('requirements-count').textContent = `${matches.length} из ${requirements.length}`;
  const state = byId('requirements-state');
  state.textContent = !requirements.length ? 'В реестре пока нет требований.' : !matches.length ? 'По этим фильтрам требований не найдено.' : '';
}

function scrollToHash() {
  if (!location.hash) return;
  try {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target) target.scrollIntoView();
  } catch (_) { /* Ignore invalid URL fragments. */ }
}

function renderBoundaries(items) {
  const container = byId('requirements-boundaries');
  container.replaceChildren();
  if (!Array.isArray(items) || !items.length) {
    container.append(element('p', 'muted', 'Границы проверки пока не описаны.'));
    return;
  }
  for (const item of items) {
    const article = element('article');
    article.append(element('h3', '', item.title || 'Без названия'), element('p', '', item.body || ''));
    container.append(article);
  }
}

function renderQuestions(items) {
  const container = byId('requirements-questions');
  container.replaceChildren();
  if (!Array.isArray(items) || !items.length) {
    container.append(element('p', 'muted', 'Открытых вопросов в реестре нет.'));
    return;
  }
  for (const item of items) {
    const article = element('article');
    if (item.id) article.append(element('span', 'requirement-question-id', item.id));
    article.append(element('h3', '', item.text || 'Вопрос без текста'));
    const sources = sourceList(item.sources);
    if (sources) article.append(sources);
    container.append(article);
  }
}

function renderSourceCatalog(items) {
  const container = byId('requirements-sources');
  container.replaceChildren();
  if (!Array.isArray(items) || !items.length) {
    container.append(element('p', 'muted', 'Каталог источников пока не заполнен.'));
    return;
  }
  for (const [index, item] of items.entries()) {
    const article = element('article');
    article.id = validAnchor(item.id, index);
    if (item.id) article.append(element('span', 'requirement-source-id', item.id));
    article.append(element('h3', '', item.title || 'Источник без названия'));
    if (item.summary) article.append(element('p', '', item.summary));
    if (item.metadata) {
      const lines = Array.isArray(item.metadata) ? item.metadata : typeof item.metadata === 'object' ? Object.entries(item.metadata).map(([key, value]) => `${key}: ${value}`) : [item.metadata];
      for (const line of lines) article.append(element('p', 'muted', line));
    }
    const sources = sourceList(item.sources);
    if (sources) article.append(sources);
    container.append(article);
  }
}

async function loadRequirements() {
  try {
    const response = await fetch('/data/requirements-data.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data || !Array.isArray(data.requirements)) throw new Error('неверный формат реестра');
    requirements = data.requirements.filter(item => item && typeof item === 'object');
    byId('requirements-summary').textContent = typeof data.summary === 'string' && data.summary ? data.summary : 'Реестр требований к решению и ссылки на подтверждающие материалы.';
    if (data.updated_at) {
      const date = new Date(data.updated_at);
      byId('requirements-updated').textContent = Number.isNaN(date.getTime()) ? `Обновлено: ${data.updated_at}` : `Обновлено: ${new Intl.DateTimeFormat('ru-RU', {dateStyle: 'long'}).format(date)}`;
    }
    renderFilters();
    renderRequirements();
    renderBoundaries(data.boundaries);
    renderSourceCatalog(data.sources_catalog);
    renderQuestions(data.open_questions);
    scrollToHash();
  } catch (error) {
    byId('requirements-summary').textContent = 'Реестр пока недоступен.';
    const state = byId('requirements-state');
    state.classList.add('is-error');
    state.textContent = `Не удалось загрузить требования: ${error.message}. Попробуйте обновить страницу.`;
    byId('requirements-boundaries').replaceChildren(element('p', 'muted', 'Данные пока недоступны.'));
    byId('requirements-sources').replaceChildren(element('p', 'muted', 'Данные пока недоступны.'));
    byId('requirements-questions').replaceChildren(element('p', 'muted', 'Данные пока недоступны.'));
  }
}

for (const id of ['requirements-search', 'requirements-status', 'requirements-scope']) {
  byId(id).addEventListener(id === 'requirements-search' ? 'input' : 'change', renderRequirements);
}
window.addEventListener('hashchange', scrollToHash);
loadRequirements();

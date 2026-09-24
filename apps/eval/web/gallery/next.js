const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const $ = selector => document.querySelector(selector);
function renderTable(table) {
  if (!Array.isArray(table.rows) || !table.rows.length) return `<div class="pending-table"><h3>${esc(table.title)}</h3><p>Измерения ожидаются.</p></div>`;
  const columns = table.columns || [];
  return `<div class="result-table"><h3>${esc(table.title)}</h3><div class="matrix-wrap"><table><thead><tr>${columns.map(col => `<th>${esc(col.label)}</th>`).join('')}</tr></thead><tbody>${table.rows.map(row => `<tr>${columns.map(col => `<td>${esc(row[col.key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${table.note ? `<p class="table-note">${esc(table.note)}</p>` : ''}</div>`;
}
function renderExamples(examples) {
  if (!Array.isArray(examples) || !examples.length) return '';
  const safeImage = item => {
    const url = item.url || '';
    return /^\/data\/evidence\/crops\/[a-zA-Z0-9._-]+\.(?:jpg|jpeg|png|webp)$/.test(url)
      ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" aria-label="Открыть ${esc(item.label)} в полном размере"><img src="${esc(url)}" alt="${esc(item.label)}" loading="lazy" decoding="async"></a>`
      : '<div class="example-missing">Кроп не опубликован</div>';
  };
  return `<div class="examples"><h3>Как выбран фрагмент кадра</h3><p>Исходное фото, выбранная бутылка и этикетка показаны без ответа или эталона.</p>${examples.map(example => `<article class="example"><h4>${esc(example.title)}</h4><p>${esc(example.note)}</p><div class="example-images">${(example.images || []).map(item => `<figure>${safeImage(item)}<figcaption>${esc(item.label)}</figcaption></figure>`).join('')}</div></article>`).join('')}</div>`;
}
function renderSection(section) {
  const status = section.status === 'ready' ? 'Опубликовано' : section.status === 'partial' ? 'Часть данных' : 'Ожидается';
  const safeSource = source => {
    try { const url = new URL(source.url); return url.protocol === 'https:' && url.hostname && !url.username && !url.password; }
    catch { return false; }
  };
  const sources = (section.sources || []).filter(safeSource).map(source => `<a href="${esc(source.url)}" rel="noopener noreferrer" target="_blank">${esc(source.label || source.url)} ↗</a>`).join(' · ');
  return `<section class="panel report-section" id="${esc(section.id)}"><div class="section-heading"><h2>${esc(section.title)}</h2><span class="badge ${section.status === 'ready' ? '' : 'pending'}">${status}</span></div><p>${esc(section.summary)}</p>${(section.tables || []).map(renderTable).join('')}${renderExamples(section.examples)}${(section.notes || []).length ? `<div class="method-notes"><h3>Как читать</h3><ul>${section.notes.map(note => `<li>${esc(note)}</li>`).join('')}</ul></div>` : ''}${sources ? `<p class="sources">Источники: ${sources}</p>` : ''}</section>`;
}
(async function loadReport(){try{
  const response = await fetch('next-data.json', {cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.schema_version !== 1 || !Array.isArray(data.sections)) throw new Error('неизвестная версия данных');
  const updated = data.updated_at ? new Date(data.updated_at) : null;
  $('#report-status').textContent = updated && !Number.isNaN(updated.getTime())
    ? `Обновлено: ${new Intl.DateTimeFormat('ru-RU', {dateStyle:'medium', timeStyle:'short', timeZone:'Europe/Moscow'}).format(updated)}`
    : 'Результаты следующего эксперимента готовятся';
  $('#report-sections').innerHTML = data.sections.map(renderSection).join('');
}catch(error){ $('#report-status').textContent = `Не удалось загрузить отчёт: ${error.message}`; }})();

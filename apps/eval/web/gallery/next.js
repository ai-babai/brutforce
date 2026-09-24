const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const $ = selector => document.querySelector(selector);
function renderTable(table) {
  if (!Array.isArray(table.rows) || !table.rows.length) return `<div class="pending-table"><h3>${esc(table.title)}</h3><p>Измерения ожидаются.</p></div>`;
  const columns = table.columns || [];
  return `<div class="result-table"><h3>${esc(table.title)}</h3><div class="matrix-wrap"><table><thead><tr>${columns.map(col => `<th>${esc(col.label)}</th>`).join('')}</tr></thead><tbody>${table.rows.map(row => `<tr>${columns.map(col => `<td>${esc(row[col.key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${table.note ? `<p class="table-note">${esc(table.note)}</p>` : ''}</div>`;
}
function renderSection(section) {
  const status = section.status === 'ready' ? 'Опубликовано' : section.status === 'partial' ? 'Часть данных' : 'Ожидается';
  const sources = (section.sources || []).filter(source => /^https:\/\//.test(source.url || '')).map(source => `<a href="${esc(source.url)}" rel="noopener noreferrer" target="_blank">${esc(source.label || source.url)} ↗</a>`).join(' · ');
  return `<section class="panel report-section" id="${esc(section.id)}"><div class="section-heading"><h2>${esc(section.title)}</h2><span class="badge ${section.status === 'ready' ? '' : 'pending'}">${status}</span></div><p>${esc(section.summary)}</p>${(section.tables || []).map(renderTable).join('')}${(section.notes || []).length ? `<div class="method-notes"><h3>Как читать</h3><ul>${section.notes.map(note => `<li>${esc(note)}</li>`).join('')}</ul></div>` : ''}${sources ? `<p class="sources">Источники: ${sources}</p>` : ''}</section>`;
}
(async function loadReport(){try{
  const response = await fetch('next-data.json', {cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.schema_version !== 1 || !Array.isArray(data.sections)) throw new Error('неизвестная версия данных');
  $('#report-status').textContent = data.updated_at ? `Обновлено: ${data.updated_at}` : 'Результаты следующего эксперимента готовятся';
  $('#report-sections').innerHTML = data.sections.map(renderSection).join('');
}catch(error){ $('#report-status').textContent = `Не удалось загрузить отчёт: ${error.message}`; }})();

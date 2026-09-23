'use strict';
function row(parent, values) { const tr = document.createElement('tr'); for (const value of values) { const td = document.createElement('td'); td.textContent = value; tr.append(td); } parent.append(tr); }
fetch('report-data.json').then(r => { if (!r.ok) throw new Error('Отчёт ещё не опубликован'); return r.json(); }).then(d => {
  for (const [value,label] of [[d.outputs,'AI-изображений'],[d.augmentations,'аугментаций Pillow'],[d.wines,'вин'],['$'+d.confirmed_total_usd.toFixed(3),'подтверждённые API-расходы']]) {
    const item=document.createElement('div'),strong=document.createElement('strong'); strong.textContent=value; item.append(strong,document.createTextNode(label));document.querySelector('#totals').append(item);
  }
  for (const m of d.generation) row(document.querySelector('#generation'),[m.name,m.outputs,'$'+m.unit_cost.toFixed(4),m.accepted+' / '+m.pending+' / '+m.rejected,m.accepted ? '$'+m.cost_per_accepted.toFixed(3) : 'нет принятых']);
  const render=()=>{const body=document.querySelector('#recognition');body.replaceChildren();for(const m of d.recognition.filter(x=>document.querySelector('#variant').value==='all'||x.base)) row(body,[m.name,m.service,m.top1,m.top5,m.top20,m.latency]);};
  document.querySelector('#variant').addEventListener('change',render);render();
  document.querySelector('#cost').textContent='Генерация: $'+d.generation_cost_usd.toFixed(5)+'. Проверка DeepSeek: $'+d.qa_cost_usd.toFixed(5)+'. Все OCR-вызовы, включая ранние пробы: $'+d.recognition_cost_usd.toFixed(5)+'. Неопределённые списания зарезервированы отдельно: до $'+d.uncertain_reserve_usd.toFixed(3)+'. Тарифы и фактические расходы этого запуска, 24 сентября 2026.';
}).catch(e=>{document.querySelector('#totals').textContent=e.message;});

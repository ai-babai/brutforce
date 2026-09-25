const copy={
 results:['Похожие вина','Вместо пяти рамок — один список. Лидер выделен крупной бутылкой, названием и короткой подписью. Фото и две иконки не заключены в отдельную плашку.','Компромисс: на первом экране чуть меньше кандидатов. Вся строка остаётся нажимаемой; полные названия и известные свойства сохраняются.'],
 home:['Главная','Одна цельная кремовая сцена мягко переходит в белый фон. Заголовок, пёс и основная кнопка образуют общую ось. У вторичных действий нет лишних подложек.','Главное действие осталось заметным. В основной кнопке сохранены камера слева и рамка сканирования справа. Вторичные действия собраны ближе друг к другу. Камера, галерея и поиск по названию доступны сразу.'],
 capture:['Камера','Крупный видоискатель без тени и массивного скругления. Более тонкая рамка, спокойная типографика и одинаковый контур иконок.','Это симуляция камеры для оценки композиции. Упрощение визуальное: «Сделать снимок» и выбор из галереи не поменяли назначение.'],
 detail:['Карточка вина','Бутылка на общей поверхности вместо отдельной плашки. Название и доступные свойства отделены только воздухом и тонкими линиями.','Сохранение осталось заметным. Вина и поля здесь демонстрационные; окончательная карточка реального каталога может содержать больше данных.']
};
document.querySelectorAll('[data-screen]').forEach(button=>button.addEventListener('click',()=>{
 const key=button.dataset.screen;const [name,explanation,tradeoff]=copy[key];
 document.querySelectorAll('[data-screen]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
 for(const [id,prefix] of [['before','before'],['after','air']]){const path=`review/${prefix}-${key}-430.png`;document.getElementById(id).src=path;document.getElementById(id).alt=`${id==='before'?'До':'Air'} · ${name}`;document.getElementById(`${id}-link`).href=path;}
 document.getElementById('explanation').textContent=explanation;document.getElementById('tradeoff').textContent=tradeoff;document.getElementById('try-link').href=`./?screen=${key}`;
}));
document.querySelector('#icon-samples').innerHTML=[['home','Главная'],['search','Поиск'],['camera','Камера'],['gallery','Галерея'],['bookmark','Сохранить'],['retry','Повтор'],['pause','Пауза']].map(([name,label])=>`<div class="sample"><svg viewBox="0 0 256 256" class="icon" aria-hidden="true">${AIR_ICONS[name]}</svg><span>${label}</span></div>`).join('');

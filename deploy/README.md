# Демонстрационный релиз

Демо: https://demo.maks.dzap.pw
Отчёт: https://reps.maks.dzap.pw/behavior/
Существующий UX Atlas остаётся https://reps.maks.dzap.pw/view.

Сервер Sigma, сервис brutforce-demo.service от lct, порт 127.0.0.1:8097.
Релизы: /srv/lct/maks/behavior-demo/releases/<revision>; current — символическая ссылка.
Содержимое релиза: brutforce-api (Linux amd64), web/ (Vite dist), reports/ (статический отчёт).
Фото не передаются API и не сохраняются на сервере. Данные результата синтетические.

Порядок: быстрые спеки → сборка → локальный браузерный smoke → перенос нового каталога
→ переключение current → запуск/перезапуск только brutforce-demo → Caddy validate/reload
→ HTTPS smoke. Не менять чужие сайты и не публиковать исходные конкурсные материалы.

Откат: переключить current на предыдущий каталог и restart brutforce-demo.
Для первого релиза: остановить brutforce-demo, убрать только z-brutforce-demo.caddy,
восстановить резервную копию maks-reports.caddy, validate и reload Caddy.

Файл demo.caddy устанавливается как /etc/caddy/sites-enabled/z-brutforce-demo.caddy: общий snippet загружается раньше из lct-previews.caddy.

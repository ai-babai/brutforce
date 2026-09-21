# Демонстрационный релиз

Общий TEST/PROD и команды Sigma: [PIPELINE.md](PIPELINE.md).
Ниже — действующий личный preview Макса; это отдельная среда.

Демо: https://demo.maks.dzap.pw
Отчёт: https://reps.maks.dzap.pw/behavior/
Существующий UX Atlas остаётся https://reps.maks.dzap.pw/view.

Сервер Sigma, сервис brutforce-demo.service от lct, порт 127.0.0.1:8097.
Релизы: /srv/lct/maks/behavior-demo/releases/<revision>; current — символическая ссылка.
Содержимое релиза: brutforce-api (Linux amd64), web/ (Vite dist), reports/ (статический отчёт).
Фото сохраняются приватно в /srv/lct/data/maks/demo-photos (lct, 0700; файлы 0600), вне релизов и web root. Лимит хранилища 200 MiB; автоудаления нет. Данные распознавания пока синтетические. См. contracts/photo-upload.md.
Перед запуском новой unit: install -d -o lct -g lct -m 0700 /srv/lct/data/maks/demo-photos. UPLOAD_DIR и ReadWritePaths должны указывать на этот каталог.

Порядок: быстрые спеки → сборка → локальный браузерный smoke → перенос нового каталога
→ переключение current → запуск/перезапуск только brutforce-demo → Caddy validate/reload
→ HTTPS smoke. Не менять чужие сайты и не публиковать исходные конкурсные материалы.

Откат: переключить current на предыдущий каталог и restart brutforce-demo.
Для первого релиза: остановить brutforce-demo, убрать только z-brutforce-demo.caddy,
восстановить резервную копию maks-reports.caddy, validate и reload Caddy.

Файл demo.caddy устанавливается как /etc/caddy/sites-enabled/z-brutforce-demo.caddy: общий snippet загружается раньше из lct-previews.caddy.

## Каталог PostgreSQL — BE-031

Демо Макса использует только `lct_maks`. Перед выпуском выполнить миграцию отдельной
ролью через `MIGRATION_DATABASE_URL`; точная команда в `apps/api/README.md`.
Не выполнять down/reset постоянной базы при откате приложения.

Runtime получает только `DATABASE_URL` из защищённого
`/etc/lct-db/brutforce-demo.env` (root:lct, 0640). Это копия runtime-настройки зоны,
не весь `/etc/lct-db/maks.env`: migration и тестовые полномочия приложению не нужны.
Systemd drop-in `brutforce-demo.service.d/database.conf` подключает этот EnvironmentFile.
Не хранить значения в Git. При смене runtime-credential обновить и эту служебную копию.

Перед публикацией: обычный fast run плюс реальный PostgreSQL-набор через `lct-db-test maks`.
Проверки не очищают постоянные базы. `/v1/catalog` и ручной поиск проверяются после перезапуска.
Фото, отчёт и Caddy-маршруты не меняются из-за подключения БД.

Откат первого подключения: вернуть предыдущий release и убрать только добавленный DB drop-in,
затем restart `brutforce-demo`. Таблицы и данные сохранить. Предыдущий бинарник использует
встроенный синтетический каталог; это осознанный откат релиза, не автоматический fallback.

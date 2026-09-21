# PostgreSQL на Sigma: команды

Проверено 2026-09-21. PostgreSQL 18.6, кластер 18/main. Общая схема: [DATABASE.md](DATABASE.md).
Серверная копия этого файла: /srv/infra/lct-db/DATABASE.md.

## Подключение

Работайте как lct. `/etc/lct-db/shared.env`, `maks.env`, `roman.env` доступны root:lct 0640.
В каждом файле четыре ключа (пример Ромы):

- LCT_ROMAN_RUNTIME_DATABASE_URL — приложение, постоянная база.
- LCT_ROMAN_MIGRATION_DATABASE_URL — миграции, постоянная база.
- LCT_ROMAN_TEST_RUNTIME_DATABASE_URL — приложение в тестах.
- LCT_ROMAN_TEST_MIGRATION_DATABASE_URL — миграции тестовой базы.

Для shared/maks замените ROMAN на SHARED/MAKS. Значения — секреты, не печатайте их.
URLs используют Unix socket /var/run/postgresql и SCRAM, поэтому работают из opencode-nl.
У ролей нет superuser/CREATEDB/CREATEROLE. Runtime имеет CRUD, migration владеет схемой.
Тестовые роли отдельные, они не получают доступ к постоянным базам.

Пример запуска приложения в зоне Ромы (Bash на сервере):

```bash
source /etc/lct-db/roman.env
export DATABASE_URL="$LCT_ROMAN_RUNTIME_DATABASE_URL"
# Теперь запустите обычную команду приложения из своей рабочей копии.
```

Не запускайте `env`, `set -x` или echo URL. Текущий Go demo ещё не подключён к БД.
Для клиента на компьютере используйте SSH-туннель на 127.0.0.1:5432;
учётные данные берутся из защищённого env. Не открывайте 5432 наружу.

## Быстрые тесты без sudo

```bash
lct-db-test roman psql -X -Atqc 'SELECT current_database(), current_user'
lct-db-test maks bash ./path/to/your-db-tests.sh
```

Второй путь — пример команды вашего проекта, готового файла с этим именем нет.
Допустимые зоны: shared, maks, roman. Команда обязательна.
Инструмент **очищает public только своей тестовой базы** lct_test_<zone> перед запуском.
В ней нельзя хранить ценные данные. Постоянные базы не пересоздаются.
Он держит файловую блокировку зоны до завершения команды; занятая зона даёт exit 75.
Все DB-тесты в этой зоне запускайте через этот инструмент, иначе блокировка не поможет.
Не запускайте из него фоновые долгоживущие процессы.

Команда получает DATABASE_URL и PG* для тестовой runtime-роли;
MIGRATION_DATABASE_URL — для применения миграций. Сначала миграции и малый seed,
затем реальные интеграционные тесты. Права новых таблиц автоматически даются runtime.
Goose и продуктовые SQL-миграции добавляются при подключении приложения, сейчас их нет.

Исходник: [lct-db-test](db-tools/lct-db-test), установлен /usr/local/bin/lct-db-test.
Зависимости: Bash, Python3 stdlib, psql, flock. Новый Python venv не требуется.
Блокировки: /srv/lct/data/db-test-locks. Разные зоны выполняются параллельно.
Проверено: reset+connect 0,17–0,20 с; DDL runtime запрещён; занятая/неизвестная зона отвергается.
Это время пустой схемы, не импорта датасета или полного набора продуктовых тестов.

## Резервное копирование

lct-db-backup.timer запускается ежедневно в 03:17 UTC (06:17 МСК).
Дампы трёх постоянных баз: /srv/lct/data/backups/postgres, только root/postgres.
Срок хранения 14 дней; удаляются только собственные файлы заданных имён.
Сначала создаётся .partial, после проверки pg_restore --list переименовывается в .dump.
Это копия на том же диске: внешнее хранение пока не подключено.

```bash
sudo systemctl start lct-db-backup.service
sudo systemctl show lct-db-backup.service -p Result -p ExecMainStatus
sudo systemctl list-timers lct-db-backup.timer
```

Проверено реальное восстановление дампа Maks в отдельную одноразовую базу.
Для восстановления оператор сначала создаёт новую изолированную базу через postgres,
передаёт дамп в pg_restore через stdin, проверяет таблицы/данные и права.
Не восстанавливайте поверх постоянной БД и не удаляйте её без отдельного поручения.
Роли/пароли не входят в pg_dump: их надо создать до восстановления на другом сервере.

## Администрирование и перенос

```bash
sudo -u postgres psql -X -d postgres
sudo systemctl status postgresql@18-main.service
```

Конфигурация: /etc/postgresql/18/main; данные: /var/lib/postgresql/18/main.
Журнал: /var/log/postgresql/postgresql-18-main.log. Buzz использует свой PostgreSQL.

Для переноса: установить PG18, создать роли и базы из карты, выдать новые секреты отдельно,
восстановить дампы, проверить подключения и только затем переключить приложения.
Скрипт копирования и units сохранены в [db-tools](db-tools/README.md).
Не копируйте работающий datadir и не переносите секреты через Git.

При изменении путей/ролей/команд обновляйте этот файл, серверную копию и infra-os в одной задаче.
Откат установки — остановка только нового PG unit, если клиентов нет; данные сохранять.

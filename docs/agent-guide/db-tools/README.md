# Установленные инструменты LCT DB

Проверенные копии на 2026-09-21. Инструкция: [DATABASE-OPS.md](../DATABASE-OPS.md).

- lct-db-test → /usr/local/bin/lct-db-test (root:root 0755).
- lct-db-backup → /usr/local/sbin/lct-db-backup (root:root 0755).
- lct-db-backup.{service,timer} → /etc/systemd/system/ (root:root 0644).

Это не установщик PostgreSQL или ролей. Не запускайте backup до подготовки путей и баз.
Секретные env не входят в комплект. После изменения синхронизируйте Git и сервер.

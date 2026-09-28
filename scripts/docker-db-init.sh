#!/bin/sh
pass=$(cat /run/secrets/app_password)
case "$pass" in *[!0-9a-f]*|'') echo 'app password must be nonempty lowercase hex' >&2; exit 1;; esac
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE brutforce_app LOGIN PASSWORD '$pass';
GRANT CONNECT ON DATABASE brutforce TO brutforce_app;
GRANT USAGE ON SCHEMA public TO brutforce_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO brutforce_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO brutforce_app;
SQL

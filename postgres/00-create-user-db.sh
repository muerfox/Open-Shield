#!/bin/bash
# Some tools default to a database named after the connecting user when no
# dbname is given (this is standard libpq behavior). Create one so any such
# connection lands somewhere real instead of erroring with "database ...
# does not exist" — the panel/pdns databases created in init.sql remain the
# actual databases those services use.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE "$POSTGRES_USER";
EOSQL

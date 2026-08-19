-- Creates separate databases for the panel and for PowerDNS.
-- POSTGRES_USER (from env) already exists and owns both databases.
-- The PowerDNS gpgsql backend (pschiffe/pdns-pgsql image) creates its own
-- schema in the `pdns` database automatically on first boot when the
-- expected tables are missing, so no manual schema is created here.
CREATE DATABASE panel;
CREATE DATABASE pdns;

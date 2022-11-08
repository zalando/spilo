CREATE EXTENSION amcheck_next;  /* the upgrade script must delete it before running pg_upgrade --check! */

\c test_db

CREATE TABLE with_oids() WITH OIDS;

CREATE EXTENSION timescaledb;

CREATE TABLE "fOo" (id bigint NOT NULL PRIMARY KEY);
SELECT create_hypertable('"fOo"', 'id', chunk_time_interval => 100000);
INSERT INTO "fOo" SELECT * FROM generate_series(1, 1000000);
ALTER TABLE "fOo" ALTER COLUMN id SET STATISTICS 500;

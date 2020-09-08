CREATE DATABASE test_db;
\c test_db

CREATE EXTENSION timescaledb;

CREATE TABLE "fOo" (id bigint NOT NULL PRIMARY KEY);
SELECT create_hypertable('"fOo"', 'id', chunk_time_interval => 100000);
INSERT INTO "fOo" SELECT * FROM generate_series(1, 3000000);
ALTER TABLE "fOo" ALTER COLUMN id SET STATISTICS 500;

CREATE UNLOGGED TABLE "bAr" ("bUz" INTEGER);
ALTER TABLE "bAr" ALTER COLUMN "bUz" SET STATISTICS 500;
INSERT INTO "bAr" SELECT * FROM generate_series(1, 300000);

CREATE TABLE with_oids() WITH OIDS;

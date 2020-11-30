\c test_db

CREATE EXTENSION timescaledb;

CREATE TABLE "fOo" (id bigint NOT NULL PRIMARY KEY);
SELECT create_hypertable('"fOo"', 'id', chunk_time_interval => 100000);
INSERT INTO "fOo" SELECT * FROM generate_series(1, 1000000);
ALTER TABLE "fOo" ALTER COLUMN id SET STATISTICS 500;

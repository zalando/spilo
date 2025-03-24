CREATE EXTENSION pg_repack; /* the upgrade script must delete it before running pg_upgrade --check! */

CREATE DATABASE test_db;
\c test_db

CREATE UNLOGGED TABLE "bAr" ("bUz" INTEGER);
ALTER TABLE "bAr" ALTER COLUMN "bUz" SET STATISTICS 500;
INSERT INTO "bAr" SELECT * FROM generate_series(1, 100000);

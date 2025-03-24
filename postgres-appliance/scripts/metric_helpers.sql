CREATE SCHEMA IF NOT EXISTS metric_helpers AUTHORIZATION postgres;

GRANT USAGE ON SCHEMA metric_helpers TO admin, robot_zmon;

SET search_path TO metric_helpers;

-- table and btree bloat estimation queries are borrowed from https://github.com/ioguix/pgsql-bloat-estimation
CREATE OR REPLACE FUNCTION get_table_bloat_approx (
    OUT t_database name,
    OUT t_schema_name name,
    OUT t_table_name name,
    OUT t_real_size numeric,
    OUT t_extra_size double precision,
    OUT t_extra_ratio double precision,
    OUT t_fill_factor integer,
    OUT t_bloat_size double precision,
    OUT t_bloat_ratio double precision,
    OUT t_is_na boolean
) RETURNS SETOF record AS
$_$
SELECT
  current_database(),
  schemaname,
  tblname,
  (bs*tblpages) AS real_size,
  ((tblpages-est_tblpages)*bs) AS extra_size,
  CASE WHEN tblpages - est_tblpages > 0
    THEN 100 * (tblpages - est_tblpages)/tblpages::float
    ELSE 0
  END AS extra_ratio,
  fillfactor,
  CASE WHEN tblpages - est_tblpages_ff > 0
    THEN (tblpages-est_tblpages_ff)*bs
    ELSE 0
  END AS bloat_size,
  CASE WHEN tblpages - est_tblpages_ff > 0
    THEN 100 * (tblpages - est_tblpages_ff)/tblpages::float
    ELSE 0
  END AS bloat_ratio,
  is_na
FROM (
  SELECT ceil( reltuples / ( (bs-page_hdr)/tpl_size ) ) + ceil( toasttuples / 4 ) AS est_tblpages,
    ceil( reltuples / ( (bs-page_hdr)*fillfactor/(tpl_size*100) ) ) + ceil( toasttuples / 4 ) AS est_tblpages_ff,
    tblpages, fillfactor, bs, tblid, schemaname, tblname, heappages, toastpages, is_na
    -- , tpl_hdr_size, tpl_data_size, pgstattuple(tblid) AS pst -- (DEBUG INFO)
  FROM (
    SELECT
      ( 4 + tpl_hdr_size + tpl_data_size + (2*ma)
        - CASE WHEN tpl_hdr_size%ma = 0 THEN ma ELSE tpl_hdr_size%ma END
        - CASE WHEN ceil(tpl_data_size)::int%ma = 0 THEN ma ELSE ceil(tpl_data_size)::int%ma END
      ) AS tpl_size, bs - page_hdr AS size_per_block, (heappages + toastpages) AS tblpages, heappages,
      toastpages, reltuples, toasttuples, bs, page_hdr, tblid, schemaname, tblname, fillfactor, is_na
      -- , tpl_hdr_size, tpl_data_size
    FROM (
      SELECT
        tbl.oid AS tblid, ns.nspname AS schemaname, tbl.relname AS tblname, tbl.reltuples,
        tbl.relpages AS heappages, coalesce(toast.relpages, 0) AS toastpages,
        coalesce(toast.reltuples, 0) AS toasttuples,
        coalesce(substring(
          array_to_string(tbl.reloptions, ' ')
          FROM 'fillfactor=([0-9]+)')::smallint, 100) AS fillfactor,
        current_setting('block_size')::numeric AS bs,
        CASE WHEN version()~'mingw32' OR version()~'64-bit|x86_64|ppc64|ia64|amd64' THEN 8 ELSE 4 END AS ma,
        24 AS page_hdr,
        23 + CASE WHEN MAX(coalesce(s.null_frac,0)) > 0 THEN ( 7 + count(s.attname) ) / 8 ELSE 0::int END
           + CASE WHEN bool_or(att.attname = 'oid' and att.attnum < 0) THEN 4 ELSE 0 END AS tpl_hdr_size,
        sum( (1-coalesce(s.null_frac, 0)) * coalesce(s.avg_width, 0) ) AS tpl_data_size,
        bool_or(att.atttypid = 'pg_catalog.name'::regtype)
          OR sum(CASE WHEN att.attnum > 0 THEN 1 ELSE 0 END) <> count(s.attname) AS is_na
      FROM pg_attribute AS att
        JOIN pg_class AS tbl ON att.attrelid = tbl.oid
        JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
        LEFT JOIN pg_stats AS s ON s.schemaname=ns.nspname
          AND s.tablename = tbl.relname AND s.inherited=false AND s.attname=att.attname
        LEFT JOIN pg_class AS toast ON tbl.reltoastrelid = toast.oid
      WHERE NOT att.attisdropped
        AND tbl.relkind = 'r'
      GROUP BY 1,2,3,4,5,6,7,8,9,10
      ORDER BY 2,3
    ) AS s
  ) AS s2
) AS s3 WHERE schemaname NOT LIKE 'information_schema';
$_$ LANGUAGE sql SECURITY DEFINER IMMUTABLE STRICT SET search_path to 'pg_catalog';

CREATE OR REPLACE VIEW table_bloat AS SELECT * FROM get_table_bloat_approx();

CREATE OR REPLACE FUNCTION get_btree_bloat_approx (
    OUT i_database name,
    OUT i_schema_name name,
    OUT i_table_name name,
    OUT i_index_name name,
    OUT i_real_size numeric,
    OUT i_extra_size numeric,
    OUT i_extra_ratio double precision,
    OUT i_fill_factor integer,
    OUT i_bloat_size double precision,
    OUT i_bloat_ratio double precision,
    OUT i_is_na boolean
) RETURNS SETOF record AS
$_$
SELECT current_database(), nspname AS schemaname, tblname, idxname, bs*(relpages)::bigint AS real_size,
  bs*(relpages-est_pages)::bigint AS extra_size,
  100 * (relpages-est_pages)::float / relpages AS extra_ratio,
  fillfactor,
  CASE WHEN relpages > est_pages_ff
    THEN bs*(relpages-est_pages_ff)
    ELSE 0
  END AS bloat_size,
  100 * (relpages-est_pages_ff)::float / relpages AS bloat_ratio,
  is_na
  -- , 100-(pst).avg_leaf_density AS pst_avg_bloat, est_pages, index_tuple_hdr_bm, maxalign, pagehdr, nulldatawidth, nulldatahdrwidth, reltuples, relpages -- (DEBUG INFO)
FROM (
  SELECT coalesce(1 +
         ceil(reltuples/floor((bs-pageopqdata-pagehdr)/(4+nulldatahdrwidth)::float)), 0 -- ItemIdData size + computed avg size of a tuple (nulldatahdrwidth)
      ) AS est_pages,
      coalesce(1 +
         ceil(reltuples/floor((bs-pageopqdata-pagehdr)*fillfactor/(100*(4+nulldatahdrwidth)::float))), 0
      ) AS est_pages_ff,
      bs, nspname, tblname, idxname, relpages, fillfactor, is_na
      -- , pgstatindex(idxoid) AS pst, index_tuple_hdr_bm, maxalign, pagehdr, nulldatawidth, nulldatahdrwidth, reltuples -- (DEBUG INFO)
  FROM (
      SELECT maxalign, bs, nspname, tblname, idxname, reltuples, relpages, idxoid, fillfactor,
            ( index_tuple_hdr_bm +
                maxalign - CASE -- Add padding to the index tuple header to align on MAXALIGN
                  WHEN index_tuple_hdr_bm%maxalign = 0 THEN maxalign
                  ELSE index_tuple_hdr_bm%maxalign
                END
              + nulldatawidth + maxalign - CASE -- Add padding to the data to align on MAXALIGN
                  WHEN nulldatawidth = 0 THEN 0
                  WHEN nulldatawidth::integer%maxalign = 0 THEN maxalign
                  ELSE nulldatawidth::integer%maxalign
                END
            )::numeric AS nulldatahdrwidth, pagehdr, pageopqdata, is_na
            -- , index_tuple_hdr_bm, nulldatawidth -- (DEBUG INFO)
      FROM (
          SELECT n.nspname, ct.relname AS tblname, i.idxname, i.reltuples, i.relpages,
              i.idxoid, i.fillfactor, current_setting('block_size')::numeric AS bs,
              CASE -- MAXALIGN: 4 on 32bits, 8 on 64bits (and mingw32 ?)
                WHEN version() ~ 'mingw32' OR version() ~ '64-bit|x86_64|ppc64|ia64|amd64' THEN 8
                ELSE 4
              END AS maxalign,
              /* per page header, fixed size: 20 for 7.X, 24 for others */
              24 AS pagehdr,
              /* per page btree opaque data */
              16 AS pageopqdata,
              /* per tuple header: add IndexAttributeBitMapData if some cols are null-able */
              CASE WHEN max(coalesce(s.stanullfrac,0)) = 0
                  THEN 2 -- IndexTupleData size
                  ELSE 2 + (( 32 + 8 - 1 ) / 8) -- IndexTupleData size + IndexAttributeBitMapData size ( max num filed per index + 8 - 1 /8)
              END AS index_tuple_hdr_bm,
              /* data len: we remove null values save space using it fractionnal part from stats */
              sum( (1-coalesce(s.stanullfrac, 0)) * coalesce(s.stawidth, 1024)) AS nulldatawidth,
              max( CASE WHEN a.atttypid = 'pg_catalog.name'::regtype THEN 1 ELSE 0 END ) > 0 AS is_na
          FROM (
              SELECT idxname, reltuples, relpages, tbloid, idxoid, fillfactor,
                  CASE WHEN indkey[i]=0 THEN idxoid ELSE tbloid END AS att_rel,
                  CASE WHEN indkey[i]=0 THEN i ELSE indkey[i] END AS att_pos
              FROM (
                  SELECT idxname, reltuples, relpages, tbloid, idxoid, fillfactor, indkey, generate_series(1,indnatts) AS i
                  FROM (
                      SELECT ci.relname AS idxname, ci.reltuples, ci.relpages, i.indrelid AS tbloid,
                          i.indexrelid AS idxoid,
                          coalesce(substring(
                              array_to_string(ci.reloptions, ' ')
                              from 'fillfactor=([0-9]+)')::smallint, 90) AS fillfactor,
                          i.indnatts,
                          string_to_array(textin(int2vectorout(i.indkey)),' ')::int[] AS indkey
                      FROM pg_index i
                      JOIN pg_class ci ON ci.oid=i.indexrelid
                      WHERE ci.relam=(SELECT oid FROM pg_am WHERE amname = 'btree')
                        AND ci.relpages > 0
                  ) AS idx_data
              ) AS idx_data_cross
          ) i
          JOIN pg_attribute a ON a.attrelid = i.att_rel
                             AND a.attnum = i.att_pos
          JOIN pg_statistic s ON s.starelid = i.att_rel
                             AND s.staattnum = i.att_pos
          JOIN pg_class ct ON ct.oid = i.tbloid
          JOIN pg_namespace n ON ct.relnamespace = n.oid
          GROUP BY 1,2,3,4,5,6,7,8,9,10
      ) AS rows_data_stats
  ) AS rows_hdr_pdg_stats
) AS relation_stats;
$_$ LANGUAGE sql SECURITY DEFINER IMMUTABLE STRICT SET search_path to 'pg_catalog';

CREATE OR REPLACE VIEW index_bloat AS SELECT * FROM get_btree_bloat_approx();

CREATE OR REPLACE FUNCTION pg_stat_statements(showtext boolean) RETURNS SETOF public.pg_stat_statements AS
$$
  SELECT * FROM public.pg_stat_statements(showtext);
$$ LANGUAGE sql IMMUTABLE SECURITY DEFINER STRICT;

CREATE OR REPLACE VIEW pg_stat_statements AS SELECT * FROM pg_stat_statements(true);

CREATE OR REPLACE FUNCTION get_nearly_exhausted_sequences(
    IN  threshold float,
    OUT schemaname name,
    OUT sequencename name,
    OUT seq_percent_used numeric
 ) RETURNS SETOF record AS
$_$
SELECT *
FROM (
  SELECT 
    schemaname,
    sequencename,
    round(abs(
      ceil((abs(last_value::numeric - start_value) + 1) / increment_by) / 
        floor((CASE WHEN increment_by > 0
                    THEN (max_value::numeric - start_value)
                    ELSE (start_value::numeric - min_value)
                    END + 1) / increment_by
              ) * 100 
      ), 
    2) AS seq_percent_used
  FROM pg_sequences
  WHERE NOT CYCLE AND last_value IS NOT NULL
) AS s
WHERE seq_percent_used >= threshold;
$_$
LANGUAGE sql SECURITY DEFINER STRICT SET search_path to 'pg_catalog';

CREATE OR REPLACE VIEW nearly_exhausted_sequences AS SELECT * FROM get_nearly_exhausted_sequences(0.8);

REVOKE ALL ON ALL TABLES IN SCHEMA metric_helpers FROM public;
GRANT SELECT ON ALL TABLES IN SCHEMA metric_helpers TO admin, robot_zmon;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA metric_helpers FROM public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA metric_helpers TO admin, robot_zmon;

RESET search_path;

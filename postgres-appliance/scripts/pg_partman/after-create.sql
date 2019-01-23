DO $$
BEGIN
    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = 'part_man';
    IF FOUND THEN
        ALTER ROLE part_man WITH NOCREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
        GRANT part_man TO admin;
    ELSE
        CREATE ROLE part_man ADMIN admin;
    END IF;

    IF current_setting('server_version_num')::integer >= 110000 THEN
        EXECUTE 'GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA @extschema@ TO part_man';
    END IF;
END;$$;
GRANT USAGE ON SCHEMA @extschema@ TO part_man;
GRANT ALL ON ALL TABLES IN SCHEMA @extschema@ TO part_man;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA @extschema@ TO part_man;

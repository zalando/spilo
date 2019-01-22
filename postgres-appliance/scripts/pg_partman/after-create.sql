DO $$
BEGIN
    PERFORM * FROM pg_catalog.pg_authid WHERE rolname = 'partman';
    IF FOUND THEN
        ALTER ROLE partman WITH NOCREATEDB NOLOGIN NOCREATEROLE NOSUPERUSER NOREPLICATION INHERIT;
        GRANT partman TO admin;
    ELSE
        CREATE ROLE partman ADMIN admin;
    END IF;

    IF current_setting('server_version_num')::integer >= 110000 THEN
        EXECUTE 'GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA @extschema@ TO partman';
    END IF;
END;$$;
GRANT USAGE ON SCHEMA @extschema@ TO partman;
GRANT ALL ON ALL TABLES IN SCHEMA @extschema@ TO partman;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA @extschema@ TO partman;

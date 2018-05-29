CREATE SCHEMA IF NOT EXISTS user_management;

GRANT USAGE ON SCHEMA user_management TO admin;

SET search_path TO user_management;

CREATE OR REPLACE FUNCTION random_password (length integer) RETURNS text LANGUAGE sql AS
$$
WITH chars (c) AS (
    SELECT chr(33)
    UNION ALL
    SELECT chr(i) FROM generate_series (35, 38) AS t (i)
    UNION ALL
    SELECT chr(i) FROM generate_series (42, 90) AS t (i)
    UNION ALL
    SELECT chr(i) FROM generate_series (97, 122) AS t (i)
),
bricks (b) AS (
    -- build a pool of chars (the size will be the number of chars above times length)
    -- and shuffle it
    SELECT c FROM chars, generate_series(1, length) ORDER BY random()
)
SELECT substr(string_agg(b, ''), 1, length) FROM bricks;
$$
SET search_path to 'pg_catalog';

CREATE OR REPLACE FUNCTION create_application_user(username text)
 RETURNS text
 LANGUAGE plpgsql
AS $function$
DECLARE
    pw text;
BEGIN
    SELECT user_management.random_password(20) INTO pw;
    EXECUTE format($$ CREATE USER %I WITH PASSWORD %L $$, username, pw);
    RETURN pw;
END
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION create_application_user(text) FROM public;
GRANT EXECUTE ON FUNCTION create_application_user(text) TO admin;

COMMENT ON FUNCTION create_application_user(text) IS 'Creates a user that can login, sets the password to a strong random one,
which is then returned';



CREATE OR REPLACE FUNCTION create_user(username text)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    EXECUTE format($$ CREATE USER %I IN ROLE :HUMAN_ROLE, admin $$, username);
    EXECUTE format($$ ALTER ROLE %I SET log_statement TO 'all' $$, username);
END;
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION create_user(text) FROM public;
GRANT EXECUTE ON FUNCTION create_user(text) TO admin;

COMMENT ON FUNCTION create_user(text) IS 'Creates a user that is supposed to be a human, to be authenticated without a password';


CREATE OR REPLACE FUNCTION create_role(rolename text)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- set ADMIN to the admin user, so every member of admin can GRANT these roles to each other
    EXECUTE format($$ CREATE ROLE %I WITH ADMIN admin $$, rolename);
END;
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION create_role(text) FROM public;
GRANT EXECUTE ON FUNCTION create_role(text) TO admin;

COMMENT ON FUNCTION create_role(text) IS 'Creates a role that cannot log in, but can be used to set up fine-grained privileges';


CREATE OR REPLACE FUNCTION create_application_user_or_change_password(username text, password text)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    PERFORM 1 FROM pg_roles WHERE rolname = username;

    IF FOUND
    THEN
        EXECUTE format($$ ALTER ROLE %I WITH PASSWORD %L $$, username, password);
    ELSE
        EXECUTE format($$ CREATE USER %I WITH PASSWORD %L $$, username, password);
    END IF;
END
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION create_application_user_or_change_password(text, text) FROM public;
GRANT EXECUTE ON FUNCTION create_application_user_or_change_password(text, text) TO admin;

COMMENT ON FUNCTION create_application_user_or_change_password(text, text) IS 'USE THIS ONLY IN EMERGENCY!  The password will appear in the DB logs.
Creates a user that can login, sets the password to the one provided.
If the user already exists, sets its password.';


CREATE OR REPLACE FUNCTION revoke_admin(username text)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    EXECUTE format($$ REVOKE admin FROM %I $$, username);
END
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION revoke_admin(text) FROM public;
GRANT EXECUTE ON FUNCTION revoke_admin(text) TO admin;

COMMENT ON FUNCTION revoke_admin(text) IS 'Use this function to make a human user less privileged,
ie. when you want to grant someone read privileges only';


CREATE OR REPLACE FUNCTION drop_user(username text)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    EXECUTE format($$ DROP ROLE %I $$, username);
END
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION drop_user(text) FROM public;
GRANT EXECUTE ON FUNCTION drop_user(text) TO admin;

COMMENT ON FUNCTION drop_user(text) IS 'Drop a human or application user.  Intended for cleanup (either after team changes or mistakes in role setup).
Roles (= users) that own database objects cannot be dropped.';


CREATE OR REPLACE FUNCTION drop_role(username text)
 RETURNS void
 LANGUAGE sql
AS $function$
SELECT user_management.drop_user(username);
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION drop_role(text) FROM public;
GRANT EXECUTE ON FUNCTION drop_role(text) TO admin;

COMMENT ON FUNCTION drop_role(text) IS 'Drop a human or application user.  Intended for cleanup (either after team changes or mistakes in role setup).
Roles (= users) that own database objects cannot be dropped.';


CREATE OR REPLACE FUNCTION terminate_backend(pid integer)
 RETURNS boolean
 LANGUAGE sql
AS $function$
SELECT pg_terminate_backend(pid);
$function$
SECURITY DEFINER SET search_path to 'pg_catalog';

REVOKE ALL ON FUNCTION terminate_backend(integer) FROM public;
GRANT EXECUTE ON FUNCTION terminate_backend(integer) TO admin;

COMMENT ON FUNCTION terminate_backend(integer) IS 'When there is a process causing harm, you can kill it using this function.  Get the pid from pg_stat_activity
(be careful to match the user name (usename) and the query, in order not to kill innocent kittens) and pass it to terminate_backend()';

-- to allow checking what to kill:
GRANT SELECT ON pg_stat_activity TO admin;


RESET search_path;

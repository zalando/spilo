#!/bin/bash

set -ex

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

readonly container=$1
readonly output_file=$2


function generate_data() {
    docker_exec "$container" $'cd $PGDATA;
        rm -rf locales_test; mkdir locales_test; cd locales_test;
        /bin/bash "/home/postgres/tests/helper_script.sh";
        truncate -s -1 _base-characters \
        && psql -c "insert into chars select regexp_split_to_table(pg_read_file(\'locales_test/_base-characters\')::text, E\'\\n\');"
    '
}

# Create an auxiliary table
docker_exec "$container" "psql -d postgres -c 'drop table if exists chars; create table chars(chr text);'"

# Insert data into the auxiliary table
generate_data

# Write sorted data to an output file
docker_exec "$container" "psql -c '\copy (select * from chars order by 1) to ${output_file}'"

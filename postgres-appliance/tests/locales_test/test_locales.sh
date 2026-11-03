#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

# shellcheck disable=SC1091
source ../test_utils.sh

TEST_CONTAINER_NAME='spilo-test'
# pairs of (image, USE_OLD_LOCALES) which must produce the same collation order:
# - Ubuntu 18.04 locales in the old (22.04-based) and in the new image
# - default locales of the old (22.04-based) image and Ubuntu 22.04 locales in the new image
TEST_IMAGE=(
    'ghcr.io/zalando/spilo-18:4.1-p2'
    'spilo'
    'ghcr.io/zalando/spilo-18:4.1-p2'
    'spilo'
)
TEST_LOCALES=(
    'true'
    'true'
    'false'
    '22'
)

function main() {
    for i in 0 1 2 3; do
        rm_container "$TEST_CONTAINER_NAME"
        docker run --rm -d --privileged \
                --name "$TEST_CONTAINER_NAME" \
                -v "$PWD":/home/postgres/tests \
                -e SPILO_PROVIDER=local -e USE_OLD_LOCALES="${TEST_LOCALES[$i]}" \
                "${TEST_IMAGE[$i]}"
        attempts=0
        while ! docker exec -i spilo-test su postgres -c "pg_isready"; do
            if [[ "$attempts" -ge 15 ]]; then
                docker logs "$TEST_CONTAINER_NAME"
                exit 1
            fi
            ((attempts++))
            sleep 1
        done
        /bin/bash -x ./generate_data.sh "$TEST_CONTAINER_NAME" "/home/postgres/output${i}.txt"
        docker exec "$TEST_CONTAINER_NAME" mv "/home/postgres/output${i}.txt" "/home/postgres/tests"
    done

    diff -u output0.txt output1.txt > /dev/null || { echo "Outputs with Ubuntu 18.04 locales are different!"; exit 1; }
    diff -u output2.txt output3.txt > /dev/null || { echo "Outputs with Ubuntu 22.04 locales are different!"; exit 1; }
    rm -f output0.txt output1.txt output2.txt output3.txt
}

trap 'rm_container $TEST_CONTAINER_NAME' QUIT TERM EXIT

main

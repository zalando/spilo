#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

# shellcheck disable=SC1091
source ../test_utils.sh

TEST_CONTAINER_NAME='spilo-test'
TEST_IMAGE=(
    'registry.opensource.zalan.do/acid/spilo-cdp-14'
    'spilo'
)

function main() {
    for i in 0 1; do
        rm_container "$TEST_CONTAINER_NAME"
        docker run --rm -d --privileged \
                --name "$TEST_CONTAINER_NAME" \
                -v "$PWD":/home/postgres/tests \
                -e SPILO_PROVIDER=local -e USE_OLD_LOCALES=true \
                "${TEST_IMAGE[$i]}"  #USE_OLD_LOCALES takes no effect for cdp-14
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

    diff -u output0.txt output1.txt > /dev/null || (echo "Outputs are different!" && exit 1)
    rm -f output0.txt output1.txt
}

trap 'rm_container $TEST_CONTAINER_NAME' QUIT TERM EXIT

main

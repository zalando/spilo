#!/bin/bash

while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag )
            build_args+=("$1" "$2-build")
            final_args+=("$1" "$2")
            IMGNAME="$2"
            shift
            ;;
        -f|--file )
            final_args+=("$1" "$2")
            shift
            ;;
        --build-arg )
            build_args+=("$1" "$2")
            shift
            ;;
        * )
            build_args+=("$1")
            final_args+=("$1")
            ;;
    esac
    shift
done

readonly REV=$(git rev-parse HEAD)
readonly URL=$(git config --get remote.origin.url)
readonly STATUS=$(git status --porcelain)
readonly GITAUTHOR=$(git show -s --format="%aN <%aE>" "$REV")

cat > scm-source.json <<__EOT__
{
    "url": "git:$URL",
    "revision": "$REV",
    "author": "$GITAUTHOR",
    "status": "$STATUS"
}
__EOT__

function run_or_fail() {
    "$@"
    local EXITCODE=$?
    if  [[ $EXITCODE != 0 ]]; then
        echo "'$@' failed with exitcode $EXITCODE"
        exit $EXITCODE
    fi
}

readonly OLD_BUILD_ID=$(docker images -q $IMGNAME-build)

function squash_new_image() {
    local NEW_BUILD_ID=$(docker images -q $IMGNAME-build)
    local TAG_OF=$(docker images --format "{{.ID}} {{.Repository}}:{{.Tag}}" \
            | grep "^$NEW_BUILD_ID " | grep -v "^$NEW_BUILD_ID $IMGNAME-build" \
            | awk '{print $2; exit 0}')

    # new "-build" image has the same id as already exiting one
    [[ ! -z $TAG_OF ]] && docker tag ${TAG_OF%-build}-squashed $IMGNAME-squashed && return 0

    [[ "$OLD_BUILD_ID" != "$NEW_BUILD_ID" || -z "$(docker images -q $IMGNAME-squashed)" ]] \
            && run_or_fail docker-squash -t $IMGNAME-squashed $IMGNAME-build
}

run_or_fail docker build "${build_args[@]}" -f Dockerfile.build

squash_new_image

run_or_fail docker tag $IMGNAME-squashed spilo:squashed

run_or_fail docker build "${final_args[@]}"

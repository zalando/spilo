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

SQUASHED=spilo:squashed
DOCKERCMD="docker build"

function usage()
{
    cat <<__EOF__
Usage: $0 [DOCKER ARGUMENTS]

__EOF__
}

REV=$(git rev-parse HEAD)
URL=$(git config --get remote.origin.url)
STATUS=$(git status --porcelain)
GITAUTHOR=$(git show -s --format="%aN <%aE>" "$REV")

cat > scm-source.json <<__EOT__
{
    "url": "git:$URL",
    "revision": "$REV",
    "author": "$GITAUTHOR",
    "status": "$STATUS"
}
__EOT__

function run_or_fail() {
    $@
    EXITCODE=$?
    if  [[ $EXITCODE != 0 ]]; then
        echo "'$@' failed with exitcode $EXITCODE"
        exit $EXITCODE
    fi
}

BUILD_ID=$(docker images -q $IMGNAME-build)
run_or_fail ${DOCKERCMD} ${build_args[@]} -f Dockerfile.build

[[ "$(docker images -q $IMGNAME-build)" != "$BUILD_ID" || -z "$(docker images -q $SQUASHED)" ]] \
    && run_or_fail docker-squash -t $SQUASHED $IMGNAME-build

run_or_fail ${DOCKERCMD} ${final_args[@]}

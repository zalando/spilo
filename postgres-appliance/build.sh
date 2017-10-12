#!/bin/bash

BUILDIMG=minispilo
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

BUILD_ID=$(docker images -q $BUILDIMG:build)
run_or_fail ${DOCKERCMD} -t $BUILDIMG:build . -f Dockerfile.build

[[ "$(docker images -q $BUILDIMG:build)" != "$BUILD_ID" || -z "$(docker images -q $BUILDIMG:squashed)" ]] \
    && run_or_fail docker-squash -t $BUILDIMG:squashed $BUILDIMG:build

run_or_fail ${DOCKERCMD} $@

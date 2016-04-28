#!/bin/bash

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
    "url": "$URL",
    "revision": "$REV",
    "author": "$GITAUTHOR",
    "status": "$STATUS"
}
__EOT__

${DOCKERCMD} $@
EXITCODE=$?

if [[ $EXITCODE != 0 ]]
then
    echo "Docker build failed, exitcode is ${EXITCODE}"
    exit ${EXITCODE}
fi

#!/bin/bash

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

exec docker build "$@"

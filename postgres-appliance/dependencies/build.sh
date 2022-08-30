#!/bin/bash

if ! docker info &> /dev/null; then
    if podman info &> /dev/null; then
        alias docker=podman
        shopt -s expand_aliases
    else
        echo "docker/podman: command not found"
        exit 1
    fi
fi

set -ex

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

readonly IMGTAG=spilo:dependencies

docker build -t $IMGTAG .

rm -f debs/*_"$(docker run --rm $IMGTAG dpkg --print-architecture)".deb

docker run --rm $IMGTAG tar -C /debs -c .| tar -C debs -x

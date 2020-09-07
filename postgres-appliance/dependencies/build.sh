#!/bin/bash

set -ex

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

readonly IMGTAG=spilo:dependencies

docker build -t $IMGTAG .

rm -f debs/*

docker run --rm $IMGTAG tar -C /debs -c .| tar -C debs -x

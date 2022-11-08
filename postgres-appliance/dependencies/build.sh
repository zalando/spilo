#!/bin/bash

set -ex

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

readonly IMGTAG=spilo:dependencies

docker build -t $IMGTAG .

rm -f debs/*_"$(docker run --rm $IMGTAG dpkg --print-architecture)".deb

docker run --rm $IMGTAG tar -C /debs -c .| tar -C debs -x

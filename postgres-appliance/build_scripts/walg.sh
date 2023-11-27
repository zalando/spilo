#!/bin/bash

## ------------
## Build wal-g
## ------------

set -ex

# should exist when $DEMO=TRUE to avoid 'COPY --from=dependencies-builder /builddeps/wal-g ...' failure

if [ "$DEMO" = "true" ]; then
    mkdir /builddeps/wal-g
    exit 0
fi

export DEBIAN_FRONTEND=noninteractive
MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)"
export MAKEFLAGS

echo -e 'APT::Install-Recommends "0";\nAPT::Install-Suggests "0";' > /etc/apt/apt.conf.d/01norecommend

apt-get update
apt-get install -y curl ca-certificates

apt-get install -y software-properties-common gpg-agent
add-apt-repository ppa:longsleep/golang-backports
apt-get update
apt-get install -y golang-go liblzo2-dev brotli libsodium-dev git make cmake gcc libc-dev jq
go version

# Build wal-g
walg_repo=$(jq -r ".\"wal-g\".repo" /builddeps/pinned_versions.json)
walg_version=$(jq -r ".\"wal-g\".version" /builddeps/pinned_versions.json)
git clone -b "$walg_version" --recurse-submodules "${walg_repo}.git"
cd /wal-g
go get -v -t -d ./...
go mod vendor

bash link_brotli.sh
bash link_libsodium.sh

export USE_LIBSODIUM=1
export USE_LZO=1
make pg_build

mkdir /builddeps/wal-g

cp /wal-g/main/pg/wal-g /builddeps/wal-g/

#!/bin/bash

## ------------------
## Dependencies magic
## ------------------

set -ex

export DEBIAN_FRONTEND=noninteractive
MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)"
export MAKEFLAGS
ARCH="$(dpkg --print-architecture)"

echo -e 'APT::Install-Recommends "0";\nAPT::Install-Suggests "0";' > /etc/apt/apt.conf.d/01norecommend

apt-get update
apt-get install -y curl ca-certificates

# Build wal-g from source for a non-amd64 arch
if [ "$ARCH" != "amd64" ]; then
    apt-get install -y software-properties-common gpg-agent
    add-apt-repository ppa:longsleep/golang-backports
    apt-get update
    apt-get install -y golang-go liblzo2-dev brotli libsodium-dev git make cmake gcc libc-dev
    go version

    git clone -b "$WALG_VERSION" --recurse-submodules https://github.com/wal-g/wal-g.git
    cd /wal-g
    go get -v -t -d ./...
    go mod vendor

    bash link_brotli.sh
    bash link_libsodium.sh

    if grep -q DISTRIB_RELEASE=18.04 /etc/lsb-release; then export CGO_LDFLAGS=-no-pie; fi

    export USE_LIBSODIUM=1
    export USE_LZO=1
    make pg_build
fi

# We want to remove all libgdal20 debs except one that is for current architecture.
printf "shopt -s extglob\nrm /builddeps/!(*_%s.deb)" "$ARCH" | bash -s

mkdir /builddeps/wal-g

if [ "$DEMO" = "true" ]; then
    rm -f /builddeps/*.deb
    # Create an empty dummy deb file to prevent the `COPY --from=dependencies-builder /builddeps/*.deb /builddeps/` step from failing
    touch /builddeps/dummy.deb
elif [ "$ARCH" != "amd64" ]; then
    cp /wal-g/main/pg/wal-g /builddeps/wal-g/
else
    # In order to speed up amd64 build we just download the binary from GH
    DISTRIB_RELEASE=$(sed -n 's/DISTRIB_RELEASE=//p' /etc/lsb-release)
    curl -sL "https://github.com/wal-g/wal-g/releases/download/$WALG_VERSION/wal-g-pg-ubuntu-$DISTRIB_RELEASE-amd64.tar.gz" \
                | tar -C /builddeps/wal-g -xz
    mv "/builddeps/wal-g/wal-g-pg-ubuntu-$DISTRIB_RELEASE-amd64" /builddeps/wal-g/wal-g
fi

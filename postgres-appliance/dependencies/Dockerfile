FROM ubuntu:22.04

LABEL maintainer="Alexander Kukushkin <alexander.kukushkin@zalando.de>"

ENV SOURCES="gdal"
ENV PACKAGES="libgdal30"

RUN export DEBIAN_FRONTEND=noninteractive \
    && echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend \
    && echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend \
    && sed -i 's/^# deb-src/deb-src/' /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y devscripts equivs \
    && mk-build-deps $SOURCES \
    && dpkg -i *-build-deps*.deb || apt-get -y -f install

ADD patches /builddir/patches
ADD debs /debs

RUN export DEBIAN_FRONTEND=noninteractive \
    && set -ex \
    && apt-get update \
    && apt-get upgrade -y \
    && need_rebuild=false \
    && for pkg in $PACKAGES; do \
        new_package=$(apt-cache show $pkg | awk -F/ '/Filename: / {print $NF}'| sort -rV | head -n 1) \
        && if [ ! -f /debs/$new_package ]; then \
            need_rebuild=true \
            && break; \
        fi; \
    done \
    && if [ "$need_rebuild" = "true" ]; then \
        cd /builddir \
        && apt-get source $SOURCES \
        && export MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)" \
        && for pkg in $SOURCES; do \
            cd $(ls -d /builddir/$pkg-*) \
            && patch -p0 < /builddir/patches/$pkg.patch \
            && debuild -b -uc -us; \
        done \

        && rm -f /debs/* \
        && for pkg in $PACKAGES; do \
            cp /builddir/${pkg}_*_$(dpkg --print-architecture).deb /debs; \
        done; \
    fi

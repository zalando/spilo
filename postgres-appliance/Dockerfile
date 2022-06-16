ARG BASE_IMAGE=ubuntu:18.04
ARG PGVERSION=14
ARG TIMESCALEDB="1.7.5 2.3.1 2.7.0"
ARG DEMO=false
ARG COMPRESS=false

FROM $BASE_IMAGE as dependencies-builder

ENV WALG_VERSION=v2.0.0
# We want to build ourself non-amd64 wal-g in one of the build steps
RUN export DEBIAN_FRONTEND=noninteractive \
    && echo 'APT::Install-Recommends "0";\nAPT::Install-Suggests "0";' > /etc/apt/apt.conf.d/01norecommend \
    && apt-get update \
    && apt-get install -y curl ca-certificates \
    && if [ "$(dpkg --print-architecture)" != "amd64" ]; then \
        apt-get install -y software-properties-common \
        && add-apt-repository ppa:longsleep/golang-backports \
        && apt-get update \
        && apt-get install -y golang-go liblzo2-dev brotli libsodium-dev git make cmake gcc \
        && go version; \
    fi

RUN if [ "$(dpkg --print-architecture)" != "amd64" ]; then git clone -b $WALG_VERSION --recurse-submodules https://github.com/wal-g/wal-g.git; fi
WORKDIR /wal-g
RUN if [ "$(dpkg --print-architecture)" != "amd64" ]; then go get -v -t -d ./... && go mod vendor; fi
RUN if [ "$(dpkg --print-architecture)" != "amd64" ]; then export MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)" && bash link_brotli.sh; fi
RUN if [ "$(dpkg --print-architecture)" != "amd64" ]; then export MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)" && bash link_libsodium.sh; fi
RUN if [ "$(dpkg --print-architecture)" != "amd64" ]; then \
        if grep -q DISTRIB_RELEASE=18.04 /etc/lsb-release; then export CGO_LDFLAGS=-no-pie; fi \
        && export USE_LIBSODIUM=1 \
        && export USE_LZO=1 \
        && export MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)" \
        && make pg_build; \
    fi

COPY  dependencies/debs /builddeps/
# We want to remove all libgdal20 debs except one that is for current architecture.
RUN echo "shopt -s extglob\nrm /builddeps/!(*_$(dpkg --print-architecture).deb)" | bash -s
ARG DEMO
RUN mkdir /builddeps/wal-g \
    && if [ "$DEMO" = "true" ]; then \
        rm -f /builddeps/*.deb \
        # Create an empty dummy deb file to prevent the `COPY --from=dependencies-builder /builddeps/*.deb /builddeps/` step from failing
        && touch /builddeps/dummy.deb; \
    elif [ "$(dpkg --print-architecture)" != "amd64" ]; then \
        cp /wal-g/main/pg/wal-g /builddeps/wal-g/; \
    else \
        # In order to speed up amd64 build we just download the binary from GH
        DISTRIB_RELEASE=$(sed -n 's/DISTRIB_RELEASE=//p' /etc/lsb-release) \
        && curl -sL https://github.com/wal-g/wal-g/releases/download/$WALG_VERSION/wal-g-pg-ubuntu-$DISTRIB_RELEASE-amd64.tar.gz \
                | tar -C /builddeps/wal-g -xz \
        && mv /builddeps/wal-g/wal-g-pg-ubuntu-$DISTRIB_RELEASE-amd64 /builddeps/wal-g/wal-g; \
    fi


FROM $BASE_IMAGE as builder-false

ARG DEMO
ARG ADDITIONAL_LOCALES=

RUN export DEBIAN_FRONTEND=noninteractive \
    && echo 'APT::Install-Recommends "0";\nAPT::Install-Suggests "0";' > /etc/apt/apt.conf.d/01norecommend \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y curl ca-certificates less locales jq vim-tiny gnupg1 cron runit dumb-init libcap2-bin rsync sysstat \
    && ln -s chpst /usr/bin/envdir \
    # Make it possible to use the following utilities without root (if container runs without "no-new-privileges:true")
    && setcap 'cap_sys_nice+ep' /usr/bin/chrt \
    && setcap 'cap_sys_nice+ep' /usr/bin/renice \
    # Disable unwanted cron jobs
    && rm -fr /etc/cron.??* \
    && truncate --size 0 /etc/crontab \
\
    && if [ "$DEMO" != "true" ]; then \
        # Required for wal-e
        apt-get install -y pv lzop \
        # install etcdctl
        && ETCDVERSION=3.3.27 \
        && curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-$(dpkg --print-architecture).tar.gz \
                | tar xz -C /bin --strip=1 --wildcards --no-anchored --no-same-owner etcdctl etcd; \
    fi \
\
    # Cleanup all locales but en_US.UTF-8 and optionally specified in ADDITIONAL_LOCALES arg
    && find /usr/share/i18n/charmaps/ -type f ! -name UTF-8.gz -delete \
    # Prepare find expression for locales
    && LOCALE_FIND_EXPR="-type f" \
    && for loc in en_US en_GB $ADDITIONAL_LOCALES "i18n*" iso14651_t1 iso14651_t1_common "translit_*"; do \
        LOCALE_FIND_EXPR="$LOCALE_FIND_EXPR ! -name $loc"; \
    done \
    && find /usr/share/i18n/locales/ $LOCALE_FIND_EXPR -delete \
\
    # Make sure we have the en_US.UTF-8 and all additional locales available
    && truncate --size 0 /usr/share/i18n/SUPPORTED \
    && for loc in en_US $ADDITIONAL_LOCALES; do \
        echo "$loc.UTF-8 UTF-8" >> /usr/share/i18n/SUPPORTED \
        && localedef -i $loc -c -f UTF-8 -A /usr/share/locale/locale.alias $loc.UTF-8; \
    done \
\
    # Add PGDG repositories
    && DISTRIB_CODENAME=$(sed -n 's/DISTRIB_CODENAME=//p' /etc/lsb-release) \
    && for t in deb deb-src; do \
        echo "$t http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" >> /etc/apt/sources.list.d/pgdg.list; \
    done \
    && curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
\
    # Clean up
    && apt-get purge -y libcap2-bin \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
            /var/cache/debconf/* \
            /usr/share/doc \
            /usr/share/man \
            /usr/share/locale/?? \
            /usr/share/locale/??_?? \
    && find /var/log -type f -exec truncate --size 0 {} \;

COPY cron_unprivileged.c dependencies/src /builddeps/
COPY --from=dependencies-builder /builddeps/*.deb /builddeps/

ARG PGVERSION
ARG TIMESCALEDB
ARG TIMESCALEDB_APACHE_ONLY=true
ARG DEMO
ARG COMPRESS
ARG PGOLDVERSIONS="9.6 10 11 12 13"
ARG WITH_PERL=false

ARG DEB_PG_SUPPORTED_VERSIONS="$PGOLDVERSIONS $PGVERSION"

# Install PostgreSQL, extensions and contribs
ENV POSTGIS_VERSION=3.2 \
    POSTGIS_LEGACY=3.2 \
    BG_MON_COMMIT=5d5002836118e4baf4b356f859566c56433e811f \
    PG_AUTH_MON_COMMIT=437435b4e2de32a820e86973f6934ec849a768e0 \
    PG_MON_COMMIT=54fbdcc3cfe7e2a626bd96dda644d9a0c6866b58 \
    SET_USER=REL3_0_0 \
    PLPROFILER=REL4_1 \
    PAM_OAUTH2=v1.0.1 \
    PLANTUNER_COMMIT=800d81bc85da64ff3ef66e12aed1d4e1e54fc006 \
    PG_PERMISSIONS_COMMIT=314b9359e3d77c0b2ef7dbbde97fa4be80e31925 \
    PG_TM_AUX_COMMIT=6c012d38a4c1b0ba4a36952d60b0ce3a22ac9c3d

RUN export DEBIAN_FRONTEND=noninteractive \
    && export MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)" \
    && set -ex \
    && sed -i 's/^#\s*\(deb.*universe\)$/\1/g' /etc/apt/sources.list \
    && apt-get update \
    && cd /builddeps \
\
    && BUILD_PACKAGES="devscripts equivs build-essential fakeroot debhelper git gcc libc6-dev make cmake libevent-dev libbrotli-dev libssl-dev libkrb5-dev" \
    && if [ "$DEMO" = "true" ]; then \
        export DEB_PG_SUPPORTED_VERSIONS="$PGVERSION" \
        && WITH_PERL=false \
        && rm -f *.deb \
        && apt-get install -y $BUILD_PACKAGES; \
    else \
        BUILD_PACKAGES="$BUILD_PACKAGES zlib1g-dev libpam0g-dev libcurl4-openssl-dev libicu-dev python libc-ares-dev pandoc pkg-config" \
        && apt-get install -y $BUILD_PACKAGES libcurl4 \
\
        # install pam_oauth2.so
        && git clone -b $PAM_OAUTH2 --recurse-submodules https://github.com/CyberDem0n/pam-oauth2.git \
        && make -C pam-oauth2 install \
\
        # prepare 3rd sources
        && git clone -b $PLPROFILER https://github.com/bigsql/plprofiler.git \
        && tar -xzf plantuner-${PLANTUNER_COMMIT}.tar.gz \
        && curl -sL https://github.com/sdudoladov/pg_mon/archive/$PG_MON_COMMIT.tar.gz | tar xz \
\
        && for p in python3-keyring python3-docutils ieee-data; do \
            version=$(apt-cache show $p | sed -n 's/^Version: //p' | sort -rV | head -n 1) \
            && echo "Section: misc\nPriority: optional\nStandards-Version: 3.9.8\nPackage: $p\nVersion: $version\nDescription: $p" > $p \
            && equivs-build $p; \
        done; \
    fi \
\
    && if [ "$WITH_PERL" != "true" ]; then \
        version=$(apt-cache show perl | sed -n 's/^Version: //p' | sort -rV | head -n 1) \
        && echo "Section: misc\nPriority: optional\nStandards-Version: 3.9.8\nPackage: perl\nSection:perl\nMulti-Arch: allowed\nReplaces: perl-base\nVersion: $version\nDescription: perl" > perl \
        && equivs-build perl; \
    fi \
\
    && if [ "$WITH_PERL" != "true" ] || [ "$DEMO" != "true" ]; then dpkg -i *.deb || apt-get -y -f install; fi \
\
    && curl -sL https://github.com/CyberDem0n/bg_mon/archive/$BG_MON_COMMIT.tar.gz | tar xz \
    && curl -sL https://github.com/sdudoladov/pg_auth_mon/archive/$PG_AUTH_MON_COMMIT.tar.gz | tar xz \
    && curl -sL https://github.com/cybertec-postgresql/pg_permissions/archive/$PG_PERMISSIONS_COMMIT.tar.gz | tar xz \
    && curl -sL https://github.com/x4m/pg_tm_aux/archive/$PG_TM_AUX_COMMIT.tar.gz | tar xz \
    && git clone -b $SET_USER https://github.com/pgaudit/set_user.git \
    && git clone https://github.com/timescale/timescaledb.git \
\
    && apt-get install -y postgresql-common libevent-2.1 libevent-pthreads-2.1 brotli libbrotli1 python3.6 python3-psycopg2 \
\
    # forbid creation of a main cluster when package is installed
    && sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf \
\
    && for version in $DEB_PG_SUPPORTED_VERSIONS; do \
            sed -i "s/ main.*$/ main $version/g" /etc/apt/sources.list.d/pgdg.list \
            && apt-get update \
\
            && if [ "$DEMO" != "true" ]; then \
                EXTRAS="postgresql-pltcl-${version} \
                        postgresql-${version}-dirtyread \
                        postgresql-${version}-extra-window-functions \
                        postgresql-${version}-first-last-agg \
                        postgresql-${version}-hll \
                        postgresql-${version}-hypopg \
                        postgresql-${version}-pgaudit \
                        postgresql-${version}-pg-checksums \
                        postgresql-${version}-pgl-ddl-deploy \
                        postgresql-${version}-pglogical \
                        postgresql-${version}-pglogical-ticker \
                        postgresql-${version}-pgq-node \
                        postgresql-${version}-pldebugger \
                        postgresql-${version}-pllua \
                        postgresql-${version}-plpgsql-check \
                        postgresql-${version}-plproxy \
                        postgresql-${version}-postgis-${POSTGIS_VERSION%.*} \
                        postgresql-${version}-postgis-${POSTGIS_VERSION%.*}-scripts \
                        postgresql-${version}-repack \
                        postgresql-${version}-wal2json" \
                && if [ "$WITH_PERL" = "true" ]; then \
                    EXTRAS="$EXTRAS postgresql-plperl-${version}"; \
                fi \
                && if [ ${version%.*} -ge 10 ]; then \
                    EXTRAS="$EXTRAS postgresql-${version}-decoderbufs"; \
                fi \
                && if [ ${version%.*} -lt 11 ]; then \
                    EXTRAS="$EXTRAS postgresql-${version}-amcheck"; \
                fi; \
            fi \
\
            # Install PostgreSQL binaries, contrib, plproxy and multiple pl's
            && apt-get install --allow-downgrades -y postgresql-contrib-${version} \
                    postgresql-plpython3-${version} postgresql-server-dev-${version} \
                    postgresql-${version}-cron postgresql-${version}-pgq3 \
                    postgresql-${version}-pg-stat-kcache $EXTRAS \
\
            # Install 3rd party stuff
            && cd timescaledb \
            && for v in $TIMESCALEDB; do \
                git checkout $v \
                && sed -i "s/VERSION 3.11/VERSION 3.10/" CMakeLists.txt \
                && if BUILD_FORCE_REMOVE=true ./bootstrap -DREGRESS_CHECKS=OFF -DWARNINGS_AS_ERRORS=OFF \
                    -DTAP_CHECKS=OFF -DPG_CONFIG=/usr/lib/postgresql/$version/bin/pg_config \
                    -DAPACHE_ONLY=$TIMESCALEDB_APACHE_ONLY -DSEND_TELEMETRY_DEFAULT=NO; then \
                        make -C build install \
                        && strip /usr/lib/postgresql/$version/lib/timescaledb*.so; \
                fi \
                && git reset --hard \
                && git clean -f -d; \
            done \
            && cd .. \
\
            && if [ "$DEMO" != "true" ]; then \
                EXTRA_EXTENSIONS="plantuner-${PLANTUNER_COMMIT} plprofiler" \
                && if [ ${version%.*} -ge 10 ]; then \
                     EXTRA_EXTENSIONS="$EXTRA_EXTENSIONS pg_mon-${PG_MON_COMMIT}"; \
                fi; \
            else \
                EXTRA_EXTENSIONS=""; \
            fi \
\
            && for n in bg_mon-${BG_MON_COMMIT} pg_auth_mon-${PG_AUTH_MON_COMMIT} set_user pg_permissions-${PG_PERMISSIONS_COMMIT} pg_tm_aux-${PG_TM_AUX_COMMIT} $EXTRA_EXTENSIONS; do \
                make -C $n USE_PGXS=1 clean install-strip; \
            done; \
    done \
\
    && apt-get install -y skytools3-ticker pgbouncer \
\
    && sed -i "s/ main.*$/ main/g" /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y postgresql postgresql-server-dev-all postgresql-all libpq-dev \
    && for version in $DEB_PG_SUPPORTED_VERSIONS; do \
        apt-get install -y postgresql-server-dev-${version}; \
    done \
\
    && if [ "$DEMO" != "true" ]; then \
        for version in $DEB_PG_SUPPORTED_VERSIONS; do \
            # due to dependency issues partman has to be installed separately
            apt-get install -y postgresql-${version}-partman \
            # create postgis symlinks to make it possible to perform update
            && ln -s postgis-${POSTGIS_VERSION%.*}.so \
                /usr/lib/postgresql/${version}/lib/postgis-2.5.so; \
        done; \
    fi \
\
    # build and install missing packages
    && for pkg in pgextwlist; do \
        apt-get source postgresql-13-${pkg} \
        && cd $(ls -d *${pkg%?}*-*/) \
        && if [ -f ../$pkg.patch ]; then patch -p1 < ../$pkg.patch; fi \
        && if [ "$pkg" = "pgextwlist" ]; then \
            sed -i '/postgresql-all/d' debian/control.in \
            # make it possible to use it from shared_preload_libraries
            && perl -ne 'print unless /PG_TRY/ .. /PG_CATCH/' pgextwlist.c > pgextwlist.c.f \
            && egrep -v '(PG_END_TRY|EmitWarningsOnPlaceholders)' pgextwlist.c.f > pgextwlist.c; \
        fi \
        && pg_buildext updatecontrol \
        && DEB_BUILD_OPTIONS=nocheck debuild -b -uc -us \
        && cd .. \
        && for version in $DEB_PG_SUPPORTED_VERSIONS; do \
            for deb in postgresql-${version}-${pkg}_*.deb; do \
                if [ -f $deb ]; then dpkg -i $deb; fi; \
            done; \
        done; \
    done \
\
    # make it possible for cron to work without root
    && gcc -s -shared -fPIC -o /usr/local/lib/cron_unprivileged.so cron_unprivileged.c \
\
    # Remove unnecessary packages
    && apt-get purge -y ${BUILD_PACKAGES} postgresql postgresql-all postgresql-server-dev-* libpq-dev=* libmagic1 bsdmainutils \
    && apt-get autoremove -y \
    && apt-get clean \
    && dpkg -l | grep '^rc' | awk '{print $2}' | xargs apt-get purge -y \
\
    # Try to minimize size by creating symlinks instead of duplicate files
    && if [ "$DEMO" != "true" ]; then \
        cd /usr/lib/postgresql/$PGVERSION/bin \
        && for u in clusterdb pg_archivecleanup pg_basebackup pg_isready pg_recvlogical pg_test_fsync pg_test_timing pgbench psql reindexdb vacuumdb vacuumlo *.py; do \
            for v in /usr/lib/postgresql/*; do \
                if [ "$v" != "/usr/lib/postgresql/$PGVERSION" ] && [ -f "$v/bin/$u" ]; then \
                    rm $v/bin/$u \
                    && ln -s ../../$PGVERSION/bin/$u $v/bin/$u; \
                fi; \
            done; \
        done \
        && set +x \
        && for v1 in $(ls -1d /usr/share/postgresql/* | sort -Vr); do \
            # relink files with the same content
            cd $v1/extension \
            && for orig in $(ls -1 *.sql | grep -v -- '--'); do \
                for f in ${orig%.sql}--*.sql; do \
                    if [ ! -L $f ] && diff $orig $f > /dev/null; then \
                        echo "creating symlink $f -> $orig" \
                        && rm $f && ln -s $orig $f; \
                    fi; \
                done; \
            done \
            && for e in pgq pgq_node plproxy address_standardizer address_standardizer_data_us; do \
                orig=$(basename "$(find -maxdepth 1 -type f -name "$e--*--*.sql" | head -n1)") \
                && if [ "x$orig" != "x" ]; then \
                    for f in $e--*--*.sql; do \
                        if [ "$f" != "$orig" ] && [ ! -L $f ] && diff $f $orig > /dev/null; then \
                            echo "creating symlink $f -> $orig" \
                            && rm $f && ln -s $orig $f; \
                        fi; \
                    done; \
                fi; \
            done \
            # relink files with the same name and content across different major versions
            && started=0 \
            && for v2 in $(ls -1d /usr/share/postgresql/* | sort -Vr); do \
                if [ $v1 = $v2 ]; then \
                    started=1; \
                elif [ $started = 1 ]; then \
                    for d1 in extension contrib contrib/postgis-$POSTGIS_VERSION; do \
                        cd $v1/$d1 \
                        && d2="$d1" \
                        && d1="../../${v1##*/}/$d1" \
                        && if [ "${d2%-*}" = "contrib/postgis" ]; then \
                            if  [ "${v2##*/}" = "9.6" ]; then d2="${d2%-*}-$POSTGIS_LEGACY"; fi \
                            && d1="../$d1"; \
                        fi \
                        && d2="$v2/$d2" \
                        && for f in *.html *.sql *.control *.pl; do \
                            if [ -f $d2/$f ] && [ ! -L $d2/$f ] && diff $d2/$f $f > /dev/null; then \
                                echo "creating symlink $d2/$f -> $d1/$f" \
                                && rm $d2/$f && ln -s $d1/$f $d2/$f; \
                            fi; \
                        done; \
                    done; \
                fi; \
            done; \
        done \
        && set -x; \
    fi \
\
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
            /var/cache/debconf/* \
            /builddeps \
            /usr/share/doc \
            /usr/share/man \
            /usr/share/info \
            /usr/share/locale/?? \
            /usr/share/locale/??_?? \
            /usr/share/postgresql/*/man \
            /etc/pgbouncer/* \
            /usr/lib/postgresql/*/bin/createdb \
            /usr/lib/postgresql/*/bin/createlang \
            /usr/lib/postgresql/*/bin/createuser \
            /usr/lib/postgresql/*/bin/dropdb \
            /usr/lib/postgresql/*/bin/droplang \
            /usr/lib/postgresql/*/bin/dropuser \
            /usr/lib/postgresql/*/bin/pg_standby \
            /usr/lib/postgresql/*/bin/pltcl_* \
    && find /var/log -type f -exec truncate --size 0 {} \;

# Install wal-g
COPY --from=dependencies-builder /builddeps/wal-g /usr/local/bin/

# Install patroni and wal-e
ENV PATRONIVERSION=2.1.4
ENV WALE_VERSION=1.1.1
RUN export DEBIAN_FRONTEND=noninteractive \
    && set -ex \
    && BUILD_PACKAGES="python3-pip python3-wheel python3-dev git patchutils binutils" \
    && apt-get update \
\
    # install most of the patroni dependencies from ubuntu packages
    && apt-cache depends patroni \
            | sed -n -e 's/.* Depends: \(python3-.\+\)$/\1/p' \
            | grep -Ev '^python3-(sphinx|etcd|consul|kazoo|kubernetes)' \
            | xargs apt-get install -y ${BUILD_PACKAGES} \
                        python3-pystache python3-requests \
\
    && pip3 install setuptools \
\
    && if [ "$DEMO" != "true" ]; then \
        EXTRAS=",etcd,consul,zookeeper,aws" \
        && apt-get install -y python3-etcd python3-consul python3-kazoo python3-meld3 \
                        python3-boto python3-gevent python3-greenlet python3-cachetools \
                        python3-rsa python3-pyasn1-modules python3-swiftclient python3-cffi \
\
        && find /usr/share/python-babel-localedata/locale-data -type f ! -name 'en_US*.dat' -delete \
\
        && pip3 install filechunkio wal-e[aws,google,swift]==$WALE_VERSION google-crc32c==1.1.2 'protobuf<4.21.0' \
                'git+https://github.com/zalando/pg_view.git@master#egg=pg-view' \
\
        # Non-exclusive backups
        && curl -sL https://github.com/CyberDem0n/wal-e/commit/dad4d53969b93c56f1eaa5243ffa8e9051fd7eb7.diff \
                | patch -d /usr/local/lib/python3.6/dist-packages/wal_e -p2 \
        # WALE_DISABLE_S3_SSE support
        && curl -sL https://github.com/CyberDem0n/wal-e/commit/0309317d33d252fcd968b3eb97313a9fdf022c65.diff \
                | patch -d /usr/local/lib/python3.6/dist-packages/wal_e -p2 \
        # Revert https://github.com/wal-e/wal-e/commit/485d834a18c9b0d97115d95f89e16bdc564e9a18, it affects S3 performance
        && curl -sL https://github.com/wal-e/wal-e/commit/485d834a18c9b0d97115d95f89e16bdc564e9a18.diff \
                | patch -d /usr/local/lib/python3.6/dist-packages/wal_e -Rp2 \
        # https://github.com/wal-e/wal-e/issues/318
        && sed -i 's/^\(    for i in range(0,\) num_retries):.*/\1 100):/g' \
                    /usr/lib/python3/dist-packages/boto/utils.py; \
    fi \
    && pip3 install patroni[kubernetes$EXTRAS]==$PATRONIVERSION \
\
    && for d in /usr/local/lib/python3.6 /usr/lib/python3; do \
        cd $d/dist-packages \
        && find . -type d -name tests | xargs rm -fr \
        && find . -type f -name 'test_*.py*' -delete; \
    done \
    && find . -type f -name 'unittest_*.py*' -delete \
    && find . -type f -name '*_test.py' -delete \
    && find . -type f -name '*_test.cpython*.pyc' -delete \
\
    # Clean up
    && apt-get purge -y ${BUILD_PACKAGES} \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
            /var/cache/debconf/* \
            /root/.cache \
            /usr/share/doc \
            /usr/share/man \
            /usr/share/locale/?? \
            /usr/share/locale/??_?? \
            /usr/share/info \
    && find /var/log -type f -exec truncate --size 0 {} \;

RUN set -ex \
    && if [ "$COMPRESS" = "true" ]; then \
        apt-get update \
        && apt-get install -y busybox xz-utils \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/* /var/cache/debconf/* /usr/share/doc /usr/share/man /etc/rc?.d /etc/systemd \
        && ln -snf busybox /bin/sh \
        && files="/bin/sh" \
        && arch=$(uname -m) \
        && darch=$(uname -m | sed 's/_/-/') \
        && libs="$(ldd $files | awk '{print $3;}' | grep '^/' | sort -u) /lib/ld-linux-$darch.so.* /lib/$arch-linux-gnu/ld-linux-$darch.so.* /lib/$arch-linux-gnu/libnsl.so.* /lib/$arch-linux-gnu/libnss_compat.so.*" \
        && (echo /var/run /var/spool $files $libs | tr ' ' '\n' && realpath $files $libs) | sort -u | sed 's/^\///' > /exclude \
        && find /etc/alternatives -xtype l -delete \
        && save_dirs="usr lib var bin sbin etc/ssl etc/init.d etc/alternatives etc/apt" \
        && XZ_OPT=-e9v tar -X /exclude -cpJf a.tar.xz $save_dirs \
        && rm -fr /usr/local/lib/python* \
        && /bin/busybox sh -c "(find $save_dirs -not -type d && cat /exclude /exclude && echo exclude) | sort | uniq -u | xargs /bin/busybox rm" \
        && /bin/busybox --install -s \
        && /bin/busybox sh -c "find $save_dirs -type d -depth -exec rmdir -p {} \; 2> /dev/null"; \
    fi

FROM scratch as builder-true
COPY --from=builder-false / /

FROM builder-${COMPRESS}

LABEL maintainer="Alexander Kukushkin <alexander.kukushkin@zalando.de>"

ARG PGVERSION
ARG TIMESCALEDB
ARG DEMO
ARG COMPRESS

EXPOSE 5432 8008 8080

ENV LC_ALL=en_US.utf-8 \
    PATH=$PATH:/usr/lib/postgresql/$PGVERSION/bin \
    PGHOME=/home/postgres \
    RW_DIR=/run \
    TIMESCALEDB=$TIMESCALEDB \
    DEMO=$DEMO

ENV WALE_ENV_DIR=$RW_DIR/etc/wal-e.d/env \
    LOG_ENV_DIR=$RW_DIR/etc/log.d/env \
    PGROOT=$PGHOME/pgdata/pgroot

ENV PGDATA=$PGROOT/data \
    PGLOG=$PGROOT/pg_log

WORKDIR $PGHOME

COPY motd /etc/
COPY runit /etc/service/
COPY pgq_ticker.ini $PGHOME/

RUN sed -i "s|/var/lib/postgresql.*|$PGHOME:/bin/bash|" /etc/passwd \
        && chown -R postgres:postgres $PGHOME $RW_DIR \
        && rm -fr /var/spool/cron /var/tmp \
        && mkdir -p /var/spool \
        && ln -s $RW_DIR/cron /var/spool/cron \
        && ln -s $RW_DIR/tmp /var/tmp \
        && for d in /etc/service/*; do \
            chmod 755 $d/* \
            && ln -s /run/supervise/$(basename $d) $d/supervise; \
        done \
        && ln -snf $RW_DIR/service /etc/service \
        && ln -s $RW_DIR/pam.d-postgresql /etc/pam.d/postgresql \
        && ln -s $RW_DIR/postgres.yml $PGHOME/postgres.yml \
        && ln -s $RW_DIR/.bash_history /root/.bash_history \
        && ln -s $RW_DIR/postgresql/.bash_history $PGHOME/.bash_history \
        && ln -s $RW_DIR/postgresql/.psql_history $PGHOME/.psql_history \
        && ln -s $RW_DIR/etc $PGHOME/etc \
        && for d in $PGHOME /root; do \
            d=$d/.config/patroni \
            && mkdir -p $d \
            && ln -s $PGHOME/postgres.yml $d/patronictl.yaml; \
        done \
        && sed -i 's/set compatible/set nocompatible/' /etc/vim/vimrc.tiny \
        && echo "PATH=\"$PATH\"" > /etc/environment \
        && for e in TERM=linux LC_ALL=C.UTF-8 LANG=C.UTF-8 EDITOR=editor; \
            do echo "export $e" >> /etc/bash.bashrc; \
        done \
        && ln -s /etc/skel/.bashrc $PGHOME/.bashrc \
        && echo "source /etc/motd" >> /root/.bashrc \
        # Allow users in the root group to access the following files and dirs
        && if [ "$COMPRESS" != "true" ]; then \
           chmod 664 /etc/passwd \
           && chmod o+r /etc/shadow \
           && chgrp -R 0 $PGHOME $RW_DIR \
           && chmod -R g=u $PGHOME $RW_DIR \
           && usermod -a -G root postgres; \
        fi

COPY scripts bootstrap major_upgrade /scripts/
COPY launch.sh /

CMD ["/bin/sh", "/launch.sh", "init"]

ARG PGVERSION=11

FROM ubuntu:18.04 as builder

ARG DEMO=false

RUN export DEBIAN_FRONTEND=noninteractive \
    && echo 'APT::Install-Recommends "0";\nAPT::Install-Suggests "0";' > /etc/apt/apt.conf.d/01norecommend \
    && apt-get update \
    && apt-get install -y curl ca-certificates less locales jq vim-tiny gnupg1 cron \
\
    && if [ "$DEMO" != "true" ]; then \
        # Required for wal-e
        apt-get install -y pv lzop \
        # install etcdctl
        && ETCDVERSION=2.3.8 \
        && curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz \
                | tar xz -C /bin --strip=1 --wildcards --no-anchored etcdctl etcd; \
    fi \
\
    # Cleanup all locales but en_US.UTF-8
    && find /usr/share/i18n/charmaps/ -type f ! -name UTF-8.gz -delete \
    && find /usr/share/i18n/locales/ -type f ! -name en_US ! -name en_GB ! -name i18n* ! -name iso14651_t1 ! -name iso14651_t1_common ! -name 'translit_*' -delete \
    && echo 'en_US.UTF-8 UTF-8' > /usr/share/i18n/SUPPORTED \
\
    ## Make sure we have a en_US.UTF-8 locale available
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \
\
    # Add PGDG repositories
    && DISTRIB_CODENAME=$(sed -n 's/DISTRIB_CODENAME=//p' /etc/lsb-release) \
    && for t in deb deb-src; do \
        echo "$t http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" >> /etc/apt/sources.list.d/pgdg.list; \
    done \
    && curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
\
    && apt-get update \
    && apt-get install -y postgresql-common \
\
    # forbid creation of a main cluster when package is installed
    && sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf \
\
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
            /var/cache/debconf/* \
            /usr/share/doc \
            /usr/share/man \
            /usr/share/locale/?? \
            /usr/share/locale/??_?? \
    && find /var/log -type f -exec truncate --size 0 {} \;

COPY dependencies/debs /builddeps

ARG PGVERSION
ARG PGOLDVERSIONS="9.3 9.4 9.5 9.6 10"
ARG WITH_PERL=false

# Install PostgreSQL, extensions and contribs
ENV POSTGIS_VERSION=2.5 \
    BG_MON_COMMIT=00311ac9b10351edde909584028339de8da4b0d1 \
    PG_AUTH_MON_COMMIT=a37987ad1465503ae805167fd1873270d5e9a010 \
    DECODERBUFS=v0.9.5.Final \
    SET_USER=REL1_6_2 \
    PLPGSQL_CHECK=v1.7.2 \
    PLPROFILER=REL3_5 \
    TIMESCALEDB=1.3.1 \
    PAM_OAUTH2=v1.0

RUN export DEBIAN_FRONTEND=noninteractive \
    && set -ex \
    && sed -i 's/^#\s*\(deb.*universe\)$/\1/g' /etc/apt/sources.list \
    && apt-get update \
    && cd /builddeps \
\
    && BUILD_PACKAGES="devscripts build-essential fakeroot debhelper git gcc libc6-dev make libevent-dev naturaldocs python" \
# pgq3: naturaldocs python
    && if [ "$DEMO" = "true" ]; then \
        PGOLDVERSIONS="" \
        && apt-get install -y $BUILD_PACKAGES; \
    else \
        BUILD_PACKAGES="$BUILD_PACKAGES equivs pgxnclient cmake libssl-dev zlib1g-dev libprotobuf-c-dev liblwgeom-dev libproj-dev libxslt1-dev libxml2-dev libpam0g-dev libkrb5-dev libedit-dev libselinux1-dev libcurl4-openssl-dev libicu-dev libc-ares-dev python-docutils pkg-config" \
# debezium-decoderbufs: libprotobuf-c-dev liblwgeom-dev libproj-dev
# pgbouncer: libc-ares-dev python-docutils pkg-config
# pg_rewind: libxslt1-dev libxml2-dev libpam0g-dev libkrb5-dev libedit-dev libselinux1-dev
        && apt-get install -y $BUILD_PACKAGES libprotobuf-c1 libcurl4 \
\
        && if [ "$WITH_PERL" != "true" ]; then \
            version=$(apt-cache show perl | sed -n 's/^Version: //p' | sort -rV | head -n 1) \
            && echo "Section: misc\nPriority: optional\nStandards-Version: 3.9.8\nPackage: perl\nSection:perl\nMulti-Arch: allowed\nReplaces: perl-base\nVersion: $version\nDescription: perl" > perl \
            && equivs-build perl; \
        fi \
\
        && for p in python3-keyring python3-docutils ieee-data; do \
            version=$(apt-cache show $p | sed -n 's/^Version: //p' | sort -rV | head -n 1) \
            && echo "Section: misc\nPriority: optional\nStandards-Version: 3.9.8\nPackage: $p\nVersion: $version\nDescription: $p" > $p \
            && equivs-build $p; \
        done \
        && dpkg -i *.deb || apt-get -y -f install \
\
        # install pam_oauth2.so
        && git clone -b $PAM_OAUTH2 --recurse-submodules https://github.com/CyberDem0n/pam-oauth2.git \
        && make -C pam-oauth2 install \
\
        # prepare 3rd sources
        && git clone -b $DECODERBUFS https://github.com/debezium/postgres-decoderbufs.git \
        && git clone -b $PLPROFILER https://github.com/pgcentral/plprofiler.git \
        && git clone -b $PLPGSQL_CHECK https://github.com/okbob/plpgsql_check.git \
        && git clone -b $TIMESCALEDB https://github.com/timescale/timescaledb.git \
        && git clone git://www.sigaev.ru/plantuner.git; \
    fi \
\
    && curl -sL https://github.com/CyberDem0n/bg_mon/archive/$BG_MON_COMMIT.tar.gz | tar xz \
    && curl -sL https://github.com/RafiaSabih/pg_auth_mon/archive/$PG_AUTH_MON_COMMIT.tar.gz | tar xz \
    && git clone -b $SET_USER https://github.com/pgaudit/set_user.git \
\
    && apt-get install -y libevent-2.1 libevent-pthreads-2.1 python3.6 python3-psycopg2 \
\
    && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            sed -i "s/ main.*$/ main $version/g" /etc/apt/sources.list.d/pgdg.list \
            && apt-get update \
\
            && if [ "$DEMO" != "true" ]; then \
                EXTRAS="postgresql-pltcl-${version} \
                        postgresql-${version}-hypopg \
                        postgresql-${version}-pgq3 \
                        postgresql-${version}-pldebugger \
                        postgresql-${version}-pllua \
                        postgresql-${version}-plproxy \
                        postgresql-${version}-repack" \
                && if [ "$WITH_PERL" = "true" ]; then \
                    EXTRAS="$EXTRAS postgresql-plperl-${version}"; \
                fi \
                && if [ $version != "9.3" ]; then \
                    EXTRAS="$EXTRAS \
                            postgresql-${version}-partman \
                            postgresql-${version}-pglogical \
                            postgresql-${version}-postgis-${POSTGIS_VERSION} \
                            postgresql-${version}-postgis-${POSTGIS_VERSION}-scripts \
                            postgresql-${version}-wal2json" \
                    && if [ $version != "9.4" ]; then \
                        EXTRAS="$EXTRAS postgresql-${version}-pgl-ddl-deploy"; \
                    fi \
                    && if [ $version != "11" ]; then \
                        EXTRAS="$EXTRAS postgresql-${version}-amcheck"; \
                    fi; \
                fi; \
            fi \
            && if [ $version != "9.3" ]; then \
                EXTRAS="$EXTRAS postgresql-${version}-pg-stat-kcache" \
                && if [ $version != "9.4" ]; then \
                    EXTRAS="$EXTRAS postgresql-${version}-cron"; \
                fi; \
            fi \
\
            # Install PostgreSQL binaries, contrib, plproxy and multiple pl's
            && apt-get install --allow-downgrades -y postgresql-contrib-${version} \
                        postgresql-plpython3-${version} libpq5=$version* $EXTRAS \
                        libpq-dev=$version* postgresql-server-dev-${version} \
\
            # Install 3rd party stuff
            && if [ "$DEMO" != "true" ]; then \
                if [ "$version" != "11" ]; then \
                    for extension in quantile trimmed_aggregates; do \
                        pgxn install $extension \
                        && strip /usr/lib/postgresql/$version/lib/$extension.so; \
                    done; \
                fi \
\
                && if [ "$version" = "9.6" ] || [ "$version" = "10" ] || [ "$version" = "11" ] ; then \
                    cd timescaledb \
                    && rm -fr build \
                    && ./bootstrap -DAPACHE_ONLY=1 -DSEND_TELEMETRY_DEFAULT=NO \
                    && make -C build install \
                    && strip /usr/lib/postgresql/$version/lib/timescaledb*.so \
                    && cd ..; \
                fi \
\
                # Install pg_rewind on 9.3 and 9.4
                && if [ "$version" = "9.3" ] || [ "$version" = "9.4" ]; then \
                    REWIND_VER=REL$(echo $version | sed 's/\./_/')_STABLE \
                    && apt-get source postgresql-${version} \
                    && curl -sL https://github.com/vmware/pg_rewind/archive/${REWIND_VER}.tar.gz | tar xz \
                    && make -C pg_rewind-${REWIND_VER} USE_PGXS=1 top_srcdir=../$(ls -d postgresql-${version}-*) install-strip \
                    && rm -fr pg_rewind-${REWIND_VER} postgresql-${version}*; \
                fi \
\
                && EXTRA_EXTENSIONS="plprofiler plantuner" \
                && if [ "$version" != "9.3" ]; then \
                    EXTRA_EXTENSIONS="$EXTRA_EXTENSIONS plpgsql_check postgres-decoderbufs"; \
                fi; \
            else \
                EXTRA_EXTENSIONS=""; \
            fi \
\
            && for n in bg_mon-${BG_MON_COMMIT} pg_auth_mon-${PG_AUTH_MON_COMMIT} set_user $EXTRA_EXTENSIONS; do \
                make -C $n USE_PGXS=1 clean install-strip; \
            done \
\
            && apt-get purge -y libpq-dev=$version*; \
    done \
\
    && apt-get install -y skytools3-ticker pspg \
\
    && if [ "$DEMO" != "true" ]; then \
        # patch, build and install pgbouncer
        apt-get source pgbouncer \
        && cd $(ls -d pgbouncer-*) \
        # Set last_connect_time for pool only when it really failed to connect
        && curl -sL https://github.com/pgbouncer/pgbouncer/pull/127.diff | patch -p1 \
        && curl -sL https://github.com/pgbouncer/pgbouncer/pull/326.diff \
            | sed -n '/^diff --git a\/src\/client.c b\/src\/client.c/,$ p' | patch -p1 \
        # Increase password size
        && sed -i 's/\(MAX_PASSWORD\t\).*/\11024/' include/bouncer.h \
        && sed -i 's/\(SEND_wrap(\)512\(, pktbuf_write_PasswordMessage, res, sk, psw)\)/\11024\2/' include/pktbuf.h \
        && debuild -b -uc -us \
        && cd .. \
        && dpkg -i pgbouncer_*.deb; \
    fi \
\
    # build and install missing packages
    && apt-get install -y postgresql-server-dev-all postgresql-server-dev-9.3 \
    && for pkg in pgextwlist; do \
        apt-get source postgresql-10-${pkg} \
        && cd $(ls -d *${pkg%?}*-*) \
        && if [ "$pkg" = "pgextwlist" ]; then \
            # make it possible to use it from shared_preload_libraries
            perl -ne 'print unless /PG_TRY/ .. /PG_CATCH/' pgextwlist.c > pgextwlist.c.f \
            && egrep -v '(PG_END_TRY|EmitWarningsOnPlaceholders)' pgextwlist.c.f > pgextwlist.c; \
        fi \
        && rm -f debian/pgversions \
        && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            echo ${version} >> debian/pgversions; \
        done \
        && pg_buildext updatecontrol \
        && debuild -b -uc -us \
        && cd .. \
        && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            for deb in postgresql-${version}-${pkg}_*.deb; do \
                if [ -f $deb ]; then dpkg -i $deb; fi; \
            done; \
        done; \
    done \
\
    # Remove unnecessary packages
    && apt-get purge -y ${BUILD_PACKAGES} postgresql-server-dev-* libmagic1 bsdmainutils \
    && apt-get autoremove -y \
    && apt-get clean \
    && dpkg -l | grep '^rc' | awk '{print $2}' | xargs apt-get purge -y \
\
    # Try to minimize size by creating symlinks instead of duplicate files
    && if [ "$DEMO" != "true" ]; then \
        cd /usr/lib/postgresql/$PGVERSION/bin \
        && for u in clusterdb pg_archivecleanup pg_basebackup pg_isready pg_test_fsync pg_test_timing pgbench psql reindexdb vacuumdb vacuumlo *.py; do \
            for v in /usr/lib/postgresql/*; do \
                if [ "$v" != "/usr/lib/postgresql/$PGVERSION" ] && [ -f "$v/bin/$u" ]; then \
                    rm $v/bin/$u \
                    && ln -s ../../$PGVERSION/bin/$u $v/bin/$u; \
                fi; \
            done; \
        done \
\
        && cd /usr/share/postgresql/$PGVERSION/contrib/postgis-$POSTGIS_VERSION \
        && for f in *.sql *.pl; do \
            for v in /usr/share/postgresql/*; do \
                if [ "$v" != "/usr/share/postgresql/$PGVERSION" ] && diff $v/contrib/postgis-$POSTGIS_VERSION/$f $f > /dev/null; then \
                    rm $v/contrib/postgis-$POSTGIS_VERSION/$f \
                    && ln -s ../../../$PGVERSION/contrib/postgis-$POSTGIS_VERSION/$f $v/contrib/postgis-$POSTGIS_VERSION/$f; \
                fi; \
            done; \
        done \
\
        && if [ -d /usr/share/postgresql/9.5/contrib/postgis-$POSTGIS_VERSION ]; then \
            cd /usr/share/postgresql/9.5/contrib/postgis-$POSTGIS_VERSION \
            && for f in *.sql *.pl; do \
                if [ -L $f ]; then continue; fi \
                && for v in /usr/share/postgresql/*; do \
                    if [ "$v" != "/usr/share/postgresql/9.5" ] && [ -f $v/contrib/postgis-$POSTGIS_VERSION/$f ] \
                            && [ ! -L $v/contrib/postgis-$POSTGIS_VERSION/$f ] \
                            && diff $v/contrib/postgis-$POSTGIS_VERSION/$f $f > /dev/null; then \
                        rm $v/contrib/postgis-$POSTGIS_VERSION/$f \
                        && ln -s ../../../9.5/contrib/postgis-$POSTGIS_VERSION/$f \
                                $v/contrib/postgis-$POSTGIS_VERSION/$f; \
                    fi; \
                done; \
            done; \
        fi \
\
        && cd /usr/share/postgresql/$PGVERSION/extension \
        && for orig in $(ls -1 *.sql | grep -v -- '--'); do \
            for f in ${orig%.sql}--*.sql; do \
                if diff $orig $f > /dev/null; then \
                    rm $f \
                    && ln -s $orig $f; \
                fi; \
            done; \
        done \
\
        && for e in pgq plproxy address_standardizer address_standardizer_data_us; do \
            orig=$(ls -1 $e--*--*.sql 2> /dev/null | head -n1) \
            && if [ "x$orig" != "x" ]; then \
                for f in $e--*--*.sql; do \
                    if [ "$f" != "$orig" ] && diff $f $orig > /dev/null; then \
                        rm $f \
                        && ln -s $orig $f; \
                    fi; \
                done; \
            fi; \
        done \
\
        && for f in *.sql *.control; do \
            for v in /usr/share/postgresql/*; do \
                if [ "$v" != "/usr/share/postgresql/$PGVERSION" ] \
                        && [ -f $v/extension/$f ] \
                        && [ ! -L $v/extension/$f ] \
                        && diff $v/extension/$f $f > /dev/null; then \
                    rm $v/extension/$f \
                    && ln -s ../../$PGVERSION/extension/$f $v/extension/$f; \
                fi; \
            done; \
        done \
\
        && if [ -d /usr/share/postgresql/9.5/extension ]; then \
            cd /usr/share/postgresql/9.5/extension \
            && for f in *.sql *.control; do \
                if [ -L $f ]; then continue; fi \
                && for v in /usr/share/postgresql/*; do \
                    if [ "$v" != "/usr/share/postgresql/9.5" ] && [ -f $v/extension/$f ] \
                            && [ ! -L $v/extension/$f ] \
                            && diff $v/extension/$f $f > /dev/null; then \
                        rm $v/extension/$f \
                        && ln -s ../../9.5/extension/$f $v/extension/$f; \
                   fi; \
                done; \
            done; \
        fi \
\
        && cd /usr/share/postgresql/$PGVERSION/contrib \
        && for f in *.sql *.html; do \
            for v in /usr/share/postgresql/*; do \
                if [ "$v" != "/usr/share/postgresql/$PGVERSION" ] && diff $v/contrib/$f $f > /dev/null; then \
                    rm $v/contrib/$f \
                    && ln -s ../../$PGVERSION/contrib/$f $v/contrib/$f; \
                fi; \
            done; \
        done; \
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
            /usr/lib/postgresql/*/bin/pg_recvlogical \
            /usr/lib/postgresql/*/bin/pg_standby \
            /usr/lib/postgresql/*/bin/pltcl_* \
    && find /var/log -type f -exec truncate --size 0 {} \;

# Install patroni, wal-e and wal-g
ENV PATRONIVERSION=1.5.7
ENV WALE_VERSION=1.1.0
ENV WALG_VERSION=v0.2.9
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
                                        python3-pystache python3-cachetools \
                                        python3-rsa python3-pyasn1-modules \
\
    && pip3 install setuptools \
\
    && if [ "$DEMO" != "true" ]; then \
        EXTRAS=",etcd,consul,zookeeper,aws" \
        && curl -sL https://github.com/wal-g/wal-g/releases/download/$WALG_VERSION/wal-g.linux-amd64-lzo.tar.gz \
                | tar -C /usr/local/bin -xz \
        && strip /usr/local/bin/wal-g \
        && apt-get install -y python3-etcd python3-consul python3-kazoo python3-meld3 \
                        python3-boto python3-gevent python3-greenlet python3-protobuf \
                        python3-websocket python3-requests-oauthlib python3-swiftclient \
\
        && find /usr/share/python-babel-localedata/locale-data -type f ! -name 'en_US*.dat' -delete \
\
        && pip3 install filechunkio wal-e[aws,google,swift]==$WALE_VERSION kubernetes==3.0.0 \
                'git+https://github.com/Supervisor/supervisor.git@master#egg=supervisor' \
                'git+https://github.com/zalando/pg_view.git@master#egg=pg-view' \
\
        && cd /usr/local/lib/python3.6/dist-packages \
\
        # pg_view installs useless pytest
        && sed -i '/^pytest/d' pg_view-*/requires.txt \
        && pip3 uninstall -y atomicwrites attrs more_itertools pluggy pytest py \
\
        # https://github.com/wal-e/wal-e/issues/318
        && sed -i 's/^\(    for i in range(0,\) num_retries):.*/\1 100):/g' /usr/lib/python3/dist-packages/boto/utils.py \
\
        # https://github.com/wal-e/wal-e/pull/384
        && curl -sL https://github.com/wal-e/wal-e/pull/384.diff | patch -p1 \
\
        # https://github.com/wal-e/wal-e/pull/392
        && curl -sL https://github.com/wal-e/wal-e/pull/392.diff | patch -p1 \
\
        && echo 4.0.0.dev0 > supervisor/version.txt; \
    fi \
    && pip3 install "git+https://github.com/zalando/patroni.git@1a6db4f5afbc3f8d7f42d1d2c57edd988e830bda#egg=patroni[kubernetes$EXTRAS]" \
    && sed -i 's/1, 5, 6/1, 5, 7/' /usr/local/lib/python3.6/dist-packages/patroni/dcs/__init__.py \
    && echo "__version__ = '$PATRONIVERSION'" > /usr/local/lib/python3.6/dist-packages/patroni/version.py \
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

ARG COMPRESS=false

RUN set -ex \
    && if [ "$COMPRESS" = "true" ]; then \
        apt-get update \
        && apt-get install -y busybox xz-utils \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/* /var/cache/debconf/* /usr/share/doc /usr/share/man /etc/rc?.d /etc/systemd \
        && ln -snf busybox /bin/sh \
        && files="/bin/sh" \
        && libs="$(ldd $files | awk '{print $3;}' | grep '^/' | sort -u) /lib/x86_64-linux-gnu/ld-linux-x86-64.so.* /lib/x86_64-linux-gnu/libnsl.so.* /lib/x86_64-linux-gnu/libnss_compat.so.*" \
        && (echo /var/run $files $libs | tr ' ' '\n' && realpath $files $libs) | sort -u | sed 's/^\///' > /exclude \
        && find /etc/alternatives -xtype l -delete \
        && save_dirs="usr lib var bin sbin etc/ssl etc/init.d etc/alternatives etc/apt" \
        && XZ_OPT=-e9v tar -X /exclude -cpJf a.tar.xz $save_dirs \
        && rm -fr /usr/local/lib/python* \
        && /bin/busybox sh -c "(find $save_dirs -not -type d && cat /exclude /exclude && echo exclude) | sort | uniq -u | xargs /bin/busybox rm" \
        && /bin/busybox --install -s \
        && /bin/busybox sh -c "find $save_dirs -type d -depth -exec rmdir -p {} \; 2> /dev/null"; \
    fi

FROM scratch
COPY --from=builder / /

LABEL maintainer="Alexander Kukushkin <alexander.kukushkin@zalando.de>"

ARG PGVERSION

EXPOSE 5432 8008 8080

ENV LC_ALL=en_US.utf-8 \
    PATH=$PATH:/usr/lib/postgresql/$PGVERSION/bin \
    PGHOME=/home/postgres

ENV WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env \
    PGROOT=$PGHOME/pgdata/pgroot \
    LOG_ENV_DIR=$PGHOME/etc/log.d/env

ENV PGDATA=$PGROOT/data \
    PGLOG=$PGROOT/pg_log

WORKDIR $PGHOME

COPY motd /etc/
COPY supervisor /etc/supervisor
COPY pgq_ticker.ini $PGHOME/
COPY envdir /usr/local/bin/

RUN mkdir -p /var/log/supervisor \
        && ln -s supervisor/supervisord.conf /etc/supervisord.conf \
        && sed -i "s|/var/lib/postgresql.*|$PGHOME:/bin/bash|" /etc/passwd \
        && chown -R postgres:postgres $PGHOME /run \
        && sed -i 's/set compatible/set nocompatible/' /etc/vim/vimrc.tiny \
        && for e in TERM=linux LC_ALL=C.UTF-8 LANG=C.UTF-8 EDITOR=editor "PAGER='pspg -bX --no-mouse'"; \
            do echo "export $e" >> /etc/bash.bashrc; \
        done \
        && echo "source /etc/motd" >> /root/.bashrc

COPY scripts bootstrap /scripts/
COPY scm-source.json launch.sh /

CMD ["/bin/sh", "/launch.sh"]

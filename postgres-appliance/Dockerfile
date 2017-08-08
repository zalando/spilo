FROM ubuntu:16.04
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend \
    && echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend \

    && apt-get upgrade -y \
    # Install cron, curl, jq, vim, gdb, strace
    && apt-get install -y cron curl ca-certificates less locales jq pv vim gdb sudo strace supervisor stunnel \

    ## Make sure we have a en_US.UTF-8 locale available
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \

    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install PostgreSQL
ENV PGVERSION=9.6 PGOLDVERSIONS="9.3 9.4 9.5"
RUN export DEBIAN_FRONTEND=noninteractive \
    && export BUILD_PACKAGES="devscripts build-essential pgxnclient libedit-dev zlib1g-dev libssl-dev libselinux1-dev libkrb5-dev libxslt1-dev libxml2-dev libpam0g-dev libcurl4-openssl-dev libprotobuf-c-dev liblwgeom-dev pkg-config libproj-dev libevent-dev" \

    # Add PGDG repositories
    && export DISTRIB_CODENAME=$(sed -n 's/DISTRIB_CODENAME=//p' /etc/lsb-release) \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && echo "deb-src http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" >> /etc/apt/sources.list.d/pgdg.list \
    && curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \

    && apt-get update \
    && apt-get install -y postgresql-common equivs gcc \
    # forbid creation of a main cluster when package is installed
    && sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf \

    # Prepare and install some "fake" packages to avoid installing unnecessary dependencies
    && mkdir tempdir && cd tempdir \
    && for p in fontconfig-config libavcodec-ffmpeg56 libavdevice-ffmpeg56 libavformat-ffmpeg56 libavresample-ffmpeg2 \
                libavutil-ffmpeg54 libblas-common libcairo2 libcoin80v5 libgl1-mesa-dri libpango-1.0-0 \
                libpangocairo-1.0-0 libpoppler-glib8 libqt4-opengl libqtcore4 libqtgui4 librsvg2-2 \
                ilibswscale-ffmpeg3 libx11-data libxft2 libxine2 libxss1 libxt6 mysql-common odbcinst; do \
        version=$(apt-cache show $p | sed -n 's/^Version: //p' | sort -rV | head -n 1) \
        && echo "Section: misc\nPriority: optional\nStandards-Version: 3.9.2\nPackage: $p\nVersion: $version\nDescription: $p" > $p \
        && equivs-build $p; \
    done \
    && dpkg -i *.deb \

    && apt-get install -y libprotobuf-c1 libevent-2.0 $BUILD_PACKAGES \

    # prepare bg_mon sources
    && export BG_MON_COMMIT=796690f2bee2778321a45233fe4012fc06b75f02 \
    && curl -s -L https://github.com/CyberDem0n/bg_mon/archive/$BG_MON_COMMIT.tar.gz | tar xz \

    && export DECODEBUFS_COMMIT=d08a75593c68897600e10f5250133337624bcf63 \
    && curl -s -L https://github.com/debezium/postgres-decoderbufs/archive/$DECODEBUFS_COMMIT.tar.gz | tar xz \

    && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            # next two lines are necessary to install exact versions of libpq5 and libpq-dev (to compile extensions)
            sed -i "s/ main.*$/ main $version/g" /etc/apt/sources.list.d/pgdg.list \
            && apt-get update \

            # Install PostgreSQL binaries, contrib, pgq, plproxy, pgq and multiple pl's
            && apt-get install --allow-downgrades -y postgresql-${version} postgresql-${version}-dbg \
                        postgresql-client-${version} postgresql-contrib-${version} postgresql-${version}-plproxy \
                        postgresql-${version}-pgq3 postgresql-${version}-postgis-2.3 postgresql-plpython3-${version} \
                        postgresql-plpython-${version} postgresql-${version}-plr postgresql-pltcl-${version} \
                        postgresql-${version}-plv8 postgresql-${version}-pllua postgresql-plperl-${version} \
                        libpq5=$version* libpq-dev=$version* postgresql-server-dev-${version} \

            # Install bg_mon
            && make -C bg_mon-${BG_MON_COMMIT} USE_PGXS=1 clean install \

            # install 3rd party extensions
            && for extension in quantile trimmed_aggregates pg_repack; do \
                pgxn install $extension; \
            done \

            && if [ "$version" != "9.3" ]; then \
                make -C postgres-decoderbufs-$DECODEBUFS_COMMIT clean install; \
            fi \

            # Install pg_rewind on 9.3 and 9.4
            && if [ "$version" = "9.3" ] || [ "$version" = "9.4" ]; then \
                export REWIND_VER=REL$(echo $version | sed 's/\./_/')_STABLE \
                && apt-get source postgresql-${version} \
                && curl -s -L https://github.com/vmware/pg_rewind/archive/${REWIND_VER}.tar.gz | tar xz \
                && make -C pg_rewind-${REWIND_VER} USE_PGXS=1 top_srcdir=../$(ls -d postgresql-${version}-*) install \
                && rm -fr pg_rewind-${REWIND_VER} postgresql-${version}*; \
            fi \

            && apt-get purge -y libpq-dev=$version* postgresql-server-dev-${version}; \
    done \

    && apt-get install -y skytools3-ticker \

    # patch, build and install pgbouncer
    && mkdir pgbouncer && cd pgbouncer \
    && apt-get source pgbouncer \
    && cd $(ls -d pgbouncer-*) \
    && curl -sL https://github.com/pgbouncer/pgbouncer/pull/127.diff | patch -p1 \
    && debuild -b -uc -us \
    && dpkg -i ../pgbouncer_*.deb \
    && cd ../.. \

    # install pam_oauth2.so
    && export PAM_OAUTH_COMMIT=bed1f8d31840d1fda49365921449112a7421b8ca \
    && export JSMN_COMMIT=1682c32e9ae5990ddd0f0e907270a0f6dde5cbe9 \
    && curl -s -L https://github.com/zalando-incubator/pam-oauth2/archive/$PAM_OAUTH_COMMIT.tar.gz | tar xz \
    && cd pam-oauth2-$PAM_OAUTH_COMMIT \
    && curl -s -L https://github.com/zserge/jsmn/archive/$JSMN_COMMIT.tar.gz | tar xz \
    && rm -fr jsmn && mv jsmn-$JSMN_COMMIT jsmn \
    && make install \
    && cd ../.. \

    # Clean up
    && apt-get purge -y equivs fakeroot libfakeroot libmpc3 bsdmainutils libcc1-0 groff-base libunistring0 libmagic1 file ${BUILD_PACKAGES} \
    && apt-get autoremove -y \

    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* tempdir

ENV PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

# Install patroni and WAL-e
ENV PATRONIVERSION=1.3.3
ENV WALE_VERSION=1.0.3
RUN export DEBIAN_FRONTEND=noninteractive \
    export BUILD_PACKAGES="python3-pip python3-dev gcc" \
    && apt-get update \
    && apt-get install -y \
            # Required for wal-e
            daemontools lzop \
            # Required for /usr/local/bin/patroni
            python3 python3-pystache python3-prettytable python3-six \
            ${BUILD_PACKAGES} \

    && pip3 install setuptools pip --upgrade \
    && pip3 install --upgrade patroni==$PATRONIVERSION \
            gcloud boto wal-e==$WALE_VERSION \

    # https://github.com/wal-e/wal-e/issues/318
    && sed -i 's/^\(    for i in range(0,\) num_retries):.*/\1 100):/g' /usr/local/lib/python3.5/dist-packages/boto/utils.py \

    # Clean up
    && apt-get purge -y ${BUILD_PACKAGES} \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache


# install etcdctl
ENV ETCDVERSION 2.3.8
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz \
    | tar xz -C /bin --strip=1 --wildcards --no-anchored etcdctl etcd


#install pg_view
RUN curl -L https://raw.githubusercontent.com/zalando/pg_view/2ea99479460d81361bdb7601a1564072ddd584ac/pg_view.py \
    | sed -e 's/env python/env python3/g' > /usr/local/bin/pg_view.py && chmod +x /usr/local/bin/pg_view.py

ENV PGHOME=/home/postgres
ENV PGROOT=$PGHOME/pgdata/pgroot
ENV PGDATA=$PGROOT/data
ENV PGLOG=$PGROOT/pg_log
ENV WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env

# Set PGHOME as a login directory for the PostgreSQL user.
RUN usermod -d $PGHOME -m postgres

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_role.py basebackup.sh wale_restore_command.sh wal-e-wal-fetch.sh callback_aws.py /
ADD supervisor.d /etc/supervisor/conf.d/
ADD pgq_ticker.ini $PGHOME
ADD motd /etc/
RUN echo "source /etc/motd" >> /root/.bashrc
RUN echo "export TERM=linux\nexport LC_ALL=C.UTF-8\nexport LANG=C.UTF-8\nexport EDITOR=vim" >> /etc/bash.bashrc
RUN chmod 700 /postgres_*

ENV ETCD_DISCOVERY_DOMAIN=postgres.acid.example.com LC_ALL=en_US.utf-8

WORKDIR $PGHOME
EXPOSE 5432 8008 8080
RUN chown -R postgres:postgres /postgres_* $PGHOME
CMD ["/bin/bash", "/launch.sh"]

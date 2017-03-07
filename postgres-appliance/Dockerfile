FROM ubuntu:14.04
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend \
    && echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend \

    && apt-get upgrade -y \
    # Install curl, jq, vim, gdb, strace
    && apt-get install -y curl ca-certificates jq pv vim gdb strace supervisor stunnel realpath \

    ## Make sure we have a en_US.UTF-8 locale available
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \

    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install PostgreSQL
ENV PGVERSION=9.6 PGOLDVERSIONS="9.3 9.4 9.5"
RUN export DEBIAN_FRONTEND=noninteractive \
    && export BUILD_PACKAGES="gcc libc6-dev dpkg-dev make pgxnclient libedit-dev zlib1g-dev libssl-dev libselinux1-dev libkrb5-dev libxslt1-dev libxml2-dev libpam0g-dev libcurl4-openssl-dev" \

    # Add PGDG repositories
    && export DISTRIB_CODENAME=$(sed -n 's/DISTRIB_CODENAME=//p' /etc/lsb-release) \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && echo "deb-src http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" >> /etc/apt/sources.list.d/pgdg.list \
    && curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \

    && apt-get update \
    && apt-get install -y postgresql-common ${BUILD_PACKAGES} \
    # forbid creation of a main cluster when package is installed
    && sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf \

    # This is a temporary solution of pg_repack problems with UPSERTS
    # as soon they will release a new version we should switch back to pgxn
    && export PG_REPACK_COMMIT=b329f9e143521077cf55266355d265857ff9a3bf \
    && curl -s -L https://github.com/reorg/pg_repack/archive/$PG_REPACK_COMMIT.tar.gz | tar xz \

    && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            # next two lines are necessary to install exact versions of libpq5 and libpq-dev (to compile extensions)
            sed -i "s/ main.*$/ main $version/g" /etc/apt/sources.list.d/pgdg.list \
            && apt-get update \

            # Install PostgreSQL binaries, contrib, pgq, plproxy, pgq and multiple pl's
            && apt-get install -y postgresql-${version} postgresql-${version}-dbg postgresql-client-${version} \
                        postgresql-contrib-${version} postgresql-${version}-plproxy postgresql-${version}-pgq3 \
                        postgresql-${version}-postgis-2.3 postgresql-plpython3-${version} \
                        postgresql-plpython-${version} postgresql-${version}-plr postgresql-pltcl-${version} \
                        postgresql-${version}-plv8 postgresql-${version}-pllua postgresql-plperl-${version} \
                        libpq5=$version* libpq-dev=$version* postgresql-server-dev-${version} \

            # install 3rd party extensions
            && for extension in quantile trimmed_aggregates; do \
                pgxn install $extension; \
            done \

            # Install pg_repack
            && make -C pg_repack-${PG_REPACK_COMMIT} clean install \

            # Install pg_rewind on 9.3 and 9.4
            && if [ "$version" = "9.3" ] || [ "$version" = "9.4" ]; then \
                export REWIND_VER=REL$(echo $version | sed 's/\./_/')_STABLE \
                && apt-get source postgresql-${version} \
                && curl -s -L https://github.com/vmware/pg_rewind/archive/${REWIND_VER}.tar.gz | tar xz \
                && make -C pg_rewind-${REWIND_VER} USE_PGXS=1 top_srcdir=$(ls -d ../postgresql-${version}-*) install \
                && rm -fr pg_rewind-${REWIND_VER} postgresql-${version}*; \
            fi \

            && apt-get purge -y libpq-dev=$version* postgresql-server-dev-${version}; \
    done \

    && apt-get install -y skytools3-ticker \

    # install pam_oauth2.so
    && export PAM_OAUTH_COMMIT=bed1f8d31840d1fda49365921449112a7421b8ca \
    && export JSMN_COMMIT=1682c32e9ae5990ddd0f0e907270a0f6dde5cbe9 \
    && curl -s -L https://github.com/zalando-incubator/pam-oauth2/archive/$PAM_OAUTH_COMMIT.tar.gz | tar xz \
    && cd pam-oauth2-$PAM_OAUTH_COMMIT \
    && curl -s -L https://github.com/zserge/jsmn/archive/$JSMN_COMMIT.tar.gz | tar xz \
    && rm -fr jsmn && mv jsmn-$JSMN_COMMIT jsmn \
    && make install \
    && cd .. \

    # Clean up
    && apt-get purge -y ${BUILD_PACKAGES} \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* pg_repack-${PG_REPACK_COMMIT} pam-oauth2-$PAM_OAUTH_COMMIT

ENV PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

# Install patroni and WAL-e
ENV PATRONIVERSION=1.2.4
ENV WALE_VERSION=1.0.3
RUN export DEBIAN_FRONTEND=noninteractive \
    export BUILD_PACKAGES="build-essential python3-dev python3-pip libpq-dev libyaml-dev" \
    && apt-get update \
    && apt-get install -y \
            # Required for wal-e
            daemontools lzop \
            # Required for /usr/local/bin/patroni
            python3 python3-pkg-resources python3-setuptools \
            ${BUILD_PACKAGES} \

    && pip3 install pip --upgrade \
    && pip3 install --upgrade packaging appdirs requests pystache patroni==$PATRONIVERSION \
            gcloud boto wal-e==$WALE_VERSION \

    # https://github.com/wal-e/wal-e/issues/318
    && sed -i 's/^\(    for i in range(0,\) num_retries):.*/\1 100):/g' /usr/local/lib/python3.4/dist-packages/boto/utils.py \

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

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_role.py basebackup.sh wale_restore_command.sh /
ADD supervisor.d /etc/supervisor/conf.d/
ADD stunnel.d /etc/stunnel
ADD pgq_ticker.ini $PGHOME
ADD motd /etc/
RUN echo "source /etc/motd" >> /root/.bashrc
RUN echo "export TERM=linux\nexport LC_ALL=C.UTF-8\nexport LANG=C.UTF-8" >> /etc/bash.bashrc
RUN chmod 700 /postgres_*

ENV ETCD_DISCOVERY_DOMAIN=postgres.acid.example.com LC_ALL=en_US.utf-8

WORKDIR $PGHOME
EXPOSE 5432 8008
RUN chown -R postgres:postgres /postgres_* $PGHOME
CMD ["/bin/bash", "/launch.sh"]

FROM ubuntu:14.04
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

# Install curl, jq, vim, gdb, strace
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend \
    && echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend \

    && apt-get upgrade -y \
    && apt-get install -y curl ca-certificates jq pv vim gdb strace supervisor stunnel realpath \

    ## Make sure we have a en_US.UTF-8 locale available
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \

    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add PGDG repositories
RUN export DISTRIB_CODENAME=$(sed -n 's/DISTRIB_CODENAME=//p' /etc/lsb-release) \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && echo "deb-src http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" >> /etc/apt/sources.list.d/pgdg.list \
    && curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

# Install PostgreSQL
ENV PGVERSION=9.6 PGOLDVERSIONS="9.5 9.4 9.3"
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install -y skytools3-ticker \
    && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            # Install PostgreSQL binaries, contrib, pgq, plproxy, pgq and multiple pl's
            apt-get install -y postgresql-${version} postgresql-${version}-dbg postgresql-client-${version} \
                        postgresql-contrib-${version} postgresql-${version}-plproxy postgresql-${version}-pgq3 \
                        postgresql-${version}-postgis-2.3 postgresql-plpython3-${version} \
                        postgresql-plpython-${version} postgresql-${version}-plr postgresql-pltcl-${version} \
                        postgresql-${version}-plv8 postgresql-${version}-pllua postgresql-plperl-${version} \
            # Remove the default cluster, which Debian stupidly starts right after installation of the packages
            && pg_dropcluster --stop ${version} main; \
    done \

    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

# Install patroni, WAL-e and extensions
# We do this in one big step to reduce the Docker image size:
## 1 Install tools required to build
## 2 Build
## 3 Remove tools only required for build
ENV PATRONIVERSION=1.2.2
ENV WALE_VERSION=1.0.1
RUN export DEBIAN_FRONTEND=noninteractive \
    export BUILD_PACKAGES="postgresql-server-dev-${PGVERSION} python3-pip python3-dev build-essential pgxnclient" \
    export PGXN_EXTENSIONS="quantile trimmed_aggregates" \
    && apt-get update \
    && apt-get install -y \
            # Required for wal-e
            daemontools lzop \
            # Required for /usr/local/bin/patroni
            python3 python3-pkg-resources python3-setuptools \
            ${BUILD_PACKAGES} \

    # install extensions for old postgres versions
    && export OLD_PATH=$PATH \
    && for version in ${PGOLDVERSIONS}; do \
        apt-get install -y postgresql-server-dev-${version} \
        && export PATH=/usr/lib/postgresql/${version}/bin:$OLD_PATH \
        && for extension in ${PGXN_EXTENSIONS}; do pgxn install $extension; done \
        && apt-get purge -y postgresql-server-dev-${version}; \
    done \
    && export PATH=$OLD_PATH \

    && pip3 install pip --upgrade \
    && pip3 install --upgrade requests pystache patroni==$PATRONIVERSION \
            gcloud boto wal-e==$WALE_VERSION \
    && for extension in ${PGXN_EXTENSIONS}; do pgxn install $extension; done \
    # Clean up
    && apt-get purge -y ${BUILD_PACKAGES} \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache


# install etcdctl
ENV ETCDVERSION 2.3.7
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz \
    | tar xz -C /bin --strip=1 --wildcards --no-anchored etcdctl etcd


#install pg_view
RUN curl -L https://raw.githubusercontent.com/zalando/pg_view/master/pg_view.py \
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

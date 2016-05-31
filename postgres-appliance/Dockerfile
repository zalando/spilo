FROM ubuntu:14.04
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

# Install curl, jq, vim, gdb, strace
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend \
    && echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend \

    && apt-get upgrade -y \
    && apt-get install -y curl ca-certificates jq pv vim gdb strace supervisor stunnel \

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
ENV PGVERSION=9.5 PGOLDVERSIONS="9.4"
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install -y skytools3-ticker \
    && for version in ${PGOLDVERSIONS} ${PGVERSION}; do \
            # Install PostgreSQL binaries, contrib, pgq, plproxy, pgq and plpython
            apt-get install -y postgresql-${version} postgresql-${version}-dbg postgresql-client-${version} \
                        postgresql-contrib-${version} postgresql-${version}-plproxy postgresql-${version}-pgq3 \
                        postgresql-${version}-postgis postgresql-plpython3-${version} \
                        postgresql-plpython-${version} postgresql-${version}-plr \

            # Remove the default cluster, which Debian stupidly starts right after installation of the packages
            && pg_dropcluster --stop ${version} main; \
    done \

    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin

# Install patroni and WAL-e
ENV PATRONIVERSION=0.90
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install -y python postgresql-server-dev-${PGVERSION} python-pip python-dev gcc \
    # Required for wal-e
    daemontools lzop \
    # Required for /usr/local/bin/patroni
    python-pkg-resources \
    && pip install pip --upgrade \
    && pip install --upgrade requests wal-e pystache patroni==$PATRONIVERSION \

    # Clean up
    && apt-get purge -y postgresql-server-dev-${PGVERSION} python-pip python-dev binutils gcc \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache


# install etcdctl
ENV ETCDVERSION 2.3.3
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz \
    | tar xz -C /bin --strip=1 --wildcards --no-anchored etcdctl

ENV PGHOME=/home/postgres
ENV PGDATA=$PGHOME/pgdata/data
ENV WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env

# Set PGHOME as a login directory for the PostgreSQL user.
RUN usermod -d $PGHOME -m postgres

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh /
ADD supervisor.d /etc/supervisor/conf.d/
ADD stunnel.d /etc/stunnel
ADD pgq_ticker.ini $PGHOME
ADD motd /etc/
RUN echo "source /etc/motd" >> /root/.bashrc
RUN chmod 700 /postgres_*

ENV ETCD_DISCOVERY_DOMAIN=postgres.acid.example.com DEBUG=0 LC_ALL=en_US.utf-8

WORKDIR $PGHOME
EXPOSE 5432 8008
RUN chown -R postgres:postgres /postgres_* $PGHOME
CMD ["/bin/bash", "/launch.sh"]

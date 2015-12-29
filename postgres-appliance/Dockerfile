FROM zalando/ubuntu:14.04.1-1
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

RUN apt-get update

# Basic tooling
RUN apt-get install curl git python ca-certificates vim jq build-essential gdb strace -y && apt-get clean

# Basic python packages
RUN apt-get install python-yaml python-pip python-dev libxml2-dev libxslt-dev libffi-dev lzop pv daemontools -y \
    && apt-get clean
RUN pip install pip --upgrade

## Make sure we have a en_US.UTF-8 locale available
RUN localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8

# Add PGDG repositories
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
RUN echo "deb-src http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" >> /etc/apt/sources.list.d/pgdg.list
RUN echo "deb http://packages.2ndquadrant.com/bdr/apt/ $(lsb_release -cs)-2ndquadrant main" >> /etc/apt/sources.list.d/pgdg.list
RUN curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
# import the BDR plugin
RUN curl -s -o - http://packages.2ndquadrant.com/bdr/apt/AA7A6805.asc | sudo apt-key add -
RUN apt-get update

ENV PGVERSION 9.4
ENV PGTYPE postgresql-bdr
ENV PGCOMPATIBLETYPE postgresql
ENV PGHOME /home/postgres
ENV PGDATA $PGHOME/pgdata/data


# Install PostgreSQL 9.4 binaries, contrib, pgq, plproxy, pgq and plpython
RUN apt-get install ${PGTYPE}-${PGVERSION} ${PGTYPE}-${PGVERSION}-bdr-plugin ${PGTYPE}-${PGVERSION}-dbg ${PGTYPE}-server-dev-${PGVERSION} ${PGTYPE}-client-${PGVERSION} ${PGTYPE}-contrib-${PGVERSION} ${PGCOMPATIBLETYPE}-${PGVERSION}-plproxy ${PGCOMPATIBLETYPE}-${PGVERSION}-plr ${PGCOMPATIBLETYPE}-${PGVERSION}-pgq3 ${PGCOMPATIBLETYPE}-${PGVERSION}-postgis -y \
    ## # install all build-dependencies for postgresql-9.4 in order to be able to compile 9.4
    && apt-get clean \
    ## # Remove the default cluster, which Debian stupidly starts right after installation of the packages
    && pg_dropcluster --stop ${PGVERSION} main
ENV PATH $PATH:/usr/lib/postgresql/${PGVERSION}/bin

# Set PGHOME as a login directory for the PostgreSQL user.
RUN usermod -d $PGHOME -m postgres
RUN apt-get build-dep postgresql-${PGVERSION} -y

ENV PGREWINDTAG PGREWIND1_0_0_PG9_4

# Add pg_rewind. Has to be compiled from git, since there are no proper packages.
RUN git clone -b ${PGREWINDTAG} --depth 1 https://github.com/vmware/pg_rewind.git \
    && cd pg_rewind && apt-get source postgresql-${PGVERSION} -y \
    && USE_PGXS=1 make top_srcdir=$(find . -name "postgresql*" -type d) install \
    && cd / \
    # we remove the sources to decrease the size of the Docker image
    && rm -rf /pg_rewind/

# WAL-e requests a relatively new version of requests, install other modules via pip as well
RUN pip install requests six wal-e psycopg2 dnspython kazoo python-etcd click prettytable --upgrade


# install etcd
ENV ETCDVERSION 2.2.1
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz \
    | tar xz -C /bin --strip=1 --wildcards --no-anchored etcd etcdctl

# Copy the snakeoil certificates for usage as dummy certificates
RUN cp /etc/ssl/private/ssl-cert-snakeoil.key $PGHOME/dummy.key && cp /etc/ssl/certs/ssl-cert-snakeoil.pem $PGHOME/dummy.crt

# Install Patroni
ENV PATRONIVERSION feature/bdr
WORKDIR $PGHOME
RUN git clone https://github.com/zalando/patroni -b ${PATRONIVERSION}
RUN ln -s $PGHOME/patroni/patronictl.py /usr/local/bin/patronictl \
    && ln -s $PGHOME/patroni/patroni/scripts/aws.py /usr/local/bin/patroni_aws \
    && ln -s $PGHOME/patroni/patroni/scripts/wale_restore.py /usr/local/bin/patroni_wale_restore

ADD postgres_ha.sh /
RUN chown postgres:postgres $PGHOME -R
RUN chown postgres:postgres /postgres_ha.sh
RUN chmod 700 /postgres_ha.sh

ENV ETCD_DISCOVERY_DOMAIN postgres.acid.example.com
ENV SCOPE test
ENV BDR_DATABASE bdrtest
ENV WAL_S3_BUCKET spilo-example-com
ENV DEBUG 0
# Shoud be 3am by GMT+2 aka Berlin Summer Time
ENV BACKUP_HOUR 1
ENV WALE_BACKUP_THRESHOLD_MEGABYTES 1024
ENV WALE_BACKUP_THRESHOLD_PERCENTAGE 30
ENV WALE_ENV_DIR $PGHOME/etc/wal-e.d/env
ENV LC_ALL en_US.utf-8
WORKDIR $PGHOME
USER postgres
ENTRYPOINT ["/bin/bash", "/postgres_ha.sh"]
EXPOSE 5432


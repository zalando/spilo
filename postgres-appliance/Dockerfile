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
RUN curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN apt-get update

ENV PGHOME /home/postgres
ENV PGDATA $PGHOME/pgdata/data


ENV PGVERSION 9.4
# Install PostgreSQL 9.4 binaries, contrib, pgq, plproxy, pgq and plpython
RUN apt-get install postgresql-${PGVERSION} postgresql-${PGVERSION}-dbg postgresql-server-dev-${PGVERSION} postgresql-client-${PGVERSION} postgresql-contrib-${PGVERSION} postgresql-${PGVERSION}-plproxy postgresql-${PGVERSION}-pgq3 postgresql-${PGVERSION}-postgis postgresql-plpython3-${PGVERSION} postgresql-plpython-${PGVERSION} postgresql-${PGVERSION}-plr -y \
    && apt-get clean \
    ## # Remove the default cluster, which Debian stupidly starts right after installation of the packages
    && pg_dropcluster --stop ${PGVERSION} main

ENV PGVERSION 9.5
# Install PostgreSQL PGVERSION binaries, contrib, pgq, plproxy, pgq and plpython
RUN apt-get install postgresql-${PGVERSION} postgresql-${PGVERSION}-dbg postgresql-server-dev-${PGVERSION} postgresql-client-${PGVERSION} postgresql-contrib-${PGVERSION} postgresql-${PGVERSION}-plproxy postgresql-${PGVERSION}-pgq3 postgresql-${PGVERSION}-postgis postgresql-plpython3-${PGVERSION} postgresql-plpython-${PGVERSION} postgresql-${PGVERSION}-plr -y \
    && apt-get clean \
    ## # Remove the default cluster, which Debian stupidly starts right after installation of the packages
    && pg_dropcluster --stop ${PGVERSION} main
ENV PATH $PATH:/usr/lib/postgresql/${PGVERSION}/bin

# Set PGHOME as a login directory for the PostgreSQL user.
RUN usermod -d $PGHOME -m postgres

# Install Patroni
ENV PATRONIVERSION 0.90
WORKDIR $PGHOME
RUN pip install patroni==$PATRONIVERSION

# WAL-e requests a relatively new version of requests, install other modules via pip as well
RUN pip install --upgrade requests wal-e pystache

# install etcd
ENV ETCDVERSION 2.3.2
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz \
    | tar xz -C /bin --strip=1 --wildcards --no-anchored etcd etcdctl

ADD postgres_ha.py /
ADD postgres_backup.sh /
RUN chown postgres:postgres $PGHOME -R
RUN chown postgres:postgres /postgres_*
RUN chmod 700 /postgres_*

ENV ETCD_DISCOVERY_DOMAIN postgres.acid.example.com
ENV DEBUG 0

ENV LC_ALL en_US.utf-8

# Allow cron to be started by postgres
RUN echo "postgres ALL=(ALL:ALL) NOPASSWD: /usr/sbin/cron" > /etc/sudoers
ADD scm-source.json /scm-source.json
WORKDIR $PGHOME
USER postgres
ENTRYPOINT ["/usr/bin/python", "/postgres_ha.py"]
EXPOSE 5432


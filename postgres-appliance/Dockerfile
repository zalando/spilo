FROM zalando/ubuntu:14.04.1-1
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

ENV PGVERSION 9.4
ENV PGHOME /home/postgres
ENV PGDATA $PGHOME/pgdata/data

# Add PGDG repositories
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
RUN apt-get install wget ca-certificates -y
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
RUN apt-get update -y
RUN apt-get upgrade -y

# Add git
RUN apt-get install git -y

# Add python
RUN apt-get install python python-yaml -y

## Make sure we have a en_US.UTF-8 locale available
RUN localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8

# Install PostgreSQL 9.4 binaries, contrib, pgq, plproxy and pgq
RUN apt-get install postgresql-${PGVERSION} postgresql-${PGVERSION}-dbg postgresql-server-dev-${PGVERSION} postgresql-client-${PGVERSION} postgresql-contrib-${PGVERSION} postgresql-${PGVERSION}-plproxy postgresql-${PGVERSION}-pgq3 postgresql-${PGVERSION}-postgis -y --fix-missing

# Remove the default cluster, which Debian stupidly starts right after installation of the packages
RUN pg_dropcluster --stop ${PGVERSION} main

# install psycopg2 and requests (for governor)
RUN apt-get install python-psycopg2 python-requests -y

# Set PGHOME as a login directory for the PostgreSQL user.
RUN usermod -d $PGHOME -m postgres

# install WAL-e
RUN apt-get install build-essential gdb strace -y
RUN apt-get install python-pip python-dev libxml2-dev libxslt-dev libffi-dev lzop pv daemontools -y
RUN pip install six --upgrade
RUN pip install wal-e

ENV ETCDVERSION 2.0.11
# install etcd
RUN apt-get install curl -y
RUN RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz | tar xz -C /bin --strip=1 --wildcards --no-anchored etcd etcdctl

# Install debug tooling
RUN apt-get install vim jq -y

ENV PATH $PATH:/usr/lib/postgresql-${PGVERSION}/bin

# Copy the snakeoil certificates for usage as dummy certificates
RUN cp /etc/ssl/private/ssl-cert-snakeoil.key $PGHOME/dummy.key && cp /etc/ssl/certs/ssl-cert-snakeoil.pem $PGHOME/dummy.crt

ADD postgres_ha.sh /
RUN chown postgres:postgres $PGHOME -R
RUN chown postgres:postgres /postgres_ha.sh
RUN chmod 700 /postgres_ha.sh

ENV ETCD_DISCOVERY_URL postgres.acid.example.com
ENV SCOPE test
ENV WAL_S3_BUCKET spilo-example-com
ENV DEBUG 0
# Shoud be 3am by GMT+2 aka Berlin Summer Time
ENV BACKUP_HOUR 1
ENV WALE_BACKUP_THRESHOLD_MEGABYTES 1024
ENV WALE_BACKUP_THRESHOLD_PERCENTAGE 30
ENV LC_ALL en_US.utf-8
WORKDIR $PGHOME
USER postgres
ENTRYPOINT ["/bin/bash", "/postgres_ha.sh"]
EXPOSE 5432


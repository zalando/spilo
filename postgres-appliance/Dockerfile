FROM zalando/ubuntu:14.04.1-1
MAINTAINER Oleksii Kliukin <oleksii.kliukin@zalando.de>

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

ENV PGVERSION 9.4
ENV PGDATA /home/postgres/data
# Install PostgreSQL 9.4 binaries, contrib, pgq, plproxy and pgq
RUN apt-get install postgresql-${PGVERSION} postgresql-${PGVERSION}-dbg postgresql-server-dev-${PGVERSION} postgresql-client-${PGVERSION} postgresql-contrib-${PGVERSION} postgresql-${PGVERSION}-plproxy postgresql-${PGVERSION}-pgq3 postgresql-${PGVERSION}-postgis -y

# Remove the default cluster, which Debian stupidly starts right after installation of the packages
RUN pg_dropcluster --stop ${PGVERSION} main

# install psycopg2
RUN apt-get install python-psycopg2 -y

# Set /home/postgres as a login directory for the PostgreSQL user.
RUN usermod -d /home/postgres -m postgres

# install WAL-e
RUN apt-get install build-essential -y
RUN apt-get install python-pip python-dev libxml2-dev libxslt-dev libffi-dev lzop pv daemontools -y
RUN pip install six --upgrade
RUN pip install wal-e

ENV ETCDVERSION 2.0.9
# install etcd
RUN apt-get install curl -y
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz -o etcd-v${ETCDVERSION}-linux-amd64.tar.gz && tar vzxf etcd-v${ETCDVERSION}-linux-amd64.tar.gz && cp etcd-v${ETCDVERSION}-linux-amd64/etcd* /bin/

# Install debug tooling
RUN apt-get install vim -y

ENV PATH $PATH:/usr/lib/postgresql-${PGVERSION}/bin

# Copy the snakeoil certificates for usage as dummy certificates
RUN cp /etc/ssl/private/ssl-cert-snakeoil.key /home/postgres/dummy.key && cp /etc/ssl/certs/ssl-cert-snakeoil.pem /home/postgres/dummy.crt

ADD postgres_ha.sh  /home/postgres/
RUN chown postgres:postgres /home/postgres -R
RUN chmod 700 /home/postgres/postgres_ha.sh

ENV ETCD_DISCOVERY_URL postgres.acid.example.com
ENV SCOPE test
ENV WAL_S3_BUCKET spilo-example-com
ENV DEBUG 0
ENV LC_ALL en_US.utf-8
# run subsequent commands as user postgres
USER postgres
WORKDIR /home/postgres
ENTRYPOINT ["/bin/bash", "/home/postgres/postgres_ha.sh"]
EXPOSE 5432


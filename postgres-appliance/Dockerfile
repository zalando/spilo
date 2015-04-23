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

ENV ETCDVERSION 2.0.9
# install etcd
RUN apt-get install curl -y
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz -o etcd-v${ETCDVERSION}-linux-amd64.tar.gz && tar vzxf etcd-v${ETCDVERSION}-linux-amd64.tar.gz && cp etcd-v${ETCDVERSION}-linux-amd64/etcd* /bin/

# install haproxy
RUN apt-get install haproxy

ENV PATH $PATH:/usr/lib/postgresql-${PGVERSION}/bin

ADD postgres_ha.sh /home/postgres/
RUN chown postgres:postgres /home/postgres/postgres_ha.sh
RUN chmod 700 /home/postgres/postgres_ha.sh

ENV ETCD_CLUSTER "default=http://127.0.0.1:7001"
ENV SCOPE "batman"
ENV DEBUG 0
# run subsequent commands as user postgres
USER postgres
WORKDIR /home/postgres
ENTRYPOINT ["/bin/bash", "/home/postgres/postgres_ha.sh"]
EXPOSE 5432


# vim:set ft=dockerfile:
FROM alpine:3.6
MAINTAINER Alexander Kukushkin <alexander.kukushkin@zalando.de>

ENV LANG en_US.utf8
ENV PGHOME=/home/postgres
ENV PGROOT=$PGHOME/pgdata/pgroot
ENV PGDATA=$PGROOT/data PGLOG=$PGROOT/pg_log WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env

RUN deluser postgres && addgroup -g 70 postgres && adduser -u 70 -h $PGHOME -s /bin/bash -S postgres

ENV PATRONIVERSION=1.3.5

RUN set -ex \
        && apk add --no-cache --virtual .spilo-rundeps \
                bash \
                curl \
                tzdata \
                openssl \
                less \
                libevent \
                libcurl \
                linux-pam \
                postgresql \
                postgresql-contrib \
                postgresql-plpython3 \
                python3 py3-gevent \
                py3-psycopg2 \
                py3-yaml \
                py3-requests \
                py3-six \
                py3-click \
                py3-dateutil \
                py3-psutil \
                py3-greenlet \
                py3-idna \
                py3-certifi \
                py3-chardet \
                py3-tz \
                py3-websocket-client \
                py3-ipaddress \
                py3-asn1 \
                py3-asn1-modules \
                py3-rsa \

        && apk add --no-cache --virtual .build-deps \
                git \
                tar \
                make \
                gcc \
                libc-dev \
                linux-headers \
                linux-pam-dev \
                curl-dev \
                postgresql-dev \
                libevent-dev \
                python3-dev \

        && mkdir -p /usr/src/tmpdir && cd /usr/src/tmpdir \

        # install bg_mon
        && export BG_MON_COMMIT=796690f2bee2778321a45233fe4012fc06b75f02 \
        && curl -s -L https://github.com/CyberDem0n/bg_mon/archive/$BG_MON_COMMIT.tar.gz | tar xz \
        && echo "#include <linux/limits.h>" > bg_mon-${BG_MON_COMMIT}/disk_stats.c.new \
        && cat bg_mon-${BG_MON_COMMIT}/disk_stats.c >> bg_mon-${BG_MON_COMMIT}/disk_stats.c.new \
        && mv bg_mon-${BG_MON_COMMIT}/disk_stats.c.new bg_mon-${BG_MON_COMMIT}/disk_stats.c \
        && make -C bg_mon-${BG_MON_COMMIT} USE_PGXS=1 clean install \

        # install pam_oauth2.so
        && export PAM_OAUTH_COMMIT=bed1f8d31840d1fda49365921449112a7421b8ca \
        && export JSMN_COMMIT=1682c32e9ae5990ddd0f0e907270a0f6dde5cbe9 \
        && curl -s -L https://github.com/CyberDem0n/pam-oauth2/archive/$PAM_OAUTH_COMMIT.tar.gz | tar xz \
        && cd pam-oauth2-$PAM_OAUTH_COMMIT \
        && curl -s -L https://github.com/zserge/jsmn/archive/$JSMN_COMMIT.tar.gz | tar xz \
        && rm -fr jsmn && mv jsmn-$JSMN_COMMIT jsmn \
        && make install \

        && pip3 install envdir wal-e pystache \
            'git+https://github.com/zalando/patroni.git@feature/k8s#egg=patroni[kubernetes,aws]' \
            'git+https://github.com/Supervisor/supervisor.git@master#egg=supervisor' \

        && sed -i 's/^\(    for i in range(0,\) num_retries):.*/\1 100):/g' /usr/lib/python3.6/site-packages/boto/utils.py \
        && echo 4.0.0.dev0 > /usr/lib/python3.6/site-packages/supervisor/version.txt \

        && mkdir /var/log/supervisor /run/postgresql \
        && chown postgres /run/postgresql \

        && apk del .build-deps \
        && cd / \
        && rm -rf /usr/src/tmpdir /root/.cache \
        && tar -cpjf usr.tar.bz2 usr \
        && rm -fr usr

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_endpoint.py basebackup.sh wale_restore_command.sh wal-e-wal-fetch.sh create_user_functions.sql /
ADD supervisor.d/patroni.conf supervisor.d/cron.conf /etc/supervisor/conf.d/
ADD motd supervisord.conf /etc/
RUN echo "source /etc/motd" >> /root/.bashrc
RUN echo "export TERM=linux\nexport LC_ALL=C.UTF-8\nexport LANG=C.UTF-8\nexport EDITOR=vi" >> /etc/bash.bashrc
RUN ln -s /etc/supervisord.conf /etc/supervisor/supervisord.conf
RUN chmod 700 /postgres_*
RUN chown -R postgres:postgres /postgres_* $PGHOME

WORKDIR $PGHOME
EXPOSE 5432 8008 8080
CMD ["/bin/sh", "/launch.sh"]

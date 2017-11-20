FROM spilo:squashed

MAINTAINER Alexander Kukushkin <alexander.kukushkin@zalando.de>

EXPOSE 5432 8008 8080

ENV ETCD_DISCOVERY_DOMAIN=postgres.acid.example.com \
    LC_ALL=en_US.utf-8 \
    PATH=$PATH:/usr/lib/postgresql/${PGVERSION}/bin \
    PGHOME=/home/postgres

ENV PGROOT=$PGHOME/pgdata/pgroot
ENV PGDATA=$PGROOT/data PGLOG=$PGROOT/pg_log WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env

WORKDIR $PGHOME

ADD motd /etc/
ADD supervisor /etc/supervisor
ADD pgq_ticker.ini $PGHOME/

RUN mkdir -p /var/log/supervisor \
        && ln -s supervisor/supervisord.conf /etc/supervisord.conf \
        && sed -i "s|/var/lib/postgresql.*|$PGHOME:/bin/bash|" /etc/passwd \
        && chown -R postgres:postgres $PGHOME \
        && sed -i 's/set compatible/set nocompatible/' /etc/vim/vimrc.tiny \
        && echo -e "export TERM=linux\nexport LC_ALL=C.UTF-8\nexport LANG=C.UTF-8\nexport EDITOR=vi" >> /etc/bash.bashrc \
        && echo "source /etc/motd" >> /root/.bashrc

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_*.py basebackup.sh wale_restore_command.sh wal-e-wal-fetch.sh create_user_functions.sql /

CMD ["/bin/sh", "/launch.sh"]

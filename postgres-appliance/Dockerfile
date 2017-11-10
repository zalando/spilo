FROM minispilo:squashed
MAINTAINER Alexander Kukushkin <alexander.kukushkin@zalando.de>

ENV PGHOME=/home/postgres
ENV PGROOT=$PGHOME/pgdata/pgroot
ENV PGDATA=$PGROOT/data PGLOG=$PGROOT/pg_log WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_*.py basebackup.sh wale_restore_command.sh wal-e-wal-fetch.sh create_user_functions.sql /
ADD supervisor.d /etc/supervisor/conf.d/
ADD motd supervisord.conf /etc/

RUN mkdir $PGHOME \
        && sed -i "s|/var/lib/postgresql.*|$PGHOME:/bin/bash|" /etc/passwd \
        && sed -i "s|:root:/root:.*|:root:/root:/bin/bash|" /etc/passwd \
        && echo -e "export TERM=linux\nexport LC_ALL=C.UTF-8\nexport LANG=C.UTF-8\nexport EDITOR=vi" >> /etc/bashrc \
        && echo -e "source /etc/bashrc\nsource /etc/motd" >> /root/.bashrc \
        && echo -e "source /etc/bashrc" >> $PGHOME/.bashrc \
        && ln -s /etc/supervisord.conf /etc/supervisor/supervisord.conf

ADD pgq_ticker.ini $PGHOME
RUN chown -R postgres:postgres /postgres_* $PGHOME \
    && chmod 700 /postgres_*

WORKDIR $PGHOME
EXPOSE 5432 8008 8080
CMD ["/bin/sh", "/launch.sh"]

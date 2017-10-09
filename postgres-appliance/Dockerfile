# vim:set ft=dockerfile:
FROM alpine:3.6
MAINTAINER Alexander Kukushkin <alexander.kukushkin@zalando.de>

ENV LANG=en_US.utf8 PGHOME=/home/postgres
ENV PGROOT=$PGHOME/pgdata/pgroot
ENV PGDATA=$PGROOT/data PGLOG=$PGROOT/pg_log WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env
ENV PG_VERSION=10.0 PG_SHA256=712f5592e27b81c5b454df96b258c14d94b6b03836831e015c65d6deeae57fd1
ENV PATRONIVERSION=1.3.5 POSTGIS=2.4.0 PROJ=4.9.3 GEOS=svn-3.6 GDAL=2.2.2

RUN set -ex \
        && cd / \
        && echo usr/bin/xz >> /exclude \
        && export saveDirs="usr lib bin sbin etc" \
        && for d in $saveDirs; do find $d -not -type d >> /exclude; done \
        && sed -i "s|/var/lib/postgresql.*|$PGHOME:/bin/bash|" /etc/passwd \
        && sed -i "s|:root:/root:.*|:root:/root:/bin/bash|" /etc/passwd \

        && apk add --no-cache --virtual .spilo-rundeps \
                bash \
                curl \
                jq \
                tzdata \
                openssl \
                less \
                libevent \
                libcurl \
                linux-pam \
                xz \
                python3 \
                py3-gevent \
# pulls libldap, libpq and so on
#               py3-psycopg2 \
                py3-yaml \
                py3-six \
                py3-click \
                py3-dateutil \
                py3-psutil \
                py3-greenlet \
                py3-idna \
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
                g++ \
                libc-dev \
                linux-headers \
                linux-pam-dev \
                curl-dev \
                libevent-dev \
                python3-dev \
                bison \
                coreutils \
                dpkg-dev dpkg \
                flex \
                file \
                libedit-dev \
                libxml2-dev \
                libxslt-dev \
                json-c-dev \
                protobuf-c-dev \
                openssl-dev \
                perl \
                perl-ipc-run \
                util-linux-dev \
                zlib-dev \
                libtool \
                autoconf \
                automake \
                python-dev \
                icu-dev \

        && wget -O postgresql.tar.bz2 "https://ftp.postgresql.org/pub/source/v$PG_VERSION/postgresql-$PG_VERSION.tar.bz2" \
        && echo "$PG_SHA256 *postgresql.tar.bz2" | sha256sum -c - \
        && mkdir -p /usr/src/postgresql \
        && tar \
                --extract \
                --file postgresql.tar.bz2 \
                --directory /usr/src/postgresql \
                --strip-components 1 \
        && rm postgresql.tar.bz2 \

        && cd /usr/src/postgresql \
# update "DEFAULT_PGSOCKET_DIR" to "/var/run/postgresql" (matching Debian)
# see https://anonscm.debian.org/git/pkg-postgresql/postgresql.git/tree/debian/patches/51-default-sockets-in-var.patch?id=8b539fcb3e093a521c095e70bdfa76887217b89f
        && awk '$1 == "#define" && $2 == "DEFAULT_PGSOCKET_DIR" && $3 == "\"/tmp\"" { $3 = "\"/var/run/postgresql\""; print; next } { print }' src/include/pg_config_manual.h > src/include/pg_config_manual.h.new \
        && grep '/var/run/postgresql' src/include/pg_config_manual.h.new \
        && mv src/include/pg_config_manual.h.new src/include/pg_config_manual.h \
        && gnuArch="$(dpkg-architecture --query DEB_BUILD_GNU_TYPE)" \
# explicitly update autoconf config.guess and config.sub so they support more arches/libcs
        && wget -O config/config.guess 'https://git.savannah.gnu.org/cgit/config.git/plain/config.guess?id=7d3d27baf8107b630586c962c057e22149653deb' \
        && wget -O config/config.sub 'https://git.savannah.gnu.org/cgit/config.git/plain/config.sub?id=7d3d27baf8107b630586c962c057e22149653deb' \
        && export PYTHON=/usr/bin/python3 \
# configure options taken from:
# https://anonscm.debian.org/cgit/pkg-postgresql/postgresql.git/tree/debian/rules?h=9.5
        && ./configure \
                --build="$gnuArch" \
# "/usr/src/postgresql/src/backend/access/common/tupconvert.c:105: undefined reference to `libintl_gettext'"
#               --enable-nls \
                --enable-integer-datetimes \
                --enable-thread-safety \
#               --enable-tap-tests \
# skip debugging info -- we want tiny size instead
#               --enable-debug \
                --disable-rpath \
                --with-uuid=e2fs \
                --with-gnu-ld \
                --with-pgport=5432 \
                --with-system-tzdata=/usr/share/zoneinfo \
                --prefix=/usr/local \
                --with-includes=/usr/local/include \
                --with-libraries=/usr/local/lib \
                \
# these make our image abnormally large (at least 100MB larger), which seems uncouth for an "Alpine" (ie, "small") variant :)
#               --with-krb5 \
#               --with-gssapi \
#               --with-ldap \
#               --with-tcl \
#               --with-perl \
                --with-icu \
                --with-python \
                --with-pam \
                --with-openssl \
                --with-libxml \
                --with-libxslt \
        && make -j "$(nproc)" install-strip \
        && make -j "$(nproc)" -C contrib install-strip \

        && cd /usr/src \
        && curl -sSL http://download.osgeo.org/proj/proj-${PROJ}.tar.gz | tar xz \
        && cd proj-${PROJ} \
        && ./configure --prefix=/usr/local --disable-static --without-mutex --without-jni \
        && export DESTDIR=/tmp/proj \
        && make -j "$(nproc)" && make install-strip \
        && cp -a /tmp/proj/usr/local/lib /tmp/proj/usr/local/include /usr/local/ \
        && cd /usr/src \

        && git clone --depth 1 -b $GEOS https://github.com/libgeos/libgeos \
        && cd libgeos \
        && ./autogen.sh \
        && ./configure --prefix=/usr/local --disable-static --disable-cassert --disable-glibcxx-debug --disable-python --disable-ruby \
        && unset DESTDIR \
        && make -j "$(nproc)" && make install-strip \
        && cd /usr/src \

        && curl -sSL http://download.osgeo.org/gdal/${GDAL}/gdal-${GDAL}.tar.xz | tar xJ \
        && cd gdal-${GDAL} \
        && ./configure --prefix=/usr/local --without-grib --without-mrf --without-pam --without-libtool --without-perl \
                --without-java --without-python --without-pcidsk --without-libz --without-qhull --without-curl \
                --without-png --without-gif --without-jpeg --without-jpeg12 --without-pcre --without-sqlite3 \
                --without-libkml --without-pg --without-pcraster --without-xml2 --disable-static \
        && export DESTDIR=/tmp/gdal \
        && make -j "$(nproc)" && make install \
        && strip  /tmp/gdal/usr/local/lib/libgdal.so \
        && cp -a /tmp/gdal/usr/local/lib /tmp/gdal/usr/local/include /usr/local/ \
        && cp -a /tmp/gdal/usr/local/bin/gdal-config  /usr/local/bin \
        && cd /usr/src \

        && curl -sSL http://download.osgeo.org/postgis/source/postgis-${POSTGIS}.tar.gz | tar xz \
        && cd postgis-${POSTGIS} \
        && ./configure --with-geosconfig=/usr/local/bin/geos-config \
        && export DESTDIR=/tmp/postgis \
        && make -j "$(nproc)" && make install \
        && strip /tmp/postgis/usr/local/lib/liblwgeom.so /tmp/postgis/usr/local/lib/postgresql/*.so \
        && cp -a /tmp/postgis/usr/local/share/postgresql /usr/local/share/ \
        && cp -a /tmp/postgis/usr/local/lib /tmp/postgis/usr/local/include /usr/local/ \
        && cd /usr/src \

        # install debezium decodebufs
        && export DECODEBUFS_COMMIT=d08a75593c68897600e10f5250133337624bcf63 \
        && curl -s -L https://github.com/debezium/postgres-decoderbufs/archive/$DECODEBUFS_COMMIT.tar.gz | tar xz \
        && make -C postgres-decoderbufs-$DECODEBUFS_COMMIT install-strip \

        # install pgq extension and pgqd
        && unset PYTHON \
        && unset DESTDIR \
        && git clone https://github.com/pgq/skytools-legacy.git \
        && cd skytools-legacy \
        && git submodule init \
        && git submodule update \
        && sed -i 's|parser/keywords.h|common/keywords.h|' sql/pgq/triggers/stringutil.c \
        && sed -i 's|^SUBDIRS .*|SUBDIRS = pgq ticker|' sql/Makefile \
        && ./autogen.sh \
        && ./configure \
        && make -C sql install \
        && strip /usr/local/lib/postgresql/pgq_*.so /usr/local/bin/pgqd \
        && cd /usr/src \

        # install plproxy
        && git clone https://github.com/plproxy/plproxy.git \
        && make -C plproxy install-strip \

        # install pg_repack
        && git clone https://github.com/reorg/pg_repack.git \
        && make -C pg_repack install \
        && strip /usr/local/lib/postgresql/pg_repack.so /usr/local/bin/pg_repack \

        # install bg_mon
        && export BG_MON_COMMIT=796690f2bee2778321a45233fe4012fc06b75f02 \
        && curl -sSL https://github.com/CyberDem0n/bg_mon/archive/$BG_MON_COMMIT.tar.gz | tar xz \
        && echo "#include <linux/limits.h>" > bg_mon-${BG_MON_COMMIT}/disk_stats.c.new \
        && cat bg_mon-${BG_MON_COMMIT}/disk_stats.c >> bg_mon-${BG_MON_COMMIT}/disk_stats.c.new \
        && mv bg_mon-${BG_MON_COMMIT}/disk_stats.c.new bg_mon-${BG_MON_COMMIT}/disk_stats.c \
        && make -C bg_mon-${BG_MON_COMMIT} USE_PGXS=1 install-strip \

        # install pg_cron
        && git clone https://github.com/citusdata/pg_cron.git \
        && sed -i 's/ -Werror//' pg_cron/Makefile \
        && make -C pg_cron install-strip \

        # install hypopg
        && git clone https://github.com/dalibo/hypopg.git \
        && make -C hypopg install-strip \

        # install set_user
        && git clone https://github.com/pgaudit/set_user.git \
        && make -C set_user USE_PGXS=1 install-strip \

        # install pam_oauth2.so
        && export PAM_OAUTH_COMMIT=bed1f8d31840d1fda49365921449112a7421b8ca \
        && export JSMN_COMMIT=1682c32e9ae5990ddd0f0e907270a0f6dde5cbe9 \
        && curl -sSL https://github.com/CyberDem0n/pam-oauth2/archive/$PAM_OAUTH_COMMIT.tar.gz | tar xz \
        && cd pam-oauth2-$PAM_OAUTH_COMMIT \
        && curl -sSL https://github.com/zserge/jsmn/archive/$JSMN_COMMIT.tar.gz | tar xz \
        && rm -fr jsmn && mv jsmn-$JSMN_COMMIT jsmn \
        && make install \
        && strip /lib/security/pam_oauth2.so \
        && cd /usr/src \

        && runDeps="$( \
                scanelf --needed --nobanner --format '%n#p' --recursive /usr/local | tr ',' '\n' | sort -u | awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
        )" \
        && apk add --no-cache --virtual .spilo-rundeps \
                $runDeps \

        && pip3 install --upgrade setuptools \
        && pip3 install envdir pystache \
            'git+https://github.com/zalando/patroni.git@feature/k8s#egg=patroni[kubernetes,aws]' \
            'git+https://github.com/Supervisor/supervisor.git@master#egg=supervisor' \
            'git+https://github.com/wal-e/wal-e@master#egg=wal-e[aws,google]' \

        && sed -i 's/^\(    for i in range(0,\) num_retries):.*/\1 100):/g' /usr/lib/python3.6/site-packages/boto/utils.py \
        && echo 4.0.0.dev0 > /usr/lib/python3.6/site-packages/supervisor/version.txt \

        && mkdir /var/log/supervisor /var/run/postgresql \
        && chown postgres:postgres /var/run/postgresql \
        && chmod 2777 /var/run/postgresql \

        && apk del .build-deps \
        && cd / \
        && for a in usr/lib/liblzma.so*; do echo $a >> /exclude; done \
        && rm -rf /tmp/* /usr/src /usr/local/include /usr/local/share/doc /usr/local/share/man /root/.cache \
# protobuf, protobuf-c
        rm usr/bin/protoc* usr/lib/libprotoc.so* usr/lib/libprotobuf-lite.so* usr/lib/libprotobuf.so* \
# libxslt
        && rm usr/bin/xsltproc usr/lib/libexslt.so* \
# libgcrypt
        && rm usr/bin/dumpsexp usr/bin/hmac256 usr/bin/mpicalc usr/lib/libgcrypt.so* \
# libgpg-error
        && rm usr/bin/gpg-error usr/lib/libgpg-error.so* \
# libevent
        && rm usr/lib/libevent_* \
        && find usr/local -name '*.a' -delete \
        && find usr/lib/python3.6/ -type d -name tests | xargs rm -fr \
        && find usr/lib/python3.6/ -type f -name 'test_*.py' -delete \
        && find usr/lib/python3.6/ -type f -name 'test_*.pyc' -delete \
        && find usr/lib/python3.6/ -type f -name 'unittest_*.py' -delete \
        && find usr/lib/python3.6/ -type f -name 'unittest_*.pyc' -delete \
        && find usr/lib/python3.6/ -type f -name '*_test.py' -delete \
        && find usr/lib/python3.6/ -type f -name '*_test.cpython*.pyc' -delete \

        && XZ_OPT=-e9v tar -X /exclude -cpJf a.tar.xz $saveDirs \
        && rm -fr /usr/lib/python* \
        && (for d in $saveDirs; do find $d -not -type d; done && cat /exclude /exclude && echo exclude) | sort | uniq -u | xargs rm \
        && for d in $saveDirs; do find $d -type d -depth -exec rmdir -p {} \; 2> /dev/null; done

ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_endpoint.py basebackup.sh wale_restore_command.sh wal-e-wal-fetch.sh create_user_functions.sql /
ADD supervisor.d /etc/supervisor/conf.d/
ADD motd supervisord.conf /etc/

RUN mkdir $PGHOME \
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

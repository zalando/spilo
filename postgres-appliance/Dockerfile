# vim:set ft=dockerfile:
FROM alpine:3.6
MAINTAINER Alexander Kukushkin <alexander.kukushkin@zalando.de>

ENV LANG en_US.utf8
ENV PGHOME=/home/postgres
ENV PGROOT=$PGHOME/pgdata/pgroot
ENV PGDATA=$PGROOT/data PGLOG=$PGROOT/pg_log WALE_ENV_DIR=$PGHOME/etc/wal-e.d/env

RUN deluser postgres && addgroup -g 70 postgres && adduser -u 70 -h $PGHOME -s /bin/bash -S postgres

ENV PATRONIVERSION=1.3.5

ENV PG_MAJOR 10
ENV PG_VERSION 10.0
ENV PG_SHA256 712f5592e27b81c5b454df96b258c14d94b6b03836831e015c65d6deeae57fd1

RUN set -ex \
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
                libevent-dev \
                python3-dev \
                bison \
                coreutils \
                dpkg-dev dpkg \
                flex \
                libedit-dev \
                libxml2-dev \
                libxslt-dev \
                openssl-dev \
                perl \
                perl-ipc-run \
                util-linux-dev \
                zlib-dev \
                libtool \
                autoconf \
                automake \
                python-dev \

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
#		--enable-nls \
		--enable-integer-datetimes \
		--enable-thread-safety \
#		--enable-tap-tests \
# skip debugging info -- we want tiny size instead
#		--enable-debug \
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
#		--with-krb5 \
#		--with-gssapi \
#		--with-ldap \
#		--with-tcl \
#		--with-perl \
		--with-python \
		--with-pam \
		--with-openssl \
		--with-libxml \
		--with-libxslt \
	&& make -j "$(nproc)" world \
	&& make install-world \
	&& make -C contrib install \
	\
	&& runDeps="$( \
		scanelf --needed --nobanner --format '%n#p' --recursive /usr/local \
			| tr ',' '\n' \
			| sort -u \
			| awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
	)" \
        && echo $runDeps \
	&& apk add --no-cache --virtual .postgresql-rundeps \
		$runDeps \

        && cd /usr/src \

        # install pgq extension and pgqd
        && unset PYTHON \
        && git clone https://github.com/pgq/skytools-legacy.git \
        && cd skytools-legacy \
        && git submodule init \
        && git submodule update \
        && sed -i 's|parser/keywords.h|common/keywords.h|' sql/pgq/triggers/stringutil.c \
        && sed -i 's|^SUBDIRS .*|SUBDIRS = pgq ticker|' sql/Makefile \
        && ./autogen.sh \
        && ./configure \
        && make -C sql install \
        && cd .. \

        # install pg_repack
        && git clone https://github.com/reorg/pg_repack.git \
        && make -C pg_repack install \

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

        && mkdir /var/log/supervisor /var/run/postgresql \
        && chown postgres:postgres /var/run/postgresql \
        && chmod 2777 /var/run/postgresql \

        && apk del .build-deps \
        && cd / \
        && rm -rf /usr/src /usr/local/share/doc /usr/local/share/man /root/.cache \
        && find /usr/local -name '*.a' -delete \
        && tar -cpJf usr.tar.xz usr \
        && cp -a usr/bin/xz /usr/lib/liblzma.so* /tmp \
        && rm -fr usr \
        && mkdir -p usr/bin usr/lib \
        && mv /tmp/liblzma.so* usr/lib/ \
        && mv /tmp/xz usr/bin/


ADD scm-source.json configure_spilo.py launch.sh postgres_backup.sh patroni_wait.sh post_init.sh _zmon_schema.dump callback_endpoint.py basebackup.sh wale_restore_command.sh wal-e-wal-fetch.sh create_user_functions.sql /
ADD pgq_ticker.ini $PGHOME
ADD supervisor.d /etc/supervisor/conf.d/
ADD motd supervisord.conf /etc/
RUN echo "source /etc/motd" >> /root/.bashrc
RUN echo "export TERM=linux\nexport LC_ALL=C.UTF-8\nexport LANG=C.UTF-8\nexport EDITOR=vi" >> /etc/bash.bashrc
RUN ln -s /etc/supervisord.conf /etc/supervisor/supervisord.conf
RUN chmod 700 /postgres_*
RUN chown -R postgres:postgres /postgres_* $PGHOME

WORKDIR $PGHOME
EXPOSE 5432 8008 8080
CMD ["/bin/sh", "/launch.sh"]

#!/bin/bash

export DEBIAN_FRONTEND=noninteractive

echo -e 'APT::Install-Recommends "0";\nAPT::Install-Suggests "0";' > /etc/apt/apt.conf.d/01norecommend

apt-get update
apt-get -y upgrade
apt-get install -y curl ca-certificates less locales jq vim-tiny gnupg1 cron runit dumb-init libcap2-bin rsync sysstat

ln -s chpst /usr/bin/envdir

# Make it possible to use the following utilities without root (if container runs without "no-new-privileges:true")
setcap 'cap_sys_nice+ep' /usr/bin/chrt
setcap 'cap_sys_nice+ep' /usr/bin/renice

# Disable unwanted cron jobs
rm -fr /etc/cron.??*
truncate --size 0 /etc/crontab

if [ "$DEMO" != "true" ]; then
    # Required for wal-e
    apt-get install -y pv lzop
    # install etcdctl
    ETCDVERSION=3.3.27
    curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-"$(dpkg --print-architecture)".tar.gz \
                | tar xz -C /bin --strip=1 --wildcards --no-anchored --no-same-owner etcdctl etcd
fi

# Cleanup all locales but en_US.UTF-8 and optionally specified in ADDITIONAL_LOCALES arg
find /usr/share/i18n/charmaps/ -type f ! -name UTF-8.gz -delete

# Prepare find expression for locales
LOCALE_FIND_EXPR="-type f"
for loc in en_US en_GB $ADDITIONAL_LOCALES "i18n*" iso14651_t1 iso14651_t1_common "translit_*"; do
    LOCALE_FIND_EXPR="$LOCALE_FIND_EXPR ! -name $loc"
done
find /usr/share/i18n/locales/ "$LOCALE_FIND_EXPR" -delete

# Make sure we have the en_US.UTF-8 and all additional locales available
truncate --size 0 /usr/share/i18n/SUPPORTED
for loc in en_US $ADDITIONAL_LOCALES; do
    echo "$loc.UTF-8 UTF-8" >> /usr/share/i18n/SUPPORTED
    localedef -i "$loc" -c -f UTF-8 -A /usr/share/locale/locale.alias "$loc.UTF-8"
done

# Add PGDG repositories
DISTRIB_CODENAME=$(sed -n 's/DISTRIB_CODENAME=//p' /etc/lsb-release)
for t in deb deb-src; do
    echo "$t http://apt.postgresql.org/pub/repos/apt/ ${DISTRIB_CODENAME}-pgdg main" >> /etc/apt/sources.list.d/pgdg.list
done
curl -s -o - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

# Clean up
apt-get purge -y libcap2-bin
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/* \
            /var/cache/debconf/* \
            /usr/share/doc \
            /usr/share/man \
            /usr/share/locale/?? \
            /usr/share/locale/??_??
find /var/log -type f -exec truncate --size 0 {} \;

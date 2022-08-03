#!/bin/bash

set -ex

apt-get update
apt-get install -y busybox xz-utils
apt-get clean

rm -rf /var/lib/apt/lists/* /var/cache/debconf/* /usr/share/doc /usr/share/man /etc/rc?.d /etc/systemd
ln -snf busybox /bin/sh

files="/bin/sh"
arch=$(uname -m)
darch=$(uname -m | sed 's/_/-/')

IFS=" " read -r -a libs <<< "$(ldd $files | awk '{print $3;}' | grep '^/' | sort -u)"
libs+=(/lib/ld-linux-"$darch".so.* \
    /lib/"$arch"-linux-gnu/ld-linux-"$darch".so.* \
    /lib/"$arch"-linux-gnu/libnsl.so.* \
    /lib/"$arch"-linux-gnu/libnss_compat.so.*)

(echo /var/run /var/spool "$files" "${libs[@]}" | tr ' ' '\n' && realpath "$files" "${libs[@]}") | sort -u | sed 's/^\///' > /exclude

find /etc/alternatives -xtype l -delete
save_dirs=(usr lib var bin sbin etc/ssl etc/init.d etc/alternatives etc/apt)
XZ_OPT=-e9v tar -X /exclude -cpJf a.tar.xz "${save_dirs[@]}"

rm -fr /usr/local/lib/python*

/bin/busybox sh -c "(find ${save_dirs[*]} -not -type d && cat /exclude /exclude && echo exclude) | sort | uniq -u | xargs /bin/busybox rm"
/bin/busybox --install -s
/bin/busybox sh -c "find ${save_dirs[*]} -type d -depth -exec rmdir -p {}; 2> /dev/null"

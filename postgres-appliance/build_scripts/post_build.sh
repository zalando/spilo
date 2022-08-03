#!/bin/sh

set -ex

sed -i "s|/var/lib/postgresql.*|$PGHOME:/bin/bash|" /etc/passwd

chown -R postgres:postgres "$PGHOME" "$RW_DIR"

rm -fr /var/spool/cron /var/tmp
mkdir -p /var/spool
ln -s "$RW_DIR/cron" /var/spool/cron
ln -s "$RW_DIR/tmp" /var/tmp

for d in /etc/service/*; do
    chmod 755 "$d"/*
    ln -s /run/supervise/"$(basename "$d")" "$d/supervise"
done

ln -snf "$RW_DIR/service" /etc/service
ln -s "$RW_DIR/pam.d-postgresql" /etc/pam.d/postgresql
ln -s "$RW_DIR/postgres.yml" "$PGHOME/postgres.yml"
ln -s "$RW_DIR/.bash_history" /root/.bash_history
ln -s "$RW_DIR/postgresql/.bash_history" "$PGHOME/.bash_history"
ln -s "$RW_DIR/postgresql/.psql_history" "$PGHOME/.psql_history"
ln -s "$RW_DIR/etc" "$PGHOME/etc"

for d in "$PGHOME" /root; do
    d="$d/.config/patroni"
    mkdir -p "$d"
    ln -s "$PGHOME/postgres.yml" "$d/patronictl.yaml"
done

sed -i 's/set compatible/set nocompatible/' /etc/vim/vimrc.tiny

echo "PATH=\"$PATH\"" > /etc/environment

for e in TERM=linux LC_ALL=C.UTF-8 LANG=C.UTF-8 EDITOR=editor;
    do echo "export $e" >> /etc/bash.bashrc
done
ln -s /etc/skel/.bashrc "$PGHOME/.bashrc"
echo "source /etc/motd" >> /root/.bashrc

# Allow users in the root group to access the following files and dirs
if [ "$COMPRESS" != "true" ]; then
    chmod 664 /etc/passwd
    chmod o+r /etc/shadow
    chgrp -R 0 "$PGHOME" "$RW_DIR"
    chmod -R g=u "$PGHOME" "$RW_DIR"
    usermod -a -G root postgres
fi

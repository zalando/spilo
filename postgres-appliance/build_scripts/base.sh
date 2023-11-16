#!/bin/bash

## -------------------------------------------
## Install PostgreSQL, extensions and contribs
## -------------------------------------------

export DEBIAN_FRONTEND=noninteractive
MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)"
export MAKEFLAGS

set -ex
sed -i 's/^#\s*\(deb.*universe\)$/\1/g' /etc/apt/sources.list

apt-get update


# Install packages required for the builds
BUILD_PACKAGES=(devscripts equivs build-essential fakeroot debhelper git gcc libc6-dev make cmake libevent-dev libbrotli-dev libssl-dev libkrb5-dev)
if [ "$DEMO" = "true" ]; then
    export DEB_PG_SUPPORTED_VERSIONS="$PGVERSION"
    WITH_PERL=false
    rm -f ./*.deb
    apt-get install -y "${BUILD_PACKAGES[@]}"
else
    BUILD_PACKAGES+=(zlib1g-dev
                    libprotobuf-c-dev
                    libpam0g-dev
                    libcurl4-openssl-dev
                    libicu-dev
                    libc-ares-dev
                    pandoc
                    pkg-config)
    apt-get install -y "${BUILD_PACKAGES[@]}" libcurl4

    # TODO: comment
    for p in python3-keyring python3-docutils ieee-data; do
        version=$(apt-cache show $p | sed -n 's/^Version: //p' | sort -rV | head -n 1)
        printf "Section: misc\nPriority: optional\nStandards-Version: 3.9.8\nPackage: %s\nVersion: %s\nDescription: %s" "$p" "$version" "$p" > "$p"
        equivs-build "$p"
    done

    # Prepare PG extensions sources (non-demo) only required for the full image
    EXTRA_BUILD_COMMIT_TAG_EXT=($(jq -r ".postgresql_extensions_source.commit_tag.extra | to_entries | map(\"\(.key)\") | @sh" pinned_versions.json | sed -e "s/'/ /g"))
    for ext in "${EXTRA_BUILD_COMMIT_TAG_EXT[@]}"; do
        url=$(jq -r ".postgresql_extensions_source.commit_tag.extra.${ext} | \"\(.repo)/archive/\(.version).tar.gz\"" pinned_versions.json)
        curl -sL "$url" | tar xz
    done

    EXTRA_BUILD_BRANCH_EXT=($(jq -r ".postgresql_extensions_source.branch.extra | to_entries | map(\"\(.key)\") | @sh" pinned_versions.json | sed -e "s/'/ /g"))
    for ext in "${EXTRA_BUILD_BRANCH_EXT[@]}"; do
        branch=$(jq -r ".postgresql_extensions_source.branch.extra.\"${ext}\".version" pinned_versions.json)
        repo=$(jq -r ".postgresql_extensions_source.branch.extra.\"${ext}\".repo" pinned_versions.json)
        git clone -b "$branch" --recurse-submodules "$repo" "${ext}-${branch}"
    done

    pam_oauth_branch=$(jq -r ".\"pam-oauth2\".version" pinned_versions.json)
    pam_oauth_repo=$(jq -r ".\"pam-oauth2\".repo" pinned_versions.json)
    git clone -b "$pam_oauth_branch" --recurse-submodules "$pam_oauth_repo"
    make -C pam-oauth2 install # build pam_oauth2 straight away
fi


# TODO: comment
if [ "$WITH_PERL" != "true" ]; then
    version=$(apt-cache show perl | sed -n 's/^Version: //p' | sort -rV | head -n 1)
    printf "Priority: standard\nStandards-Version: 3.9.8\nPackage: perl\nMulti-Arch: allowed\nReplaces: perl-base, perl-modules\nVersion: %s\nDescription: perl" "$version" > perl
    equivs-build perl
fi

# Prepare srouces for PG extensions available in both demo and full image
BASE_BUILD_COMMIT_TAG_EXT=($(jq -r ".postgresql_extensions_source.commit_tag.base | to_entries | map(\"\(.key)\") | @sh" pinned_versions.json | sed -e "s/'/ /g"))
for ext in "${BASE_BUILD_COMMIT_TAG_EXT[@]}"; do
    url=$(jq -r ".postgresql_extensions_source.commit_tag.base.${ext} | \"\(.repo)/archive/\(.version).tar.gz\"" pinned_versions.json)
    curl -sL "$url" | tar xz
done

BASE_BUILD_BRANCH_EXT=($(jq -r ".postgresql_extensions_source.branch.base | to_entries | map(\"\(.key)\") | @sh" pinned_versions.json | sed -e "s/'/ /g"))
for ext in "${BASE_BUILD_BRANCH_EXT[@]}"; do
    branch=$(jq -r ".postgresql_extensions_source.branch.base.\"${ext}\".version" pinned_versions.json)
    repo=$(jq -r ".postgresql_extensions_source.branch.base.\"${ext}\".repo" pinned_versions.json)
    git clone -b "$branch" --recurse-submodules "$repo" "${ext}-${branch}"
done

timescaledb_repo=$(jq -r ".postgresql_extensions_source.timescaledb.repo" pinned_versions.json)
git clone "${timescaledb_repo}.git"


# Install base packages
apt-get install -y \
    postgresql-common \
    libevent-2.1 \
    libevent-pthreads-2.1 \
    brotli \
    libbrotli1 \
    python3.10 \
    python3-psycopg2

# forbid creation of a main cluster when package is installed
sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf

# Install/build PG extensions for each supported major version
for version in $DEB_PG_SUPPORTED_VERSIONS; do
    sed -i "s/ main.*$/ main $version/g" /etc/apt/sources.list.d/pgdg.list
    apt-get update
    minor_version=$(jq -r ".postgresql_pgdg.\"${version}\"" pinned_versions.json)

    # Base extensions available in both demo and full image
    BASE_EXT=($(jq -r ".postgresql_extensions_pgdg.\"${version}\".base | to_entries | map(\"postgresql-${version}-\(.key)=\(.value).pgdg22.04+1\") | @sh" pinned_versions.json | sed -e "s/'/ /g"))

    # Extra extensions installed in the full image
    if [ "$DEMO" != "true" ]; then
        EXTRA_EXT=($(jq -r ".postgresql_extensions_pgdg.\"${version}\".extra | to_entries | map(\"postgresql-${version}-\(.key)=\(.value).pgdg22.04+1\") | @sh" pinned_versions.json | sed -e "s/'/ /g"))
        EXTRA_EXT+=("postgresql-pltcl-${version}=${minor_version}.pgdg22.04+1")

        if [ "$WITH_PERL" = "true" ]; then
            EXTRA_EXT+=("postgresql-plperl-${version}=${minor_version}.pgdg22.04+1")
        fi
    fi

    # Now install everything defined
    apt-get install --allow-downgrades -y \
        "postgresql-plpython3-${version}=${minor_version}.pgdg22.04+1" \
        "postgresql-server-dev-${version}=${minor_version}.pgdg22.04+1" \
        "${BASE_EXT[@]}" \
        "${EXTRA_EXT[@]}" \
        # "postgresql-contrib-${version}"

    # build timescaledb
    # use subshell to avoid having to cd back (SC2103)
    (
        cd timescaledb
        if [ "$version" != "16" ]; then
            for v in $(jq -r ".postgresql_extensions_source.timescaledb.version" ../pinned_versions.json); do
                git checkout "$v"
                sed -i "s/VERSION 3.11/VERSION 3.10/" CMakeLists.txt
                if BUILD_FORCE_REMOVE=true ./bootstrap -DREGRESS_CHECKS=OFF -DWARNINGS_AS_ERRORS=OFF \
                        -DTAP_CHECKS=OFF -DPG_CONFIG="/usr/lib/postgresql/$version/bin/pg_config" \
                        -DAPACHE_ONLY="$TIMESCALEDB_APACHE_ONLY" -DSEND_TELEMETRY_DEFAULT=NO; then
                    make -C build install
                    strip /usr/lib/postgresql/"$version"/lib/timescaledb*.so
                fi
                git reset --hard
                git clean -f -d
            done
        fi
    )

    if [ "${TIMESCALEDB_APACHE_ONLY}" != "true" ] && [ "${TIMESCALEDB_TOOLKIT}" = "true" ]; then
        __versionCodename=$(sed </etc/os-release -ne 's/^VERSION_CODENAME=//p')
        echo "deb [signed-by=/usr/share/keyrings/timescale_E7391C94080429FF.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ ${__versionCodename} main" | tee /etc/apt/sources.list.d/timescaledb.list
        curl -L https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor > /usr/share/keyrings/timescale_E7391C94080429FF.gpg

        apt-get update
        if [ "$(apt-cache search --names-only "^timescaledb-toolkit-postgresql-${version}$" | wc -l)" -eq 1 ]; then
            apt-get install "timescaledb-toolkit-postgresql-$version"
        else
            echo "Skipping timescaledb-toolkit-postgresql-$version as it's not found in the repository"
        fi

        rm /etc/apt/sources.list.d/timescaledb.list
        rm /usr/share/keyrings/timescale_E7391C94080429FF.gpg
    fi

    # Build extensions from source
    for repo in "${EXTRA_BUILD_COMMIT_TAG_EXT[@]}" \
                "${EXTRA_BUILD_BRANCH_EXT[@]}" \
                "${BASE_BUILD_COMMIT_TAG_EXT[@]}" \
                "${BASE_BUILD_BRANCH_EXT[@]}"; do
        dir=$(jq -r ".. | select(.\"${repo}\"?).\"${repo}\" | \"${repo}-\(.version)\"" pinned_versions.json)
        make -C "$dir" USE_PGXS=1 clean install-strip
    done
done

apt-get install -y skytools3-ticker pgbouncer

# TODO: comment
sed -i "s/ main.*$/ main/g" /etc/apt/sources.list.d/pgdg.list
apt-get update
apt-get install -y postgresql postgresql-server-dev-all postgresql-all libpq-dev
for version in $DEB_PG_SUPPORTED_VERSIONS; do
    minor_version=$(jq -r ".postgresql_pgdg.\"${version}\"" pinned_versions.json)
    apt-get install -y "postgresql-server-dev-${version}=${minor_version}.pgdg22.04+1"
done

# make it possible for cron to work without root
gcc -s -shared -fPIC -o /usr/local/lib/cron_unprivileged.so cron_unprivileged.c

apt-get purge -y "${BUILD_PACKAGES[@]}"
apt-get autoremove -y

# TODO: comment
if [ "$WITH_PERL" != "true" ] || [ "$DEMO" != "true" ]; then
    dpkg -i ./*.deb || apt-get -y -f install
fi

# Remove unnecessary packages
apt-get purge -y \
                libdpkg-perl \
                libperl5.* \
                perl-modules-5.* \
                postgresql \
                postgresql-all \
                postgresql-server-dev-* \
                libpq-dev=* \
                libmagic1 \
                bsdmainutils
apt-get autoremove -y
apt-get clean
dpkg -l | grep '^rc' | awk '{print $2}' | xargs apt-get purge -y

# Try to minimize size by creating symlinks instead of duplicate files
if [ "$DEMO" != "true" ]; then
    POSTGIS_VERSION=$(jq -r ".postgresql_extensions_pgdg.\"12\".extra.\"postgis-3\"" pinned_versions.json)
    POSTGIS_LEGACY=$(jq -r ".postgresql_extensions_pgdg.\"11\".extra.\"postgis-3\"" pinned_versions.json)
    cd "/usr/lib/postgresql/$PGVERSION/bin"
    for u in clusterdb \
            pg_archivecleanup \
            pg_basebackup \
            pg_isready \
            pg_recvlogical \
            pg_test_fsync \
            pg_test_timing \
            pgbench \
            reindexdb \
            vacuumlo *.py; do
        for v in /usr/lib/postgresql/*; do
            if [ "$v" != "/usr/lib/postgresql/$PGVERSION" ] && [ -f "$v/bin/$u" ]; then
                rm "$v/bin/$u"
                ln -s "../../$PGVERSION/bin/$u" "$v/bin/$u"
            fi
        done
    done

    set +x

    for v1 in $(find /usr/share/postgresql -type d -mindepth 1 -maxdepth 1 | sort -Vr); do
        # relink files with the same content
        cd "$v1/extension"
        while IFS= read -r -d '' orig
        do
            for f in "${orig%.sql}"--*.sql; do
                if [ ! -L "$f" ] && diff "$orig" "$f" > /dev/null; then
                    echo "creating symlink $f -> $orig"
                    rm "$f" && ln -s "$orig" "$f"
                fi
            done
        done <  <(find . -type f -maxdepth 1 -name '*.sql' -not -name '*--*')

        for e in pgq pgq_node plproxy address_standardizer address_standardizer_data_us; do
            orig=$(basename "$(find . -maxdepth 1 -type f -name "$e--*--*.sql" | head -n1)")
            if [ "x$orig" != "x" ]; then
                for f in "$e"--*--*.sql; do
                    if [ "$f" != "$orig" ] && [ ! -L "$f" ] && diff "$f" "$orig" > /dev/null; then
                        echo "creating symlink $f -> $orig"
                        rm "$f" && ln -s "$orig" "$f"
                    fi
                done
            fi
        done

        # relink files with the same name and content across different major versions
        started=0
        for v2 in $(find /usr/share/postgresql -type d -mindepth 1 -maxdepth 1 | sort -Vr); do
            if [ "$v1" = "$v2" ]; then
                started=1
            elif [ $started = 1 ]; then
                for d1 in extension contrib contrib/postgis-${POSTGIS_VERSION%.*}; do
                    cd "$v1/$d1"
                    d2="$d1"
                    d1="../../${v1##*/}/$d1"
                    if [ "${d2%-*}" = "contrib/postgis" ]; then
                        if [ "${v2##*/}" = "11" ]; then d2="${d2%-*}-${POSTGIS_VERSION%.*}"; fi
                        d1="../$d1"
                    fi
                    d2="$v2/$d2"
                    for f in *.html *.sql *.control *.pl; do
                        if [ -f "$d2/$f" ] && [ ! -L "$d2/$f" ] && diff "$d2/$f" "$f" > /dev/null; then
                            echo "creating symlink $d2/$f -> $d1/$f"
                            rm "$d2/$f" && ln -s "$d1/$f" "$d2/$f"
                        fi
                    done
                done
            fi
        done
    done
    set -x
fi

# Clean up
rm -rf /var/lib/apt/lists/* \
        /var/cache/debconf/* \
        /builddeps \
        /usr/share/doc \
        /usr/share/man \
        /usr/share/info \
        /usr/share/locale/?? \
        /usr/share/locale/??_?? \
        /usr/share/postgresql/*/man \
        /etc/pgbouncer/* \
        /usr/lib/postgresql/*/bin/createdb \
        /usr/lib/postgresql/*/bin/createlang \
        /usr/lib/postgresql/*/bin/createuser \
        /usr/lib/postgresql/*/bin/dropdb \
        /usr/lib/postgresql/*/bin/droplang \
        /usr/lib/postgresql/*/bin/dropuser \
        /usr/lib/postgresql/*/bin/pg_standby \
        /usr/lib/postgresql/*/bin/pltcl_*
find /var/log -type f -exec truncate --size 0 {} \;

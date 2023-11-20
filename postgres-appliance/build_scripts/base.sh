#!/bin/bash

## -------------------------------------------
## Install PostgreSQL, extensions and contribs
## -------------------------------------------


## Auxiliary functions and vars ##
export DEBIAN_FRONTEND=noninteractive
MAKEFLAGS="-j $(grep -c ^processor /proc/cpuinfo)"
export MAKEFLAGS

set -ex

VER_FILE='pinned_versions.json'

function get_list_from_entries() {
    local path=$1
    local map_pattern=$2
    jq -r "${path} | to_entries | map(\"${map_pattern}\") | @sh" "$VER_FILE" | sed -e "s/'/ /g"
}

function get_exts_source() {
    local suffix=$1
    get_list_from_entries ".postgresql_extensions_source.${suffix}" '\(.key)'
}

function get_exts_pgdg() {
    local version=$1
    local suffix=$2
    get_list_from_entries ".postgresql_extensions_pgdg.\"${version}\".${suffix}" "postgresql-${version}-\(.key)=\(.value).pgdg22.04+1"
}

function get_ext_source_branch_repo() {
    local ext=$1
    local suffix=$2
    jq -r ".postgresql_extensions_source.branch.${suffix}.\"${ext}\".repo" "$VER_FILE"
}

function get_ext_source_branch_version() {
    local ext=$1
    local suffix=$2
    jq -r ".postgresql_extensions_source.branch.${suffix}.\"${ext}\".version" "$VER_FILE"
}

function get_ext_source_commit_tag_url() {
    local ext=$1
    local suffix=$2
    jq -r ".postgresql_extensions_source.commit_tag.${suffix}.${ext} | \"\(.repo)/archive/\(.version).tar.gz\"" "$VER_FILE"
}



## Prepare everything required for the builds ##
apt-get update

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

    # Prepare "fake" packages
    for p in python3-keyring python3-docutils ieee-data; do
        version=$(apt-cache show $p | sed -n 's/^Version: //p' | sort -rV | head -n 1)
        printf "Section: misc\nPriority: optional\nStandards-Version: 3.9.8\nPackage: %s\nVersion: %s\nDescription: %s" "$p" "$version" "$p" > "$p"
        equivs-build "$p"
    done

    # PG extensions sources
    EXTRA_BUILD_COMMIT_TAG_EXT=($(get_exts_source 'commit_tag.extra'))
    for ext in "${EXTRA_BUILD_COMMIT_TAG_EXT[@]}"; do
        url=$(get_ext_source_commit_tag_url "$ext" 'extra')
        curl -sL "$url" | tar xz
    done

    EXTRA_BUILD_BRANCH_EXT=($(get_exts_source 'branch.extra'))
    for ext in "${EXTRA_BUILD_BRANCH_EXT[@]}"; do
        branch=$(get_ext_source_branch_version "$ext" 'extra')
        repo=$(get_ext_source_branch_repo "$ext" 'extra')
        git clone -b "$branch" --recurse-submodules "$repo" "${ext}-${branch}"
    done

    # Build pam_oauth2 straight away
    pam_oauth_branch=$(jq -r ".\"pam-oauth2\".version" "$VER_FILE")
    pam_oauth_repo=$(jq -r ".\"pam-oauth2\".repo" "$VER_FILE")
    git clone -b "$pam_oauth_branch" --recurse-submodules "$pam_oauth_repo"
    make -C pam-oauth2 install
fi

# If perl is not required, prepare a "fake" package
if [ "$WITH_PERL" != "true" ]; then
    version=$(apt-cache show perl | sed -n 's/^Version: //p' | sort -rV | head -n 1)
    printf "Priority: standard\nStandards-Version: 3.9.8\nPackage: perl\nMulti-Arch: allowed\nReplaces: perl-base, perl-modules\nVersion: %s\nDescription: perl" "$version" > perl
    equivs-build perl
fi

# PG extensions sources (available in both demo and full image)
BASE_BUILD_COMMIT_TAG_EXT=($(get_exts_source 'commit_tag.base'))
for ext in "${BASE_BUILD_COMMIT_TAG_EXT[@]}"; do
    url=$(get_ext_source_commit_tag_url "$ext" 'base')
    curl -sL "$url" | tar xz
done

BASE_BUILD_BRANCH_EXT=($(get_exts_source 'branch.base'))
for ext in "${BASE_BUILD_BRANCH_EXT[@]}"; do
    branch=$(get_ext_source_branch_version "$ext" 'base')
    repo=$(get_ext_source_branch_repo "$ext" 'base')
    git clone -b "$branch" --recurse-submodules "$repo" "${ext}-${branch}"
done

# Clone timescaldb in case there is no package for the required version available
git clone https://github.com/timescale/timescaledb.git



## Install packages / build extensions ##
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

# Install/build components for each supported major version
for version in $DEB_PG_SUPPORTED_VERSIONS; do
    sed -i "s/ main.*$/ main $version/g" /etc/apt/sources.list.d/pgdg.list
    apt-get update
    minor_version=$(jq -r ".postgresql_pgdg.\"${version}\"" "$VER_FILE")

    # Extensions for both demo and full image available in pgdg
    BASE_EXT=($(get_exts_pgdg "$version" 'base'))

    # Extensions for the full image only vailable in pgdg
    if [ "$DEMO" != "true" ]; then
        EXTRA_EXT=($(get_exts_pgdg "$version" 'extra'))
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
        "${EXTRA_EXT[@]}"

    # Install/build timescaledb
    ts_versions=($(jq -r ".timescaledb_pkg.\"${version}\"" "$VER_FILE"))
    if [ "$version" != "16" ]; then
        for v in "${ts_versions[@]}"; do
            if [ "${TIMESCALEDB_APACHE_ONLY}" != "true" ]; then
                pkg="timescaledb-2-${v}-postgresql-${version}"
            else
                pkg="timescaledb-2-oss-${v}-postgresql-${version}"
            fi
            if [ "$(apt-cache search --names-only "^${pkg}$" | wc -l)" -eq 1 ]; then
                apt-get install -y "$pkg"
            else
                # use subshell to avoid having to cd back (SC2103)
                (
                    cd timescaledb
                    git checkout "$v"
                    if BUILD_FORCE_REMOVE=true ./bootstrap -DREGRESS_CHECKS=OFF -DWARNINGS_AS_ERRORS=OFF \
                            -DTAP_CHECKS=OFF -DPG_CONFIG="/usr/lib/postgresql/$version/bin/pg_config" \
                            -DAPACHE_ONLY="$TIMESCALEDB_APACHE_ONLY" -DSEND_TELEMETRY_DEFAULT=NO; then
                        make -C build install
                        strip /usr/lib/postgresql/"$version"/lib/timescaledb*.so
                    fi
                    git reset --hard
                    git clean -f -d
                )
            fi
        done
    fi

    if [ "${TIMESCALEDB_APACHE_ONLY}" != "true" ] && [ "${TIMESCALEDB_TOOLKIT}" = "true" ]; then
        if [ "$(apt-cache search --names-only "^timescaledb-toolkit-postgresql-${version}$" | wc -l)" -eq 1 ]; then
            apt-get install "timescaledb-toolkit-postgresql-$version"
        else
            echo "Skipping timescaledb-toolkit-postgresql-$version as it's not found in the repository"
        fi
    fi

    # Build extensions from source
    for repo in "${EXTRA_BUILD_COMMIT_TAG_EXT[@]}" \
                "${EXTRA_BUILD_BRANCH_EXT[@]}" \
                "${BASE_BUILD_COMMIT_TAG_EXT[@]}" \
                "${BASE_BUILD_BRANCH_EXT[@]}"; do
        dir=$(jq -r ".. | select(.\"${repo}\"?).\"${repo}\" | \"${repo}-\(.version)\"" "$VER_FILE")
        make -C "$dir" USE_PGXS=1 clean install-strip
    done
done

# Install components that don't depend on the PG version
apt-get install -y skytools3-ticker pgbouncer

# make it possible for cron to work without root
gcc -s -shared -fPIC -o /usr/local/lib/cron_unprivileged.so cron_unprivileged.c

apt-get purge -y "${BUILD_PACKAGES[@]}"
apt-get autoremove -y

# Install *.deb packages (incl. libgdal)
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



## Try to minimize size by creating symlinks instead of duplicate files ##
if [ "$DEMO" != "true" ]; then
    POSTGIS_VERSION=$(jq -r ".postgresql_extensions_pgdg.\"12\".extra.\"postgis-3\"" "$VER_FILE")
    POSTGIS_LEGACY=$(jq -r ".postgresql_extensions_pgdg.\"11\".extra.\"postgis-3\"" "$VER_FILE")
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



## Final clean up ##
rm -rf /var/lib/apt/lists/* \
        /var/cache/debconf/* \
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

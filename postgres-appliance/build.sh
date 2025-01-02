#/bin/bash
WITH_PERL=false # set to true if you want to install perl and plperl packages into image
PGVERSION="17"
DEMO=false # set to true to build the smallest possible image which will work only on Kubernetes
TIMESCALEDB_APACHE_ONLY=false # set to false to build timescaledb community version (Timescale License)
TIMESCALEDB_TOOLKIT=false # set to false to skip installing toolkit with timescaledb community edition. Only relevant when TIMESCALEDB_APACHE_ONLY=false
ADDITIONAL_LOCALES=fi_FI # additional UTF-8 locales to build into image (example: "de_DE pl_PL fr_FR")

docker build -t ghcr.io/damischa1/spilo:X.X . \
       --build-arg WITH_PERL=false \
       --build-arg PGVERSION="17" \
       --build-arg DEMO=false \
       --build-arg TIMESCALEDB_APACHE_ONLY=false \
       --build-arg TIMESCALEDB_TOOLKIT=false \
       --build-arg ADDITIONAL_LOCALES=fi_FI
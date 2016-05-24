#!/bin/bash

if [ -z $1 ]
then
    cat <<__EOT__
Usage: $0 ROLE [INTERVAL] [TIMEOUT]

Waits for ROLE (master or replica). It will check every INTERVAL seconds ($INTERVAL).
If TIMEOUT is specified, it will stop trying after TIMEOUT seconds.

returns 0 when ROLE is available
returns 2 if the request timed out
__EOT__
    exit 1
fi

ROLE=$1
INTERVAL=$2
TIMEOUT=$3

[ -z "$INTERVAL" ] && INTERVAL=60
[ -z "$APIPORT" ]  && APIPORT=8008

CUTOFF=$(date --date="$TIMEOUT seconds" +%s)

while :
do
    [ $(curl -o /dev/null --silent --write-out '%{http_code}\n' "localhost:8008/$ROLE") -eq 200 ] && exit 0
    [ ! -z "$TIMEOUT" ] && [ $CUTOFF -le $(date +%s) ] && exit 2
    sleep $INTERVAL
done

exit 1

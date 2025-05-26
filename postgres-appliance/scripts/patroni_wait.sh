#!/bin/bash

ROLE=primary
INTERVAL=60
TIMEOUT=""

if [ -z "$1" ]
then
    cat <<__EOT__
Usage: $(basename 0) [OPTIONS] [-- COMMAND [ARG1] [ARG2]]

Options:

    -i, --interval  Specify the polling INTERVAL (default: $INTERVAL)

    -r, --role      Which ROLE to wait upon (default: $ROLE)

    -t, --timeout   Fail after TIMEOUT seconds (default: no timeout)

Waits for ROLE (primary or replica). It will check every INTERVAL seconds ($INTERVAL).
If TIMEOUT is specified, it will stop trying after TIMEOUT seconds.

Executes COMMAND after ROLE has become available. (Default: exit 0)
returns 2 if the request timed out.

Examples:

    $(basename "$0") -r replica -- echo "Replica is available"
    $(basename "$0") -t 1800 -- pg_basebackup -h localhost -D /tmp/backup --xlog-method=stream
__EOT__
    exit 1
fi


while [ $# -gt 0 ]
do
    case $1 in
    -r|--role)
        ROLE=$2
        shift
        ;;
    -i|--interval)
        INTERVAL=$2
        shift
        ;;
    -t|--timeout)
        TIMEOUT=$2
        shift
        ;;
    --)
        shift
        break
        ;;
    *)
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
    shift
done

if [ $# -gt 0 ]; then
    [ -n "$TIMEOUT" ] && CUTOFF=$(($(date +%s)+TIMEOUT))

    while [ "$(curl -so /dev/null -w '%{http_code}' "http://localhost:8008/$ROLE")" != "200" ]; do
        [ -n "$TIMEOUT" ] && [ $CUTOFF -le "$(date +%s)" ] && exit 2
        sleep "$INTERVAL"
    done

    exec "$@"  # Execute the command that was specified
fi

#!/bin/bash

ROLE=master
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

Waits for ROLE (master or replica). It will check every INTERVAL seconds ($INTERVAL).
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

    PORT=8008
    if [ -n "$APIPORT" ]
    then
        PORT="$APIPORT"
    fi

    options=""
    protocol="http"

    # If Patroni is configured in SSL we need to query the Patroni REST API using the 
    # HTTPS protocol and certificates.
    if [ "$SSL_RESTAPI_CERTIFICATE_FILE" != "" ] && [ "$SSL_RESTAPI_PRIVATE_KEY_FILE" != "" ]
    then
        protocol="https"
        options="$options --cert $SSL_RESTAPI_CERTIFICATE_FILE --key $SSL_RESTAPI_PRIVATE_KEY_FILE"
    fi

    if [ "$SSL_RESTAPI_CA_FILE" != "" ]
    then
        protocol="https"
        options="$options --cacert $SSL_RESTAPI_CA_FILE"
    fi

    # shellcheck disable=SC2086
    while [ "$(curl -so /dev/null -w '%{http_code}' $options "$protocol://localhost:$PORT/$ROLE")" != "200" ]; do
        [ -n "$TIMEOUT" ] && [ "$CUTOFF" -le "$(date +%s)" ] && exit 2
        sleep "$INTERVAL"
    done

    exec "$@"  # Execute the command that was specified
fi

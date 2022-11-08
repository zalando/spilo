#!/bin/bash

RETRIES=2

while getopts ":-:" optchar; do
    [[ "${optchar}" == "-" ]] || continue
    case "${OPTARG}" in
        datadir=* )
            DATA_DIR=${OPTARG#*=}
            ;;
        connstring=* )
            CONNSTR="${OPTARG#*=}"
            ;;
        retries=* )
            RETRIES=${OPTARG#*=}
            ;;
    esac
done

[[ -z $DATA_DIR || -z "$CONNSTR" || ! $RETRIES =~ ^[1-9]$ ]] && exit 1

if which pg_receivewal &> /dev/null; then
    PG_RECEIVEWAL=pg_receivewal
    PG_BASEBACKUP_OPTS=(-X none)
else
    PG_RECEIVEWAL=pg_receivexlog
    PG_BASEBACKUP_OPTS=()
fi

WAL_FAST=$(dirname "$DATA_DIR")/wal_fast
readonly WAL_FAST
mkdir -p "$WAL_FAST"

rm -fr "$DATA_DIR" "${WAL_FAST:?}"/*

function sigterm_handler() {
    kill -SIGTERM "$receivewal_pid" "$basebackup_pid"
    exit 143
}

trap sigterm_handler QUIT TERM INT


function start_receivewal() {
    local receivewal_pid=$BASHPID

    # wait for backup_label
    while [[ ! -f ${DATA_DIR}/backup_label ]]; do
        sleep 1
    done

    # get the first wal segment necessary for recovery from backup label
    SEGMENT=$(sed -n 's/^START WAL LOCATION: .*file \([0-9A-F]\{24\}\).*$/\1/p' "$DATA_DIR/backup_label")

    [ -z "$SEGMENT" ] && exit 1

    # run pg_receivewal until postgres will not start streaming
    (
        while ! pgrep -cf 'wal {0,1}receiver( process){0,1}\s+streaming' > /dev/null; do
            # exit if pg_receivewal is not running
            kill -0 $receivewal_pid && sleep 1 || exit
        done

        kill $receivewal_pid && sleep 1
        rm -f "${WAL_FAST:?}"/*
    )&

    # calculate the name of previous segment
    timeline=${SEGMENT:0:8}
    log=$((16#${SEGMENT:8:8}))
    seg=$((16#${SEGMENT:16:8}))
    if [[ $seg == 0 ]]; then
        seg=255
        log=$((log-1))
    else
        seg=$((seg-1))
    fi

    SEGMENT=$(printf "%s%08X%08X\n" "$timeline" "$log" "$seg")

    # pg_receivewal doesn't have an argument to specify position to start stream from
    # therefore we will "precreate" previous file and pg_receivewal will start fetching the next one
    dd if=/dev/zero of="$WAL_FAST/$SEGMENT" bs=16k count=1k

    exec $PG_RECEIVEWAL --directory="$WAL_FAST" --dbname="$CONNSTR"
}

# make sure that there is only one receivewal running
exec 9>"$WAL_FAST/receivewal.lock"
if flock -x -n 9; then
    start_receivewal &
    receivewal_pid=$!
    echo $receivewal_pid > "$WAL_FAST/receivewal.pid"
else
    receivewal_pid=$(cat "$WAL_FAST/receivewal.pid")
fi

ATTEMPT=0
while [[ $((ATTEMPT++)) -le $RETRIES ]]; do
    pg_basebackup --pgdata="${DATA_DIR}" "${PG_BASEBACKUP_OPTS[@]}" --dbname="${CONNSTR}" &
    basebackup_pid=$!
    wait $basebackup_pid
    EXITCODE=$?
    if [[ $EXITCODE == 0 ]]; then
        break
    elif [[ $ATTEMPT -le $RETRIES ]]; then
        sleep $((ATTEMPT*10))
        rm -fr "${DATA_DIR}"
    fi
done

[[ $EXITCODE != 0 && -n $receivewal_pid ]] && kill "$receivewal_pid"
exit $EXITCODE

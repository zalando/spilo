#!/bin/bash
set -e

date

prefetch=8

AWS_INSTANCE_PROFILE=0

function load_aws_instance_profile() {
    local CREDENTIALS_URL=http://169.254.169.254/latest/meta-data/iam/security-credentials/
    local INSTANCE_PROFILE=$(curl -s $CREDENTIALS_URL)
    source <(curl -s $CREDENTIALS_URL$INSTANCE_PROFILE | jq -r '"AWS_SECURITY_TOKEN=\"" + .Token + "\"\nAWS_SECRET_ACCESS_KEY=\"" + .SecretAccessKey + "\"\nAWS_ACCESS_KEY_ID=\"" + .AccessKeyId + "\""')
}

function load_region_from_aws_instance_profile() {
    local AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
    AWS_REGION=${AZ:0:-1}
}

function usage() {
    echo "Usage: $0 wal-fetch [--prefetch PREFETCH] WAL_SEGMENT WAL_DESTINATION"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --s3-prefix )
            WALE_S3_PREFIX=$2
            shift
            ;;
        -k|--aws-access-key-id )
            AWS_ACCESS_KEY_ID=$2
            shift
            ;;
        --aws-instance-profile )
            AWS_INSTANCE_PROFILE=1
            ;;
        wal-fetch )
            ;;
        -p|--prefetch )
            prefetch=$2
            shift
            ;;
        * )
            PARAMS+=("$1")
            ;;
    esac
    shift
done

[[ ${#PARAMS[@]} == 2 ]] || usage

[[ $AWS_INSTANCE_PROFILE == 1 ]] && load_aws_instance_profile

if [[ -z $AWS_SECRET_ACCESS_KEY || -z $AWS_ACCESS_KEY_ID || -z $WALE_S3_PREFIX ]]; then
    echo bad environment
    exit 1
fi

readonly SEGMENT=${PARAMS[-2]}
readonly DESTINATION=${PARAMS[-1]}

if [[ $WALE_S3_PREFIX =~ ^s3://([^\/]+)(.+) ]]; then
    readonly BUCKET=${BASH_REMATCH[1]}
    BUCKET_PATH=${BASH_REMATCH[2]}
    readonly BUCKET_PATH=${BUCKET_PATH%/}
else
    echo bad WALE_S3_PREFIX
    exit 1
fi

if [[ -z $AWS_REGION ]]; then
    if [[ ! -z $WALE_S3_ENDPOINT && $WALE_S3_ENDPOINT =~ ^([a-z\+]{2,10}://)?(s3-([^\.]+)[^:\/?]+) ]]; then
        S3_HOST=${BASH_REMATCH[2]}
        AWS_REGION=${BASH_REMATCH[3]}
    elif [[ $AWS_INSTANCE_PROFILE == 1 ]]; then
        load_region_from_aws_instance_profile
    fi
fi

if [[ -z $AWS_REGION ]]; then
    echo AWS_REGION is unknown
fi

if [[ -z $S3_HOST ]]; then
    S3_HOST=s3-$AWS_REGION.amazonaws.com
fi

readonly SERVICE=s3
readonly REQUEST=aws4_request
readonly HOST=$BUCKET.$S3_HOST
readonly TIME=$(date +%Y%m%dT%H%M%SZ)
readonly DATE=${TIME%T*}
readonly DRSR="$DATE/$AWS_REGION/$SERVICE/$REQUEST"
readonly EMPTYHASH=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

function hmac_sha256() {
    echo -en "$2" | openssl dgst -sha256 -mac HMAC -macopt "$1" | sed 's/^.* //'
}

# Four-step signing key calculation
readonly DATE_KEY=$(hmac_sha256 key:"AWS4$AWS_SECRET_ACCESS_KEY" $DATE)
readonly DATE_REGION_KEY=$(hmac_sha256 hexkey:$DATE_KEY $AWS_REGION)
readonly DATE_REGION_SERVICE_KEY=$(hmac_sha256 hexkey:$DATE_REGION_KEY $SERVICE)
readonly SIGNING_KEY=$(hmac_sha256 hexkey:$DATE_REGION_SERVICE_KEY $REQUEST)

if [[ -z $AWS_INSTANCE_PROFILE ]]; then
    readonly SIGNED_HEADERS="host;x-amz-content-sha256;x-amz-date"
    readonly REQUEST_TOKEN=""
    readonly TOKEN_HEADER=()
else
    readonly SIGNED_HEADERS="host;x-amz-content-sha256;x-amz-date;x-amz-security-token"
    readonly REQUEST_TOKEN="x-amz-security-token:$AWS_SECURITY_TOKEN\n"
    readonly TOKEN_HEADER=(-H "x-amz-security-token: $AWS_SECURITY_TOKEN")
fi

function s3_get() {
    local segment=$1
    local destination=$2
    local FILE=$BUCKET_PATH/wal_005/$segment.lzo
    local CANONICAL_REQUEST="GET\n$FILE\n\nhost:$HOST\nx-amz-content-sha256:$EMPTYHASH\nx-amz-date:$TIME\n$REQUEST_TOKEN\n$SIGNED_HEADERS\n$EMPTYHASH"
    local CANONICAL_REQUEST_HASH=$(echo -en $CANONICAL_REQUEST | openssl dgst -sha256 | sed 's/^.* //')
    local STRING_TO_SIGN="AWS4-HMAC-SHA256\n$TIME\n$DRSR\n$CANONICAL_REQUEST_HASH"
    local SIGNATURE=$(hmac_sha256 hexkey:$SIGNING_KEY $STRING_TO_SIGN)

    if curl -s https://$HOST$FILE "${TOKEN_HEADER[@]}" -H "x-amz-content-sha256: $EMPTYHASH" -H "x-amz-date: $TIME" \
        -H "Authorization: AWS4-HMAC-SHA256 Credential=$AWS_ACCESS_KEY_ID/$DRSR, SignedHeaders=$SIGNED_HEADERS, Signature=$SIGNATURE" \
        | lzop -dc > $destination 2> /dev/null && [[ ${PIPESTATUS[0]} == 0 ]]; then
        [[ -s $destination ]] && echo "$$ success $FILE" && return 0
    fi
    rm -f $destination
    echo "$$ failed $FILE"
    return 1
}

function generate_next_segments() {
    local num=$1

    local timeline=${SEGMENT:0:8}
    local log=$((16#${SEGMENT:8:8}))
    local seg=$((16#${SEGMENT:16:8}))

    while [[ $((num--)) -gt 0 ]]; do
        seg=$((seg+1))
        printf "%s%08X%08X\n" $timeline $((log+seg/256)) $((seg%256))
    done
}

function clear_except() {
    set +e
    for dir in $PREFETCHDIR/running/0*; do
        item=$(basename $dir)
        if [[ $item =~ ^[0-9A-F]{24}$ ]]; then
            [[ " ${PREFETCHES[@]} " =~ " $item " ]] || rm -fr $dir
        fi
    done

    for file in $PREFETCHDIR/0*; do
        item=$(basename $file)
        if [[ $item =~ ^[0-9A-F]{24}$ ]]; then
            [[ " ${PREFETCHES[@]} " =~ " $item " ]] || rm -f $file
        fi
    done
    set -e
    return 0
}

function try_to_promote_prefetched() {
    local prefetched=$PREFETCHDIR/$SEGMENT
    [[ -f $prefetched ]] || return 1
    echo "$$ promoting $prefetched"
    mv $prefetched $DESTINATION && clear_except && exit 0
}

echo "$$ $SEGMENT"

readonly PREFETCHDIR=$(dirname $DESTINATION)/.wal-e/prefetch
if [[ $prefetch > 0 && $SEGMENT =~ ^[0-9A-F]{24}$ ]]; then
    readonly PREFETCHES=($(generate_next_segments $prefetch))
    for segment in ${PREFETCHES[@]}; do
        running="$PREFETCHDIR/running/$segment"
        [[ -d $running || -f $PREFETCHDIR/$segment ]] && continue

        mkdir -p $running
        (
            trap "rm -fr $running" QUIT TERM EXIT
            TMPFILE=$(mktemp -p $running)
            echo "$$ prefetching $segment"
            s3_get $segment $TMPFILE && mv $TMPFILE $PREFETCHDIR/$segment
        ) &
    done

    last_size=0
    while ! try_to_promote_prefetched; do
        size=$(du -bs $PREFETCHDIR/running/$SEGMENT 2> /dev/null | cut -f1)
        if [[ -z $size ]]; then
            try_to_promote_prefetched || break
        elif [[ $size > $last_size ]]; then
            echo "($size > $last_size), sleeping 1"
            last_size=$size
            sleep 1
        else
            echo "size=$size, last_size=$last_size"
            break
        fi
    done
    clear_except
fi

s3_get $SEGMENT $DESTINATION

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import boto3
import os
import logging
import subprocess
import sys
import time

from datetime import datetime, timedelta

from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig

logger = logging.getLogger(__name__)


def compress_pg_log():
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_day_number = yesterday.strftime('%u')

    log_file = os.path.join(os.getenv('PGLOG'), 'postgresql-' + yesterday_day_number + '.csv')
    archived_log_file = os.path.join(os.getenv('LOG_TMPDIR'), yesterday.strftime('%F') + '.csv.gz')

    if os.path.getsize(log_file) == 0:
        logger.warning("Postgres log from yesterday '%s' is empty.", log_file)
        sys.exit(0)

    try:
        with open(archived_log_file, 'wb') as f_out:
            subprocess.Popen(['gzip', '-9c', log_file], stdout=f_out).wait()
    except Exception:
        logger.exception('Failed to compress log file %s', log_file)

    return archived_log_file


def upload_to_s3(local_file_path):
    # boto picks up AWS credentials automatically when run within a EC2 instance
    s3 = boto3.resource(
        service_name="s3",
        endpoint_url=os.getenv('LOG_S3_ENDPOINT'),
        region_name=os.getenv('LOG_AWS_REGION')
    )

    bucket_name = os.getenv('LOG_S3_BUCKET')
    bucket = s3.Bucket(bucket_name)

    key_name = os.path.join(os.getenv('LOG_S3_KEY'), os.path.basename(local_file_path))
    if os.getenv('LOG_GROUP_BY_DATE'):
        key_name = key_name.format(**{'DATE': os.path.basename(local_file_path).split('.')[0]})

    chunk_size = 52428800  # 50 MiB
    config = TransferConfig(multipart_threshold=chunk_size, multipart_chunksize=chunk_size)

    try:
        bucket.upload_file(local_file_path, key_name, Config=config)
    except S3UploadFailedError as e:
        logger.exception('Failed to upload the %s to the bucket %s under the key %s. Exception: %r',
                         local_file_path, bucket_name, key_name, e)
        return False

    return True


def main():
    max_retries = 3
    compressed_log = compress_pg_log()

    for _ in range(max_retries):
        if upload_to_s3(compressed_log):
            return os.unlink(compressed_log)
        time.sleep(10)

    logger.warning('Upload of the compressed log file %s failed after %s attempts.', compressed_log, max_retries)
    sys.exit(1)


if __name__ == '__main__':
    main()

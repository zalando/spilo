#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import boto
import math
import os
import logging
import gzip
import shutil
import time

from datetime import datetime, timedelta
from filechunkio import FileChunkIO


def compress_pg_log():

    yesterday = datetime.now() - timedelta(days=1)
    yesterday_day_number = yesterday.strftime('%u')

    log_file = os.getenv('PGLOG') + "/postgresql-" + yesterday_day_number + ".csv"
    archived_log_file = os.getenv('LOG_TMPDIR') + "/" + yesterday.strftime('%Y-%m-%d') + ".csv.gz"

    if os.path.getsize(log_file) == 0:
        logging.warn("Postgres log from yesterday '%s' is empty.", log_file)
        exit(0)

    with open(log_file, 'rb') as f_in:
        with gzip.open(archived_log_file, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    return archived_log_file


def upload_to_s3(local_file_path):

    # boto picks up AWS credentials automatically when run within a EC2 instance

    # host sets a region and the correct AWS SignatureVersion along the way
    # see https://github.com/boto/boto/issues/2741
    conn = boto.connect_s3(host=os.getenv('LOG_AWS_HOST'))

    bucket_name = os.getenv('LOG_S3_BUCKET')
    bucket = conn.get_bucket(bucket_name, validate=False)

    key_name = os.getenv('LOG_S3_KEY') + '/' + os.path.basename(local_file_path)
    mp_upload = bucket.initiate_multipart_upload(key_name)

    chunk_size = 52428800  # 50 MiB
    file_size = os.stat(local_file_path).st_size
    chunk_count = int(math.ceil(file_size / float(chunk_size)))

    for i in range(chunk_count):
        offset = chunk_size * i
        bytes = min(chunk_size, file_size - offset)
        with FileChunkIO(local_file_path, 'r', offset=offset, bytes=bytes) as fp:
            try:
                mp_upload.upload_part_from_file(fp, part_num=i + 1)
            except Exception as e:
                logging.critical(
                    """Failed to upload the {} to the bucket {} under the key {}
                    . Cancelling the multipart upload {}. Error: {}"""
                    .format(local_file_path, mp_upload.bucket_name, mp_upload.key_name, mp_upload.id, e))
                cancel_multipart_upload(mp_upload)
                return False

    if not len(mp_upload.get_all_parts()) == chunk_count:
        cancel_multipart_upload(mp_upload)
        return False

    mp_upload.complete_upload()
    return True


def is_successfully_cancelled(mp_upload):
    uploaded_parts = mp_upload.bucket.list_multipart_uploads(upload_id_marker=mp_upload.id)
    return len(uploaded_parts) == 0


def cancel_multipart_upload(mp_upload, max_retries=3):
    """
    Attempt to free storage consumed by already uploaded parts to avoid extra charges from S3.
    """

    # cancellation might fail for uploads currently in progress
    for _ in range(max_retries):
        mp_upload.cancel_upload()
        if is_successfully_cancelled(mp_upload):
            break
        time.sleep(10)

    if not is_successfully_cancelled(mp_upload):
        logging.warn("Unable to delete some of the already uploaded log parts.\
        Leftover parts incur monetary charges from S3.")

    return


def main():

    max_retries = 3
    compressed_log = compress_pg_log()

    for _ in range(max_retries):
        if upload_to_s3(compressed_log):
            exit(0)
        time.sleep(10)

    logging.warn("Upload of the compressed log file {} failed after {} attempts.", compressed_log, max_retries)
    exit(1)


if __name__ == '__main__':
    main()

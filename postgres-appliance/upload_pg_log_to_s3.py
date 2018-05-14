#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import boto, os, logging, gzip, shutil, requests, math

from datetime import datetime, timedelta
from filechunkio import FileChunkIO


def compress_pg_log():

    yesterday = datetime.now() - timedelta(days=1)
    yesterday_day_number = yesterday.strftime('%u')

    log_file = os.getenv('PGLOG') + "/postgresql-" + yesterday_day_number + ".csv"
    archived_log_file = os.getenv('LOG_TMPDIR') + "/" + yesterday.strftime('%Y-%m-%d-%H-%M-%S') + ".csv.gz"

    if os.path.getsize(log_file) == 0:
        logging.info("Postgres log from yesterday '%s' is empty. Was this Spilo pod started today ?", log_file)
        exit(0)

    with open(log_file, 'rb') as f_in:
        with gzip.open(archived_log_file, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    return archived_log_file


def upload_to_s3(local_file_path):

    # specifying the region also sets the correct AWS SignatureVersion
    # see https://github.com/boto/boto/issues/2741
    conn = boto.connect_s3(host = os.getenv('LOG_AWS_HOST'))

    bucket_name = os.getenv('LOG_S3_BUCKET')
    bucket = conn.get_bucket(bucket_name, validate = False)

    key_name = os.getenv('LOG_S3_KEY') + '/' + os.path.basename(local_file_path)
    mp_upload = bucket.initiate_multipart_upload(key_name)

    chunk_size = 52428800 # 50 MiB
    local_file_size = os.stat(local_file_path).st_size
    chunk_count = int(math.ceil(local_file_size / float(chunk_size)))

    for i in range(chunk_count):
        offset = chunk_size * i
        bytes = min(chunk_size, local_file_size - offset)
        with FileChunkIO(local_file_path, 'r', offset=offset, bytes=bytes) as fp:
            mp.upload_part_from_file(fp, part_num=i + 1)

    mp_upload.complete_upload()


def main():

    upload_to_s3(compress_pg_log())

if __name__ == '__main__':
    main()

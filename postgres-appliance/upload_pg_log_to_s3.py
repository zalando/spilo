#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import boto, os, logging, gzip, shutil, requests
from datetime import datetime, timedelta

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
    conn = boto.connect_s3(host = os.getenv('LOG_S3_HOST'))

    bucket_name = os.getenv('LOG_S3_BUCKET')
    bucket = conn.get_bucket(bucket_name, validate = False)

    object_to_upload = boto.s3.key.Key(bucket)
    object_to_upload.key = os.getenv('LOG_S3_KEY') + '/' + os.path.basename(local_file_path)
    object_to_upload.set_contents_from_filename(local_file_path)


def main():

    upload_to_s3(compress_pg_log())

if __name__ == '__main__':
    main()

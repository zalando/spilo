#!/bin/bash

# the BusyBox version of `date` installed in Spilo lacks the ' --date "yesterday" ' option, so we process the date in code

# determine the file to upload; assume Monday is 1, Sunday is 7
yesterday_day_number=$(($(date +%u) - 1)) 
if [ "$yesterday_day_number" -eq 0 ];
then
   yesterday_day_number=7 # Sunday comes before Monday
fi
log_file="${PGLOG}/postgresql-${yesterday_day_number}.csv"

# if a pod was started today, yesterday's logs will be empty
if [ -s "$log_file" ];
then

  # get the yesterday's date from the log itself
  yesterday=$(head -1 "$log_file" | cut -d " " -f 1)

  archive_name_with_date="${PGLOG}/postgresql-"$yesterday".csv.gz"
  tar cz -f "$archive_name_with_date" "$log_file"

  # upload file if it does not exist in the bucket
  # exclude/include filters - in that particular order - ensure the operation syncs only a single file
  aws s3 sync ${PGLOG} ${PG_DAILY_LOG_S3_PREFIX} --exclude '*' --include "'${archive_name_with_date}'"
  rm "$archive_name_with_date"

fi





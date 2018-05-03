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

  archived_log_with_date=${LOG_TMPDIR}/${yesterday}.csv.gz
  gzip --best --stdout "$log_file" > "$archived_log_with_date"

  aws s3 cp "${archived_log_with_date}" ${LOG_S3_PREFIX}${HOSTNAME}/
  rm "$archived_log_with_date"

fi

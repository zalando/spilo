# the BusyBox version of `date` installed in Spilo lacks the ' --date "yesterday" ' option, so we process the yesterday's date in code

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
# TODO fix S3 bucket
  # get the yesterday's date from the log itself
  yesterday=$(head -1 "$log_file" | cut -d " " -f 1)

  # compress with gzip under descriptive name and upload
  archive_name_with_date="${PGLOG}/postgresql-"$yesterday"-test.csv.gz"
  tar cz -f "$archive_name_with_date" "$log_file"
  aws s3 cp "$archive_name_with_date" s3://"$WAL_S3_BUCKET"
  rm "$archive_name_with_date"

fi





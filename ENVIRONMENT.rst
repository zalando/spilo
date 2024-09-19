Environment Configuration Settings
==================================

- **ETCD_HOST**: the DNS A record pointing to Etcd hosts.
- **ETCD_HOSTS**: list of Etcd hosts in format '"host1:port1","host2:port2",...,"hostN:portN"'.
- **ETCD_DISCOVERY_DOMAIN**: the DNS SRV record pointing to Etcd hosts.
- **ETCD_URL**: url for Etcd host in format http(s)://host1:port
- **ETCD_PROXY**: url for Etcd Proxy format http(s)://host1:port
- **ETCD_CACERT**: Etcd CA certificate. If present it will enable validation.
- **ETCD_CERT**: Etcd client certificate.
- **ETCD_KEY**: Etcd client certificate key. Can be empty if the key is part of certificate.
- **PGHOME**: filesystem path where to put PostgreSQL home directory (/home/postgres by default)
- **APIPORT**: TCP port to Patroni API connections (8008 by default)
- **BACKUP_SCHEDULE**: cron schedule for doing backups via WAL-E (if WAL-E is enabled, '00 01 * * *' by default)
- **CLONE_TARGET_TIMELINE**: timeline id of the backup for restore, 'latest' by default.
- **CRONTAB**: anything that you want to run periodically as a cron job (empty by default)
- **PGROOT**: a directory where we put the pgdata (by default /home/postgres/pgroot). One may adjust it to point to the mount point of the persistent volume, such as EBS.
- **WALE_TMPDIR**: directory to store WAL-E temporary files. PGROOT/../tmp by default, make sure it has a few GBs of free space.
- **PGDATA**: location of PostgreSQL data directory, by default PGROOT/pgdata.
- **PGUSER_STANDBY**: username for the replication user, 'standby' by default.
- **PGPASSWORD_STANDBY**: a password for the replication user, 'standby' by default.
- **STANDBY_HOST**: hostname or IP address of the primary to stream from.
- **STANDBY_PORT**: TCP port on which the primary is listening for connections. Patroni will use "5432" if not set.
- **STANDBY_PRIMARY_SLOT_NAME**: replication slot to use on the primary.
- **PGUSER_ADMIN**: username for the default admin user, 'admin' by default.
- **PGPASSWORD_ADMIN**: a password for the default admin user, 'cola' by default.
- **USE_ADMIN**: whether to use the admin user or not.
- **PGUSER_SUPERUSER**: username for the superuser, 'postgres' by default.
- **PGPASSWORD_SUPERUSER**: a password for the superuser, 'zalando' by default
- **ALLOW_NOSSL**: set to allow clients to connect without SSL enabled.
- **PGPORT**: port PostgreSQL listens to for client connections, 5432 by default
- **PGVERSION**: Specifies the version of postgreSQL to reference in the bin_dir variable (/usr/lib/postgresql/PGVERSION/bin) if postgresql.bin_dir wasn't set in SPILO_CONFIGURATION
- **SCOPE**: cluster name, multiple Spilos belonging to the same cluster must have identical scope.
- **SSL_CA_FILE**: path to the SSL CA certificate file inside the container (by default: '')
- **SSL_CRL_FILE**: path to the SSL Certificate Revocation List file inside the container (by default: '')
- **SSL_CERTIFICATE_FILE**: path to the SSL certificate file inside the container (by default /run/certs/server.crt), Spilo will generate one if not present.
- **SSL_PRIVATE_KEY_FILE**: path to the SSL private key within the container (by default /run/certs/server.key), Spilo will generate one if not present
- **SSL_CA**: content of the SSL CA certificate in the SSL_CA_FILE file (by default: '')
- **SSL_CRL**: content of the SSL Certificate Revocation List in the SSL_CRL_FILE file (by default: '')
- **SSL_CERTIFICATE**: content of the SSL certificate in the SSL_CERTIFICATE_FILE file (by default /run/certs/server.crt).
- **SSL_PRIVATE_KEY**: content of the SSL private key in the SSL_PRIVATE_KEY_FILE file (by default /run/certs/server.key).
- **SSL_RESTAPI_CA_FILE**: path to the Patroni REST Api SSL CA certificate file inside the container (by default: '')
- **SSL_RESTAPI_CERTIFICATE_FILE**: path to the Patroni REST Api SSL certificate file inside the container (by default /run/certs/restapi.crt), Spilo will generate one if not present.
- **SSL_RESTAPI_PRIVATE_KEY_FILE**: path to the Patroni REST Api SSL private key within the container (by default /run/certs/restapi.key), Spilo will generate one if not present
- **SSL_RESTAPI_CA**: content of the Patroni REST Api SSL CA certificate in the SSL_RESTAPI_CA_FILE file (by default: '')
- **SSL_RESTAPI_CERTIFICATE**: content of the REST Api SSL certificate in the SSL_CERTIFICATE_FILE file (by default /run/certs/server.crt).
- **SSL_RESTAPI_PRIVATE_KEY**: content of the REST Api SSL private key in the SSL_PRIVATE_KEY_FILE file (by default /run/certs/server.key).
- **SSL_TEST_RELOAD**: whenever to test for certificate rotation and reloading (by default True if SSL_PRIVATE_KEY_FILE has been set).
- **RESTAPI_CONNECT_ADDRESS**: when you configure Patroni RESTAPI in SSL mode some safe API (i.e. switchover) perform hostname validation. In this case could be convenient configure ````restapi.connect_address````as a hostname instead of IP. For example, you can configure it as "$(POD_NAME).<service name>".
- **WALE_BACKUP_THRESHOLD_MEGABYTES**: maximum size of the WAL segments accumulated after the base backup to consider WAL-E restore instead of pg_basebackup.
- **WALE_BACKUP_THRESHOLD_PERCENTAGE**: maximum ratio (in percents) of the accumulated WAL files to the base backup to consider WAL-E restore instead of pg_basebackup.
- **WALE_ENV_DIR**: directory where to store WAL-E environment variables
- **WAL_RESTORE_TIMEOUT**: timeout (in seconds) for restoring a single WAL file (at most 16 MB) from the backup location, 0 by default. A duration of 0 disables the timeout.
- **WAL_S3_BUCKET**: (optional) name of the S3 bucket used for WAL-E base backups.
- **AWS_ACCESS_KEY_ID**: (optional) aws access key
- **AWS_SECRET_ACCESS_KEY**: (optional) aws secret key
- **AWS_REGION**: (optional) region of S3 bucket
- **AWS_ENDPOINT**: (optional) in format 'https://s3.AWS_REGION.amazonaws.com:443', if not specified will be calculated from AWS_REGION
- **WALE_S3_ENDPOINT**: (optional) in format 'https+path://s3.AWS_REGION.amazonaws.com:443', if not specified will be calculated from AWS_ENDPOINT or AWS_REGION
- **WALE_S3_PREFIX**: (optional) the full path to the backup location on S3 in the format s3://bucket-name/very/long/path. If not specified Spilo will generate it from WAL_S3_BUCKET.
- **WAL_GS_BUCKET**: ditto for the Google Cloud Storage (WAL-E supports both S3 and GCS).
- **WALE_GS_PREFIX**: (optional) the full path to the backup location on the Google Cloud Storage in the format gs://bucket-name/very/long/path. If not specified Spilo will generate it from WAL_GS_BUCKET.
- **GOOGLE_APPLICATION_CREDENTIALS**: credentials for WAL-E when running in Google Cloud.
- **WAL_SWIFT_BUCKET**: ditto for the OpenStack Object Storage (Swift)
- **SWIFT_AUTHURL**: see wal-e documentation https://github.com/wal-e/wal-e#swift
- **SWIFT_TENANT**:
- **SWIFT_TENANT_ID**:
- **SWIFT_USER**:
- **SWIFT_USER_ID**:
- **SWIFT_PASSWORD**:
- **SWIFT_AUTH_VERSION**:
- **SWIFT_ENDPOINT_TYPE**:
- **SWIFT_REGION**:
- **SWIFT_DOMAIN_NAME**:
- **SWIFT_DOMAIN_ID**:
- **SWIFT_USER_DOMAIN_NAME**:
- **SWIFT_USER_DOMAIN_ID**:
- **SWIFT_PROJECT_NAME**:
- **SWIFT_PROJECT_ID**:
- **SWIFT_PROJECT_DOMAIN_NAME**:
- **SWIFT_PROJECT_DOMAIN_ID**:
- **WALE_SWIFT_PREFIX**: (optional) the full path to the backup location on the Swift Storage in the format swift://bucket-name/very/long/path. If not specified Spilo will generate it from WAL_SWIFT_BUCKET.
- **SSH_USERNAME**: (optional) the username for WAL backups.
- **SSH_PORT**: (optional) the ssh port for WAL backups.
- **SSH_PRIVATE_KEY_PATH**: (optional) the path to the private key used for WAL backups.
- **AZURE_STORAGE_ACCOUNT**: (optional) the azure storage account to use for WAL backups.
- **AZURE_STORAGE_ACCESS_KEY**: (optional) the access key for the azure storage account used for WAL backups.
- **AZURE_CLIENT_ID**: (optional) Client (application) ID of the Service Principal
- **AZURE_CLIENT_SECRET**: (optional) Client secret of the Service Principal
- **AZURE_TENANT_ID**: (optional) Tenant ID of the Service Principal
- **CALLBACK_SCRIPT**: the callback script to run on various cluster actions (on start, on stop, on restart, on role change). The script will receive the cluster name, connection string and the current action. See `Patroni <http://patroni.readthedocs.io/en/latest/SETTINGS.html?highlight=callback#postgresql>`__ documentation for details.
- **LOG_S3_BUCKET**: path to the S3 bucket used for PostgreSQL daily log files (i.e. foobar, without `s3://` prefix). Spilo will add `/spilo/{LOG_BUCKET_SCOPE_PREFIX}{SCOPE}{LOG_BUCKET_SCOPE_SUFFIX}/log/` to that path. Logs are shipped if this variable is set.
- **LOG_S3_TAGS**: map of key value pairs to be used for tagging files uploaded to S3. Values should be referencing existing environment variables e.g. ``{"ClusterName": "SCOPE", "Namespace": "POD_NAMESPACE"}``
- **LOG_SHIP_HOURLY**: if true, log rotation in Postgres is set to 1h incl. foreign tables for every hour (schedule `1 */1 * * *`)
- **LOG_SHIP_SCHEDULE**: cron schedule for shipping compressed logs from ``pg_log`` (``1 0 * * *`` by default)
- **LOG_ENV_DIR**: directory to store environment variables necessary for log shipping
- **LOG_TMPDIR**: directory to store temporary compressed daily log files. PGROOT/../tmp by default.
- **LOG_S3_ENDPOINT**: (optional) S3 Endpoint to use with Boto3
- **LOG_BUCKET_SCOPE_PREFIX**: (optional) using to build S3 file path like `/spilo/{LOG_BUCKET_SCOPE_PREFIX}{SCOPE}{LOG_BUCKET_SCOPE_SUFFIX}/log/`
- **LOG_BUCKET_SCOPE_SUFFIX**: (optional) same as above
- **LOG_GROUP_BY_DATE**: (optional) enable grouping log by date. Default is False - group the log files based on the instance ID.
- **DCS_ENABLE_KUBERNETES_API**: a non-empty value forces Patroni to use Kubernetes as a DCS. Default is empty.
- **KUBERNETES_USE_CONFIGMAPS**: a non-empty value makes Patroni store its metadata in ConfigMaps instead of Endpoints when running on Kubernetes. Default is empty.
- **KUBERNETES_ROLE_LABEL**: name of the label containing Postgres role when running on Kubernetens. Default is 'spilo-role'.
- **KUBERNETES_SCOPE_LABEL**: name of the label containing cluster name. Default is 'version'.
- **KUBERNETES_LABELS**: a JSON describing names and values of other labels used by Patroni on Kubernetes to locate its metadata. Default is '{"application": "spilo"}'.
- **INITDB_LOCALE**: database cluster's default UTF-8 locale (en_US by default)
- **ENABLE_WAL_PATH_COMPAT**: old Spilo images were generating wal path in the backup store using the following template ``/spilo/{WAL_BUCKET_SCOPE_PREFIX}{SCOPE}{WAL_BUCKET_SCOPE_SUFFIX}/wal/``, while new images adding one additional directory (``{PGVERSION}``) to the end. In order to avoid (unlikely) issues with restoring WALs (from S3/GC/and so on) when switching to ``spilo-13`` please set the ``ENABLE_WAL_PATH_COMPAT=true`` when deploying old cluster with ``spilo-13`` for the first time. After that the environment variable could be removed. Change of the WAL path also mean that backups stored in the old location will not be cleaned up automatically.
- **WALE_DISABLE_S3_SSE**, **WALG_DISABLE_S3_SSE**: by default wal-e/wal-g are configured to encrypt files uploaded to S3. In order to disable it you can set this environment variable to ``true``.
- **USE_OLD_LOCALES**: whether to use old locales from Ubuntu 18.04 in the Ubuntu 22.04-based image. Default is false.

wal-g
-----

`wal-g` is used by default for Azure and SSH backups and restore.
In case of S3, `wal-e` is used for backups and `wal-g` for restore.

- **USE_WALG_BACKUP**: (optional) Enforce using `wal-g` instead of `wal-e` for backups (Boolean)
- **USE_WALG_RESTORE**: (optional) Enforce using `wal-g` instead of `wal-e` for restores (Boolean)

- **WALG_DELTA_MAX_STEPS**, **WALG_DELTA_ORIGIN**, **WALG_DOWNLOAD_CONCURRENCY**, **WALG_UPLOAD_CONCURRENCY**, **WALG_UPLOAD_DISK_CONCURRENCY**, **WALG_DISK_RATE_LIMIT**, **WALG_NETWORK_RATE_LIMIT**, **WALG_COMPRESSION_METHOD**, **WALG_BACKUP_COMPRESSION_METHOD**, **WALG_BACKUP_FROM_REPLICA**, **WALG_SENTINEL_USER_DATA**, **WALG_PREVENT_WAL_OVERWRITE**: (optional) configuration options for wal-g.
- **WALG_S3_CA_CERT_FILE**: (optional) TLS CA certificate for wal-g (see [wal-g configuration](https://github.com/wal-g/wal-g#configuration))
- **WALG_SSH_PREFIX**: (optional) the ssh prefix to store WAL backups at in the format ssh://host.example.com/path/to/backups/ See `Wal-g <https://github.com/wal-g/wal-g#configuration>`__ documentation for details.
- **WALG_LIBSODIUM_KEY**, **WALG_LIBSODIUM_KEY_PATH**, **WALG_LIBSODIUM_KEY_TRANSFORM**, **WALG_PGP_KEY**, **WALG_PGP_KEY_PATH**, **WALG_PGP_KEY_PASSPHRASE** (optional) wal-g encryption properties (see [wal-g encryption](https://github.com/wal-g/wal-g#encryption))
- **http_proxy**, **https_proxy**, **no_proxy** (optional) HTTP(S) proxy configuration for `wal-g` to access S3. While http_proxy and https_proxy take a proxy URL, no_proxy takes a comma separated list of exceptions. Both are following a de-facto standard, see the [`wget`](https://www.gnu.org/software/wget/manual/html_node/Proxies.html) documentation.
- **AWS_ROLE_ARN**, **AWS_WEB_IDENTITY_TOKEN_FILE**, **AWS_STS_REGIONAL_ENDPOINTS** (optional) `AWS EKS IRSA <https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html>`__ auth configuration for `wal-g` to access S3. Usually these variables are automatically set by the AWS EKS. Only `wal-g` supports AWS EKS IRSA feature.

Azure Specific WAL-G Configuration
`````

For more information on the Azure specific options, refer to https://github.com/wal-g/wal-g/blob/master/docs/STORAGES.md#azure.

General configuration options for wal-g backup to Azure:

- **WALG_AZ_PREFIX**: Enables Azure Backups. The azure prefix to store WAL backups at in the format azure://test-container/walg-folder.
- **AZURE_STORAGE_ACCOUNT**
- **WALG_AZURE_BUFFER_SIZE**
- **WALG_AZURE_MAX_BUFFERS**
- **AZURE_ENVIRONMENT_NAME**

For authentication with the Microsoft Azure Blob Storage, choose one of the available authentication options:

- Storage Account Key:

  - **AZURE_STORAGE_ACCESS_KEY**

- Shared Access Signatures (SAS):

  - **AZURE_STORAGE_SAS_TOKEN**

- Service Principal:

  - **AZURE_CLIENT_ID**
  - **AZURE_CLIENT_SECRET**
  - **AZURE_TENANT_ID**

- Managed Service Identity (MSI): No configuration options required.

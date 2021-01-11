Configuration items specific to Spilo are listed here.

### Docker image
The Docker image containing Patroni and AWS-specific code which constitutes Spilo.

Example: `registry.opensource.zalan.do/acid/spilo-9.4:0.76-p1`

### Postgres WAL S3 bucket
The location to store the `pg_basebackup` and the archived WAL-files of the PostgreSQL cluster.

Example: `example-team-eu-west-1-spilo-app`

### EC2 instance type
Which EC2 instance type you want to use. Amazon provides many types of instances for different use cases.

Example: `m3.large`

**Amazon Documentation** [Amazon EC2 Instance Types](https://aws.amazon.com/ec2/instance-types/)


### ETCD Discovery Domain
What domain to use for etcd discovery.

Example: `team.example.com`

The supplied domain will be prefixed with `_etcd-server-ssl._tcp.` or `_etcd-server._tcp.` to
resolve a dns SRV record. This record contains the IP-addresses and ports of the etcd cluster. Example output:

```bash
$ dig +noall +answer SRV _etcd-server._tcp.tutorial.team.example.com
_etcd-server._tcp.tutorial.team.example.com. 60 IN      SRV 1 1 2380 ip-172-31-152-102.eu-west-1.compute.internal.
_etcd-server._tcp.tutorial.team.example.com. 60 IN      SRV 1 1 2380 ip-172-31-152-103.eu-west-1.compute.internal.
_etcd-server._tcp.tutorial.team.example.com. 60 IN      SRV 1 1 2380 ip-172-31-161-166.eu-west-1.compute.internal.
_etcd-server._tcp.tutorial.team.example.com. 60 IN      SRV 1 1 2380 ip-172-31-131-14.eu-west-1.compute.internal.
_etcd-server._tcp.tutorial.team.example.com. 60 IN      SRV 1 1 2380 ip-172-31-131-15.eu-west-1.compute.internal.
```

**etcd documentation** [DNS Discovery](https://github.com/coreos/etcd/blob/master/Documentation/clustering.md#dns-discovery)

### Database Volume Size
The size for the volume containing the Database.

### Database Volume Type
What EBS Volume type to use. Currently only three options are available:

* gp2
* io1
* standard

**Amazon Documentation** [Amazon EBS Volume Types](http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSVolumeTypes.html)

### EBS Snapshot ID
When reusing an old EBS snapshot, specify its ID here.

Example: `snap-e8bdf4c1`

### File system for the data partition
What file system to use for your PostgreSQL cluster. Choosing `ext4` is a safe bet.

Example: `ext4`

**Blog with a lot of pointers on what Filesystem to choose**
[PostgreSQL performance on EXT4 and XFS](http://blog.pgaddict.com/posts/postgresql-performance-on-ext4-and-xfs)

### File system mount options
Which mount options for the file system containing the data.

Example: `noatime,nodiratime,nobarrier`

### Scalyr Account key
The key with which Spilo is allowed to write Scalyr logs.

Example: `W21hc3RlciA1NjExNDc2XSBBZGQgZ2VuZXJhdGVkIHBI-`

**Stups documentation**
[Configuring Application Logging](http://stups.readthedocs.org/en/latest/user-guide/standalone-deployment.html#optional-configuring-application-logging)

### PostgreSQL passwords
The passwords to use for the initial PostgreSQL users. These can be randomly generated and optionally can be encrypted
using KMS.

### KMS Encryption Key
Which key to use to encrypt the passwords in the template. By using KMS encryption we avoid storing the passwords
in plain text anywhere. They will only be available to the EC2 instances running Spilo.

### Initialization scripts

If you would like to do additional initialization in an image derived from this one, add one or more `*.sql`, `*.sql.gz`, or `*.sh` scripts under `/docker-entrypoint-initdb.d` (creating the directory if necessary). After the entrypoint calls `initdb` to create the default `postgres` user and database, it will run any `*.sql` files, run any executable `*.sh` scripts, and source any non-executable `*.sh` scripts found in that directory to do further initialization before starting the service.

**Warning**: scripts in `/docker-entrypoint-initdb.d` are only run if you start the container with a data directory that is empty; any pre-existing database will be left untouched on container startup. One common problem is that if one of your `/docker-entrypoint-initdb.d` scripts fails (which will cause the entrypoint script to exit) and your orchestrator restarts the container with the already initialized data directory, it will not continue on with your scripts.

For example, to add an additional user and database, add the following to `/docker-entrypoint-initdb.d/init-user-db.sh`:

```bash
#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE USER docker;
	CREATE DATABASE docker;
	GRANT ALL PRIVILEGES ON DATABASE docker TO docker;
EOSQL
```

These initialization files will be executed in sorted name order as defined by the current locale, which defaults to `en_US.utf8`. Any `*.sql` files will be executed by `POSTGRES_USER`, which defaults to the `postgres` superuser. It is recommended that any `psql` commands that are run inside of a `*.sh` script be executed as `POSTGRES_USER` by using the `--username "$POSTGRES_USER"` flag. This user will be able to connect without a password due to the presence of `trust` authentication for Unix socket connections made inside the container.

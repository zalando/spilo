Spilo combines [Patroni](https://github.com/zalando/Patroni) with [stups](https://stups.io). Running Spilo therefore
requires that you have an Amazon VPC with Stups installed. For more details,
see the [Stups Installation Guide](http://docs.stups.io/en/latest/installation/)

## Stups

To be able to deploy and troubleshoot Spilo, you need the stups tooling installed locally:
```bash
$ sudo pip3 install --upgrade stups
```

If you need different installation methods, run into issues, or want more details on how to install the stups tooling
locally, we refer you to the [Stups User's Guide](http://docs.stups.io/en/latest/user-guide/index.html)

You can test your setup by logging in using mai and then listing the already running instances using senza,
example session:

```bash
$ mai login
Please enter password for encrypted keyring:
Authenticating against https://aws.example.com.. OK
Assuming role AWS Account 1234567890 (example-team): SomeRoleName.. OK
Writing temporary AWS credentials.. OK
```
```bash
$ senza list
Stack Name|Ver.    |Status         |Created|Description
spilo      tutorial CREATE_COMPLETE  6d ago Spilo ()
```

## etcd
Patroni requires a DCS. One of these could be etcd.
You may already have etcd installed within your account.

To check if etcd is already deployed using the advised method:

```bash
$ senza list etcd-cluster
Stack Name  │Ver.    │Status         │Created │Description
etcd-cluster somename CREATE_COMPLETE 242d ago Etcd Cluster (<details>)
```

If etcd is not installed yet, you can use the
[Installation Section](https://github.com/zalando/stups-etcd-cluster/blob/master/README.md#usage) of the
stups-etcd-cluster appliance.

**Demo etcd-cluster deployment**
[![Demo on asciicast](https://asciinema.org/a/32703.png)](https://asciinema.org/a/32703)

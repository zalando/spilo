Introduction
============
This etcd appliance is created for an AWS environment. It is available as an etcd cluster internally, for any applicatin willing to use it. For discovery of the appliance we consider having a recently updated DNS SRV record.

Design
======
The appliance itself will simply run etcd. Another process will be running which will update the dns-records (if necessary, periodically). By acquiring a distributed lock we ensure:
- Only 1 process will be actively updating the record
- We can connect to a cluster member which can reach the quorum of the etcd-members

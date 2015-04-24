Introduction
============
For creating an etcd-cluster you need something to discover other members: a (public) etcd server, a valid DNS SRV record, or a static list of other members.
This is needed to solve the chicken-egg problem: Before the cluster is functional, how do I know about the other cluster members.

To help in solving this issue, we do not start etcd directly; we use a python script that forks an etcd process, after it has established what its peers are.
It uses immutage AWS tags to gather this information.

The script also takes caring of adding members later on and cleaning up members.

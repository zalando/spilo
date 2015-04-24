Introduction
============
The etcd-proxy is the bridge between a HA-Cluster member and the etcd-cluster. By using a etcd-proxy we do not unnecessarily increase the quorum or the write performance of an etcd cluster, but we do have an etcd interface which knows about the etcd-cluster.

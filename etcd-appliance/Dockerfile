FROM zalando/ubuntu:14.04.1-1

## Install python
RUN apt-get update && apt-get -y install python

## Install etcd
ENV ETCDVERSION 2.0.9
RUN curl -L  https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz | tar xz
EXPOSE 4001 7001 2379 2380

ADD etcd-wrapper.sh etcd-wrapper.sh
ADD update-dns-from-etcd.py update-dns-from-etcd.py

ENTRYPOINT ["/etcd-wrapper.sh"]

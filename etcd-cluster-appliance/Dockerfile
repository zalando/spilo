FROM zalando/ubuntu:14.04.1-1

## Install python
RUN apt-get update && apt-get -y install python python-boto

## Install etcd
ENV ETCDVERSION 2.0.9
RUN mkdir -m 777 /etcd && curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz | tar xz -C /etcd --strip=1 --wildcards --no-anchored etcd etcdctl
EXPOSE 2379 2380

ADD etcd.py /etcd/etcd.py

CMD ["/etcd/etcd.py"]

FROM zalando/ubuntu:14.04.1-1

## Install python
RUN apt-get update && apt-get -y install python python-boto

## Install etcd
RUN useradd -d /home/etcd -k /etc/skel -s /bin/bash -m etcd
ENV ETCDVERSION 2.0.11
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz | tar xz -C /bin --strip=1 --wildcards --no-anchored etcd etcdctl
EXPOSE 2379 2380

ADD etcd.py /bin/etcd.py

USER etcd
CMD ["/bin/etcd.py"]

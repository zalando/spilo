FROM zalando/ubuntu:14.04.1-1

ENV USER etcd
ENV HOME /home/${USER}
ENV ETCDVERSION 2.0.12

## Install python
RUN apt-get update && apt-get -y install python python-boto

## Install etcd
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz | tar xz -C /bin --strip=1 --wildcards --no-anchored etcd etcdctl
EXPOSE 2379 2380

ADD etcd.py /bin/etcd.py

RUN useradd -d ${HOME} -k /etc/skel -s /bin/bash -m ${USER} && chmod 777 ${HOME}
WORKDIR $HOME
USER ${USER}
CMD ["/bin/etcd.py"]

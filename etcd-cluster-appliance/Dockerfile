FROM zalando/python:3.4.0-1
MAINTAINER Alexander Kukushkin <alexander.kukushkin@zalando.de>

ENV USER etcd
ENV HOME /home/${USER}
ENV ETCDVERSION 2.1.3

# Create home directory for etcd
RUN useradd -d ${HOME} -k /etc/skel -s /bin/bash -m ${USER} && chmod 777 ${HOME}

# Install boto
RUN ln -s /usr/bin/python3 /usr/bin/python && pip3 install boto

EXPOSE 2379 2380

## Install etcd
RUN curl -L https://github.com/coreos/etcd/releases/download/v${ETCDVERSION}/etcd-v${ETCDVERSION}-linux-amd64.tar.gz | tar xz -C /bin --strip=1 --wildcards --no-anchored etcd etcdctl

ADD etcd.py /bin/etcd.py

WORKDIR $HOME
USER ${USER}
CMD ["/bin/etcd.py"]

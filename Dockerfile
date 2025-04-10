FROM python:3.12 as builder

LABEL description="ElastAlert-feishu-alarm"
LABEL maintainer="zhentianxiang"

COPY . /tmp/elastalert

ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

RUN mkdir -p /opt/elastalert && \
    cd /tmp/elastalert && \
    pip install --upgrade pip && \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python setup.py sdist bdist_wheel

FROM python:3.12

ARG GID=1000
ARG UID=1000
ARG USERNAME=elastalert

ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

COPY --from=builder /tmp/elastalert/dist/*.tar.gz /tmp/

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources  && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources  && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        jq \
        curl \
        gcc \
        libffi-dev \
        tzdata && \
    ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ /tmp/*.tar.gz && \
    rm -rf /tmp/* && \
    apt-get remove -y gcc libffi-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /opt/elastalert && \
    echo "#!/bin/sh" >> /opt/elastalert/run.sh && \
    echo "set -e" >> /opt/elastalert/run.sh && \
    echo "elastalert-create-index --config /opt/elastalert/config.yaml" \
        >> /opt/elastalert/run.sh && \
    echo "elastalert --config /opt/elastalert/config.yaml \"\$@\"" \
        >> /opt/elastalert/run.sh && \
    chmod +x /opt/elastalert/run.sh && \
    groupadd -g ${GID} ${USERNAME} && \
    useradd -u ${UID} -g ${GID} -M -b /opt -s /sbin/nologin \
        -c "ElastAlert 2 User" ${USERNAME}

USER ${USERNAME}
WORKDIR /opt/elastalert
ENTRYPOINT ["/opt/elastalert/run.sh"]

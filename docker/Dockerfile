FROM ubuntu:xenial
LABEL maintainer "Kentaro Wada <www.kentaro.wada@gmail.com>"

RUN \
  apt-get update -qq && \
  apt-get upgrade -qq -y && \
  apt-get install -qq -y \
    git \
    python3 \
    python3-pip \
    python3-matplotlib \
    python3-pyqt5 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install -U pip setuptools wheel

RUN python3 -m pip install -v git+https://github.com/wkentaro/labelme.git

RUN mkdir /root/workdir

ENV LANG en-US

WORKDIR /root/workdir
ENTRYPOINT [ "labelme" ]

FROM ubuntu:bionic
LABEL maintainer "Kentaro Wada <www.kentaro.wada@gmail.com>"

ENV DEBIAN_FRONTEND=noninteractive

RUN \
  apt-get update -qq && \
  apt-get install -qq -y \
    sudo \
    git \
    python3 \
    python3-pip \
    python3-matplotlib \
    python3-pyqt5 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install -U pip setuptools wheel

# don't run as root ------------------------------------------------------------
ARG USERNAME=user
ARG UID
ARG GID
ARG HOME=/home/$USERNAME
ENV HOME=$HOME
ENV USERNAME=$USERNAME
ARG GID

RUN echo groupadd -g $GID -o $USERNAME
RUN groupadd -g $GID -o $USERNAME
RUN useradd \
    --create-home \
    --uid $UID \
    --gid $GID \
    --groups sudo \
    --password $(openssl passwd -1 $USERNAME) $USERNAME \
    --home-dir $HOME
RUN usermod -aG sudo $USERNAME
RUN usermod -aG sudo $USERNAME
RUN echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$USERNAME

# change default shell
RUN chsh -s /bin/bash $USERNAME

# vvvv Regular user vvvv -------------------------------------------------------

USER $USERNAME
ENV HOME=/home/$USERNAME/
ENV LANG en-US

COPY . $HOME/labelme-build
RUN cd $HOME/labelme-build && sudo -H pip3 install .
WORKDIR $HOME/labelme
ENTRYPOINT [ "labelme" ]

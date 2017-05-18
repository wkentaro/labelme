FROM ubuntu:trusty

# http://fabiorehm.com/blog/2014/09/11/running-gui-apps-with-docker/
RUN export uid=1000 gid=1000 && \
    mkdir -p /home/developer && \
    echo "developer:x:${uid}:${gid}:Developer,,,:/home/developer:/bin/bash" >> /etc/passwd && \
    echo "developer:x:${uid}:" >> /etc/group && \
    echo "developer ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/developer && \
    chmod 0440 /etc/sudoers.d/developer && \
    chown ${uid}:${gid} -R /home/developer

RUN \
  apt-get update -qq && \
  apt-get upgrade -qq -y && \
  apt-get install -qq -y \
    aptitude \
    git \
    python \
    python-setuptools

RUN \
  easy_install -q pip && \
  pip install -q -U pip setuptools

RUN apt-get install -qq -y python-qt4 pyqt4-dev-tools
RUN apt-get install -qq -y python-matplotlib
RUN apt-get install -qq -y python-scipy
RUN apt-get install -qq -y python-skimage

RUN pip install -v git+https://github.com/wkentaro/labelme.git

USER developer
ENV HOME /home/developer

FROM ubuntu:trusty

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

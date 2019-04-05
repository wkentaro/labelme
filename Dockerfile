FROM mubashirhanif/my-xfce

USER 0
RUN \
  apt-get update && \
  apt-get install -y \
    # requirements
    git \
    python3 \
    python3-pip \
    python3-matplotlib \
    python3-pyqt5 \
    # utilities
    sudo

RUN pip3 install -v git+https://github.com/wkentaro/labelme.git
USER 1000
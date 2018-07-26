#!/bin/bash

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd $HERE

if [ ! -e .anaconda2 ]; then
  curl -L https://github.com/wkentaro/dotfiles/raw/master/local/bin/install_anaconda2.sh | bash -s .
fi
source .anaconda2/bin/activate

if [ ! -e src/polyrnn-pp ]; then
  mkdir -p src
  git clone https://github.com/wkentaro/polyrnn-pp.git src/polyrnn-pp
fi

conda list | egrep '^opencv ' &>/dev/null || conda install -y -q opencv
conda list | egrep '^tensorflow-gpu ' &>/dev/null || conda install -y -q tensorflow-gpu==1.3.0
conda list | egrep '^scikit-image ' &>/dev/null || conda install -y -q scikit-image

conda list | egrep '^pyqt ' &>/dev/null || conda install -y -q pyqt
pip install -e .

# demo
(cd src/polyrnn-pp && CUDA_VISIBLE_DEVICES=0 src/demo_inference.sh)

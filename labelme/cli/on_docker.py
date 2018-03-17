#!/usr/bin/env python

import argparse
import json
import os
import os.path as osp
import platform
import shlex
import subprocess
import sys


def get_ip():
    dist = platform.platform().split('-')[0]
    if dist == 'Linux':
        return ''
    elif dist == 'Darwin':
        cmd = 'ifconfig en0'
        output = subprocess.check_output(shlex.split(cmd))
        for row in output.splitlines():
            cols = row.strip().split(' ')
            if cols[0] == 'inet':
                ip = cols[1]
                return ip
        else:
            raise RuntimeError('No ip is found.')
    else:
        raise RuntimeError('Unsupported platform.')


def labelme_on_docker(image_file, out_file):
    ip = get_ip()
    cmd = 'xhost + %s' % ip
    subprocess.check_output(shlex.split(cmd))

    out_file = osp.abspath(out_file)
    if osp.exists(out_file):
        raise RuntimeError('File exists: %s' % out_file)
    else:
        open(osp.abspath(out_file), 'w')

    cmd = 'docker run -it --rm' \
        ' -e DISPLAY={0}:0' \
        ' -e QT_X11_NO_MITSHM=1' \
        ' -v /tmp/.X11-unix:/tmp/.X11-unix' \
        ' -v {1}:{2}' \
        ' -v {3}:{4}' \
        ' -w /home/developer' \
        ' labelme' \
        ' labelme {2} -O {4}'
    cmd = cmd.format(
        ip,
        osp.abspath(image_file),
        osp.join('/home/developer', osp.basename(image_file)),
        osp.abspath(out_file),
        osp.join('/home/developer', osp.basename(out_file)),
    )
    subprocess.call(shlex.split(cmd))

    try:
        json.load(open(out_file))
        return out_file
    except Exception as e:
        if open(out_file).read() == '':
            os.remove(out_file)
        raise RuntimeError('Annotation is cancelled.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image_file')
    parser.add_argument('-O', '--output', required=True)
    args = parser.parse_args()

    try:
        out_file = labelme_on_docker(args.image_file, args.output)
        print('Saved to: %s' % out_file)
    except RuntimeError as e:
        sys.stderr.write(e.__str__() + '\n')
        sys.exit(1)


if __name__ == '__main__':
    main()

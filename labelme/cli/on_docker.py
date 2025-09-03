#!/usr/bin/env python


import argparse
import json
import os
import os.path as osp
import platform
import shlex
import shutil
import subprocess
import sys


def get_ip():
    dist = platform.platform().split("-")[0]
    if dist == "Linux":
        return ""
    elif dist == "Darwin":
        output = subprocess.check_output("ifconfig en0", encoding="utf-8")
        for row in output.splitlines():
            cols = row.strip().split(" ")
            if cols[0] == "inet":
                ip = cols[1]
                return ip
        else:
            raise RuntimeError("No ip is found.")
    else:
        raise RuntimeError("Unsupported platform.")


def labelme_on_docker(in_file, out_file):
    ip = get_ip()
    cmd = f"xhost + {ip}"
    subprocess.check_output(shlex.split(cmd))

    if out_file:
        out_file = osp.abspath(out_file)
        if osp.exists(out_file):
            raise RuntimeError(f"File exists: {out_file}")
        else:
            open(osp.abspath(out_file), "w")

    cmd = (
        "docker run -it --rm"
        " -e DISPLAY={0}:0"
        " -e QT_X11_NO_MITSHM=1"
        " -v /tmp/.X11-unix:/tmp/.X11-unix"
        " -v {1}:{2}"
        " -w /home/developer"
    )
    in_file_a = osp.abspath(in_file)
    in_file_b = osp.join("/home/developer", osp.basename(in_file))
    cmd = cmd.format(
        ip,
        in_file_a,
        in_file_b,
    )
    if out_file:
        out_file_a = osp.abspath(out_file)
        out_file_b = osp.join("/home/developer", osp.basename(out_file))
        cmd += f" -v {out_file_a}:{out_file_b}"
    cmd += f" wkentaro/labelme labelme {in_file_b}"
    if out_file:
        cmd += f" -O {out_file_b}"
    subprocess.call(shlex.split(cmd))

    if out_file:
        try:
            json.load(open(out_file))
            return out_file
        except Exception:
            if open(out_file).read() == "":
                os.remove(out_file)
            raise RuntimeError("Annotation is cancelled.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("in_file", help="Input file or directory.")
    parser.add_argument("-O", "--output")
    args = parser.parse_args()

    if not shutil.which("docker"):
        print("Please install docker", file=sys.stderr)
        sys.exit(1)

    try:
        out_file = labelme_on_docker(args.in_file, args.output)
        if out_file:
            print(f"Saved to: {out_file}")
    except RuntimeError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

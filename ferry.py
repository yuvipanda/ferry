import subprocess
import os
import sys
import json
import argparse


def fetch_image(image_spec):
    """
    Fetch a docker image into local filesystem
    """
    args = [
        "skopeo",
        "--insecure-policy",
        "copy",
        "docker://{}".format(image_spec),
        "oci:{}".format(image_spec)
    ]
    subprocess.check_call(args)


def create_runtime(image_spec, container_name):
    args = [
        "umoci",
        "unpack",
        "--rootless",
        "--image", image_spec,
        container_name
    ]
    subprocess.check_call(args)

def setup_config(container_name, cmd, bind_mounts):
    with open(os.path.join(container_name, 'config.json'), 'r') as f:
        config = json.load(f)

    # HACK: Don't support readonly bind mounts
    # Waiting for runc fix: https://github.com/opencontainers/runc/issues/1523
    for m in config['mounts']:
        if m['type'] == 'bind':
            if 'ro' in m['options']:
                m['options'].remove('ro')

    for src, dest in bind_mounts.items():
        config['mounts'].append({
            'source': src,
            'destination': dest,
            'type': 'bind',
            'options': ['bind', 'rw']
        })

    # Give it a more readable hostname
    config['hostname'] = container_name
    if cmd:
        config['process']['args'] = cmd

    # Only root can exist inside the container
    config['process']['user'] = { 'uid': 0, 'gid': 0 }

    with open(os.path.join(container_name, 'config.json'), 'w') as f:
        json.dump(config, f)


def container_exists(container_name):
    return os.path.exists(container_name)

def start_container(container_name):
    args = [
        "runc",
        "--root", "/tmp/runc",
        "run", container_name,
        "--bundle", container_name
    ]
    subprocess.check_call(args)


def run_container(image_spec, container_name, cmd, bind_mounts):
    fetch_image(image_spec)
    if not container_exists(container_name):
        create_runtime(image_spec, container_name)
    setup_config(container_name, cmd, bind_mounts)
    start_container(container_name)


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        'image',
        help='Image to fetch (if necessary) and run!'
    )
    argparser.add_argument(
        'container_name',
        help='Name to use for container we are starting'
    )
    argparser.add_argument(
        '--mount',
        default=[],
        action='append',
        help="Paths to bind mount into the container. Format src=dest"
    )
    argparser.add_argument(
        '--cmd',
        nargs='*',
        default=[],
        help="Arguments to pass to started container"
    )
    args = argparser.parse_args()
    bind_mounts = dict([bm.split(':', 1) for bm in args.mount])
    run_container(args.image, args.container_name, args.cmd, bind_mounts)

import sys
import os
import json
import subprocess
import argparse


class ProotRuntime:
    """
    A `proot` based partial OCI implementation.

    Attempts to implement enough of OCI spec to be useful.

    Things this should support:

    1. rootfs
    2. env
    3. args
    4. cwd
    5. rlimits
    6. mounts (only bind mounts, pretty much!)

    The goal is to be able to run arbitrary containers off DockerHub.
    """
    def __init__(self, basedir):
        self.basedir = basedir
        # Default mounts!
        self.mounts = {
            '/etc/resolv.conf': '/etc/resolv.conf',
            '/etc/hosts': '/etc/hosts',
            '/etc/hostname': '/etc/hostname',
            '/run': '/run',
            '/etc/passwd': '/etc/passwd',
            '/etc/group': '/etc/group',
            '/etc/nsswitch.conf': '/etc/nsswitch.conf'
        }

        path = os.path.join(basedir, 'config.json')
        with open(path) as f:
            config = json.load(f)

        for mount in config.get('mounts', []):
            if mount['type'] == 'proc':
                self.mounts['/proc'] = '/proc'
            elif mount['type'] == 'tmpfs' and mount['destination'] == '/dev':
                self.mounts['/dev'] = '/dev'
            elif mount['type'] == 'none' and mount['source'] == '/sys':
                self.mounts['/sys'] = '/sys'
            elif mount['type'] == 'mqueue' and mount['destination'] == '/dev/mqueue':
                self.mounts['/dev/mqueue'] = '/dev/mqueue'
            elif mount['type'] == 'tmpfs' and mount['destination'] == '/dev/shm':
                self.mounts['/dev/shm'] = '/dev/shm'
            elif mount['type'] == 'devpts':
                self.mounts['/dev/pts'] = '/dev/pts'
            else:
                self.mounts[mount['source']] = mount['destination']

        self.cwd = config['process']['cwd']
        self.rootfs = os.path.join(basedir, config['root']['path'])
        self.args = config['process']['args']

    def run(self):
        args = [
            'proot',
            '-r', self.rootfs,
            '--cwd={}'.format(self.cwd)
        ]
        for src, dst in self.mounts.items():
            args += ['-b', '{}:{}'.format(src, dst)]
        args += self.args
        subprocess.check_call(args)

class RuncRuntime:
    def __init__(self, basedir):
        self.basedir = basedir
        path = os.path.join(basedir, 'config.json')
        with open(path) as f:
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

        self.config = config
        os.rename(path, path + '.orig')
        with open(path, 'w') as f:
            json.dump(self.config, f)

    def run(self):
        args = [
            "runc",
            "--root", "/tmp/runc",
            "run", self.basedir,
            "--bundle", self.basedir
        ]
        subprocess.check_call(args)


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

def run_container(image_spec, container_name, cmd, bind_mounts):
    fetch_image(image_spec)
    create_runtime(image_spec, container_name)
    r = ProotRuntime(container_name)
    r.run()

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
    print(args.container_name)
    run_container(
        args.image,
        args.container_name,
        args.cmd,
        bind_mounts
    )

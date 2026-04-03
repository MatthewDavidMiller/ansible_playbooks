#!/usr/bin/env python3
"""Bootstrap a new Rocky Linux VM for the maintained Ansible workflow."""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
from pathlib import Path


BOOTSTRAP_PACKAGES = [
    "ansible-core",
    "openssh-clients",
    "sshpass",
    "ansible-collection-ansible-posix",
    "ansible-collection-community-general",
]


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def main() -> int:
    run(["dnf", "install", "-y", *BOOTSTRAP_PACKAGES])

    ansible_configs = Path("/ansible_configs")
    ansible_configs.mkdir(mode=0o700, exist_ok=True)

    root_user = pwd.getpwnam("root")
    os.chown(ansible_configs, root_user.pw_uid, root_user.pw_gid)
    os.chmod(ansible_configs, stat.S_IRWXU)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

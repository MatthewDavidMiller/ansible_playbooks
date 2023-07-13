# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm
# https://ochoaprojects.github.io/posts/ProxMoxCloudInitImage/

# Initial setup for your first vm.

import subprocess
import os
import pwd
import stat

# Debian update packages
subprocess.call([r"apt-get", r"update", r"-y"])
subprocess.call([r"apt-get", r"upgrade", r"-y"])

# Install Ansible
subprocess.call([r"apt-get", r"install", r"-y", r"ansible-base"])

# Install Ansible Collections
subprocess.call([r"ansible-galaxy", r"collection", r"install", r"community.general"])
subprocess.call([r"ansible-galaxy", r"collection", r"install", r"community.crypto"])
subprocess.call([r"ansible-galaxy", r"collection", r"install", r"community.docker"])

# Create folder for ansible
os.mkdir(r"/ansible_configs")

# Get uid and gid of root
uid = pwd.getpwnam(r"root").pw_uid
gid = pwd.getpwnam(r"root").pw_gid

# Set permissions for ansible config folder
os.chown(r"/ansible_configs" + uid, gid)
os.chmod(r"/ansible_configs", stat.S_IRWXU)

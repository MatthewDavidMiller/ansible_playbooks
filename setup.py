# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm

import subprocess
import os
import pwd
import stat

subprocess.call([r'apt-get', r'update', r'-y'])

subprocess.call([r'apt-get', r'upgrade', r'-y'])

subprocess.call([r'apt-get', r'install', r'-y', r'ansible-base'])

subprocess.call([r'ansible-galaxy', r'collection',
                r'install', r'community.general'])

subprocess.call([r'ansible-galaxy', r'collection',
                r'install', r'community.crypto'])

subprocess.call([r'ansible-galaxy', r'collection',
                r'install', r'community.docker'])

os.mkdir(r'/ansible_configs')
uid = pwd.getpwnam(r'root').pw_uid
gid = pwd.getpwnam(r'root').pw_gid
os.chown(r'/ansible_configs' + uid, gid)
os.chmod(r'/ansible_configs', stat.S_IRWXU)

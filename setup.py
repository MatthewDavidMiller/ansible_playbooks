import subprocess

subprocess.call([r'apt-get', r'update', r'-y'])

subprocess.call([r'apt-get', r'upgrade', r'-y'])

subprocess.call([r'apt-get', r'install', r'-y', r'ansible'])

subprocess.call([r'ansible-galaxy', r'collection',
                r'install', r'community.general'])

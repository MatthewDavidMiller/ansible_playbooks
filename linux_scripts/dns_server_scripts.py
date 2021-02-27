# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm
# https://stackabuse.com/how-to-copy-a-file-in-python/
# https://pynative.com/python-sqlite-insert-into-table/
# https://stackoverflow.com/questions/38780764/how-to-create-a-list-from-a-text-file-in-python
# https://www.geeksforgeeks.org/iterate-over-a-list-in-python/


import os
import stat
import urllib.request
import subprocess
import shutil
import sqlite3
import re


def configure_dns_server_scripts(user_name):
    # Script to archive config files for backup
    urllib.request.urlretrieve(
        r'https://raw.githubusercontent.com/MatthewDavidMiller/scripts/stable/linux_scripts/backup_configs.sh', r'/usr/local/bin/backup_configs.sh')
    os.chmod(r'/usr/local/bin/backup_configs.sh',
             stat.S_IRUSR + stat.S_IXUSR)

    # Script to update root.hints file
    root_hints_text = r'#!/bin/bash' + '\n' + r'wget -O "/home/' + user_name + r'/root.hints" \'https://www.internic.net/domain/named.root\'' + \
        '\n' + r'mv -f "/home/' + user_name + r'/root.hints" \'/var/lib/unbound/\''
    with open(r'/usr/local/bin/update_root_hints.sh', "w") as opened_file:
        opened_file.write(root_hints_text + '\n')
    os.chmod(r'/usr/local/bin/update_root_hints.sh',
             stat.S_IRUSR + stat.S_IXUSR)

    # Configure cron jobs
    cron_jobs_text = r'* 0 * * 1 bash /usr/local/bin/backup_configs.sh &'
    with open(r'jobs.cron', "w") as opened_file:
        opened_file.write(cron_jobs_text + '\n')
    subprocess.call([r'crontab', r'jobs.cron'])
    os.remove(r'jobs.cron')


def configure_unbound():
    urllib.request.urlretrieve(
        r'https://www.internic.net/domain/named.root', r'/var/lib/unbound/root.hints')
    subprocess.call([r'systemctl', r'enable', r'unbound'])
    subprocess.call([r'systemctl', r'start', r'unbound'])
    shutil.copyfile(r'dns_server_configuration/env/pi-hole.conf',
                    r'/etc/unbound/unbound.conf.d/pi-hole.conf')


def install_pihole(user_name):
    subprocess.call([r'sudo', r'-u', user_name, r'git', r'clone', r'--depth', r'1',
                     r'https://github.com/pi-hole/pi-hole.git', r'/home/' + user_name + r'/Pi-hole'])
    subprocess.call([r'sudo', r'-u', user_name, r'bash', r'/home/' +
                     user_name + r'/Pi-hole/automated install/basic-install.sh'])


def configure_pihole():
    allow_block_list = open(
        r'dns_server_configuration/env/allow_block_list.txt').readlines()
    lists = open(
        r'dns_server_configuration/env/lists.txt').readlines()
    shutil.copyfile(r'dns_server_configuration/domains.txt',
                    r'/etc/pihole/custom.list')

    for i in allow_block_list:
        sqlite3.connect(r'/etc/pihole/gravity.db').cursor().execute(i)

    for i in lists:
        sqlite3.connect(r'/etc/pihole/gravity.db').cursor().execute(i)

    shutil.copyfile(r'dns_server_configuration/env/setupVars.conf',
                    r'/etc/pihole/setupVars.conf')

    print(r'Set Pihole Password')
    subprocess.call([r'pihole', r'-a', r'-p'])

    uid = pwd.getpwnam(r'pihole').pw_uid
    gid = pwd.getpwnam(r'pihole').pw_gid
    os.chown(r'/etc/pihole' + uid, gid)
    os.chmod(r'/etc/pihole',
             stat.S_IRWXU + stat.S_IRWXG)

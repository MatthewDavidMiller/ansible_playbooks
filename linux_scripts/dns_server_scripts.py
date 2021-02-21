# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm

import os
import stat
import urllib.request
import subprocess


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

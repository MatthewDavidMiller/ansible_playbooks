# Credits
# https://www.geeksforgeeks.org/python-os-umask-method/
# https://stackoverflow.com/questions/13332268/how-to-use-subprocess-command-with-pipes
# https://www.tutorialspoint.com/python/os_chmod.htm
import subprocess
import os
import pwd
import stat


def install_vpn_server_packages():
    subprocess.call([r'apt-get', r'install', r'-y', r'wireguard', r'ddclient'])


def setup_basic_wireguard_interface(interface, ip_address):
    # Create interface
    subprocess.call([r'ip', r'link', r'add', r'dev',
                     interface, r'type', r'wireguard'])
    # Set ip address
    subprocess.call([r'ip', r'address', r'add', r'dev',
                     interface, ip_address + r'/24'])
    # Activate interface
    subprocess.call([r'ip', r'link', r'set', r'up', r'dev', interface])


def generate_wireguard_key(user_name, key_name):
    os.makedirs(r'/home/' + user_name + r'/.wireguard_keys', exist_ok=True)
    os.umask(r'0o077')
    wg_genkey_output = subprocess.getoutput()([r'wg', r'genkey'])
    with open(r'/home/' + user_name + r'/.wireguard_keys/' + key_name, "w") as opened_file:
        opened_file.write(wg_genkey_output + '\n')

    wg_pubkey_output = subprocess.getoutput(
        ([r'wg', r'pubkey']), stdout=subprocess.PIPE)
    with open(r'/home/' + user_name + r'/.wireguard_keys/' + key_name + r'.pub', "w") as opened_file:
        opened_file.write(wg_pubkey_output + '\n')

    uid = pwd.getpwnam(user_name).pw_uid
    gid = pwd.getpwnam(user_name).pw_gid
    os.chown(r'/home/' + user_name + r'/.wireguard_keys' + uid, gid)

    os.chmod(r'/home/' + user_name + r'/.wireguard_keys', stat.S_IRWXU)

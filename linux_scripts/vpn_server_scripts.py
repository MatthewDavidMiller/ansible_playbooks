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


def configure_wireguard_server_base(wireguard_interface, user_name, server_key_name, ip_address, listen_port, network_interface, vpn_network_prefix):
    with open(r'/home/' + user_name + r'/.wireguard_keys/' + server_key_name, "r") as opened_file:
        private_key = opened_file.read()

    config_text = r'[Interface]' + '\n' + r'Address = ' + ip_address + r'/24' + '\n' + r'ListenPort = ' + listen_port + '\n' + r'PrivateKey = ' + private_key + '\n' + r'PostUp = iptables -A FORWARD -d ' + vpn_network_prefix + r' -i ' + network_interface + r' -o ' + wireguard_interface + r' -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT; iptables -A FORWARD -s ' + vpn_network_prefix + r' -i ' + wireguard_interface + r' -o ' + network_interface + r' -j ACCEPT; iptables -t nat -I POSTROUTING -s ' + \
        vpn_network_prefix + r' -o ' + network_interface + r' -j MASQUERADE' + '\n' + r'PostDown = iptables -A FORWARD -d ' + vpn_network_prefix + r' -i ' + network_interface + r' -o ' + wireguard_interface + r' -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT; iptables -A FORWARD -s ' + \
        vpn_network_prefix + r' -i ' + wireguard_interface + r' -o ' + network_interface + \
        r' -j ACCEPT; iptables -t nat -I POSTROUTING -s ' + \
        vpn_network_prefix + r' -o ' + network_interface + r' -j MASQUERADE'

    with open(r'/etc/wireguard/' + wireguard_interface + r'.conf', "w") as opened_file:
        opened_file.write(config_text + '\n')


def add_wireguard_peer(interface, user_name, client_key_name, ip_address):
    with open(r'/home/' + user_name + r'/.wireguard_keys/' + client_key_name + r'.pub', "r") as opened_file:
        public_key = opened_file.read()

    config_text = r'# ' + client_key_name + '\n' + \
        r'[Peer]' + '\n' + r'PublicKey = ' + public_key + \
        '\n' + r'AllowedIPs = ' + ip_address + r'/32'

    with open(r'/etc/wireguard/' + interface + r'.conf', "w") as opened_file:
        opened_file.write(config_text + '\n')


def wireguard_create_client_config(user_name, client_key_name, server_key_name, ip_address, dns_server, public_dns_ip_address, listen_port):
    with open(r'/home/' + user_name + r'/.wireguard_keys/' + client_key_name, "r") as opened_file:
        private_key = opened_file.read()

    with open(r'/home/' + user_name + r'/.wireguard_keys/' + client_key_name + r'.pub', "r") as opened_file:
        public_key = opened_file.read()

    os.makedirs(r'/home/' + user_name +
                r'/.wireguard_client_configs', exist_ok=True)

    config_text = r'[Interface]' + '\n' + r'Address = ' + ip_address + '\n' + r'PrivateKey = ' + private_key + '\n' + r'DNS = ' + dns_server + '\n\n' + \
        r'[Peer]' + '\n' + r'PublicKey = ' + public_key + '\n' + r'AllowedIPs = 0.0.0.0/0, ::/0' + \
        '\n' + r'Endpoint = ' + public_dns_ip_address + r':' + listen_port

    with open(r'/home/' + user_name + r'/.wireguard_client_configs/' + client_key_name + r'.conf', "w") as opened_file:
        opened_file.write(config_text + '\n')


def enable_wireguard_service(interface):
    subprocess.call(
        [r'systemctl', r'start', r'wg-quick@' + interface + r'.service'])
    subprocess.call(
        [r'systemctl', r'enable', r'wg-quick@' + interface + r'.service'])

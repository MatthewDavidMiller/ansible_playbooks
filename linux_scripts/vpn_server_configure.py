# Credits
# https://stackoverflow.com/questions/19964603/creating-a-menu-in-python

import urllib.request

# Get needed scripts
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/VPN-Server-Configuration/stable/linux_scripts/vpn_server_scripts.py', r'vpn_server_scripts.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/functions.py', r'functions.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/apt_auto_updates.py', r'apt_auto_updates.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/configure_network.py', r'configure_network.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/configure_ssh.py', r'configure_ssh.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/generate_ssh_key.py', r'generate_ssh_key.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/iptables_base.py', r'iptables_base.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/iptables_rules.py', r'iptables_rules.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/log_rotate_configure.py', r'log_rotate_configure.py')

# Import functions from files
import vpn_server_scripts  # type: ignore # nopep8
import functions  # type: ignore # nopep8
import apt_auto_updates  # type: ignore # nopep8
import configure_network  # type: ignore # nopep8
import configure_ssh  # type: ignore # nopep8
import generate_ssh_key  # type: ignore # nopep8
import iptables_base  # type: ignore # nopep8
import iptables_rules  # type: ignore # nopep8
import log_rotate_configure  # type: ignore # nopep8
import env  # type: ignore # nopep8

functions.get_linux_headers()
linux_headers = functions.linux_headers
env.env(linux_headers)
release_name = r'buster'
key_name = env.key_name
ip_address = env.ip_address
network_address = env.network_address
subnet_mask = env.subnet_mask
gateway_address = env.gateway_address
dns_address = env.dns_address
network_prefix = env.network_prefix
ipv6_link_local_address = env.ipv6_link_local_address
wireguard_interface = env.wireguard_interface
wireguard_server_ip_address = env.wireguard_server_ip_address
wireguard_server_network_prefix = env.wireguard_server_network_prefix
wireguard_server_vpn_key_name = env.wireguard_server_vpn_key_name
wireguard_client_key_name = env.wireguard_client_key_name
wireguard_server_listen_port = env.wireguard_server_listen_port
wireguard_client_ip_address = env.wireguard_client_ip_address
wireguard_dns_server = env.wireguard_dns_server
wireguard_public_dns_ip_address = env.wireguard_public_dns_ip_address
user_name = env.user_name
device_hostname = env.device_hostname
packages = env.packages
functions.get_interface_name()
interface = functions.interface

# Option Menu
option_menu = {}
option_menu['1'] = r'Pre-Setup'
option_menu['2'] = r'Main Setup.'
option_menu['3'] = r'Add wireguard client'
option_menu['4'] = r'Exit'

# Setup Selections
while True:
    selection_options = option_menu.keys()
    for entry in selection_options:
        print(entry, option_menu[entry])

    selection = input(r'Select an option: ')
    if selection == '1':
        functions.lock_root()
        configure_network.configure_network(
            ip_address, network_address, subnet_mask, gateway_address, dns_address, interface, ipv6_link_local_address)
        functions.install_packages(packages)
        vpn_server_scripts.install_vpn_server_packages()
        print(r'Reboot the OS before configuring wireguard: ')
        input()
    elif selection == '2':
        configure_ssh.configure_ssh()
        generate_ssh_key.generate_ssh_key(
            user_name, r'y', r'n', r'n', key_name)
        functions.setup_config_backups()
        functions.configure_ddclient(wireguard_public_dns_ip_address)
        vpn_server_scripts.setup_basic_wireguard_interface(
            wireguard_interface, wireguard_server_ip_address)
        vpn_server_scripts.generate_wireguard_key(
            user_name, wireguard_server_vpn_key_name)
        vpn_server_scripts.configure_wireguard_server_base(wireguard_interface, user_name, wireguard_server_vpn_key_name,
                                                           wireguard_server_ip_address, wireguard_server_listen_port, interface, wireguard_server_network_prefix)
        vpn_server_scripts.generate_wireguard_key(
            user_name, wireguard_client_key_name)
        vpn_server_scripts.add_wireguard_peer(
            wireguard_interface, user_name, wireguard_client_key_name, wireguard_client_ip_address)
        vpn_server_scripts.wireguard_create_client_config(user_name, wireguard_client_key_name, wireguard_server_vpn_key_name,
                                                          wireguard_client_ip_address, wireguard_dns_server, wireguard_public_dns_ip_address, wireguard_server_listen_port)
        vpn_server_scripts.enable_wireguard_service(wireguard_interface)
        iptables_base.iptables_setup_base()
        iptables_rules.iptables_allow_ssh(network_prefix, interface)
        iptables_base.iptables_set_defaults()
        iptables_rules.iptables_allow_vpn_port(
            interface, wireguard_server_listen_port)
        iptables_rules.iptables_allow_icmp(network_prefix, interface)
        iptables_rules.iptables_allow_loopback()
        iptables_base.iptables_allow_forwarding()
        apt_auto_updates.apt_configure_auto_update_reboot()
        log_rotate_configure(user_name)

    elif selection == '3':
        print(r'Enter wireguard client name: ')
        wireguard_client_key_name = input()
        print(r'Enter wireguard client ip address: ')
        wireguard_client_ip_address = input()
        vpn_server_scripts.generate_wireguard_key(
            user_name, wireguard_client_key_name)
        vpn_server_scripts.add_wireguard_peer(
            wireguard_interface, user_name, wireguard_client_key_name, wireguard_client_ip_address)
        vpn_server_scripts.wireguard_create_client_config(user_name, wireguard_client_key_name, wireguard_server_vpn_key_name,
                                                          wireguard_client_ip_address, wireguard_dns_server, wireguard_public_dns_ip_address, wireguard_server_listen_port)
    elif selection == '4':
        break
    else:
        print(r'Incorrect input')

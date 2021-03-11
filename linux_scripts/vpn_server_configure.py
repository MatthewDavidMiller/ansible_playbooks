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
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/create_swap_file.py', r'create_swap_file.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/generate_ssh_key.py', r'generate_ssh_key.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/iptables_base.py', r'iptables_base.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/iptables_rules.py', r'iptables_rules.py')
urllib.request.urlretrieve(
    r'https://raw.githubusercontent.com/MatthewDavidMiller/Bash_Python_Common_Functions/main/functions/log_rotate_configure.py', r'log_rotate_configure.py')

# Import functions from files
from vpn_server_scripts import *  # type: ignore # nopep8
from functions import *  # type: ignore # nopep8
from apt_auto_updates import *  # type: ignore # nopep8
from configure_network import *  # type: ignore # nopep8
from configure_ssh import *  # type: ignore # nopep8
from create_swap_file import *  # type: ignore # nopep8
from generate_ssh_key import *  # type: ignore # nopep8
from iptables_base import *  # type: ignore # nopep8
from iptables_rules import *  # type: ignore # nopep8
from log_rotate_configure import *  # type: ignore # nopep8
from env import *  # type: ignore # nopep8

# Option Menu
option_menu = {}
option_menu['1'] = r'Pre-Setup'
option_menu['2'] = r'Main Setup.'
option_menu['3'] = r'Add wireguard client'
option_menu['4'] = r'Exit'

# Setup Selections
while True:
    selection_options = option_menu.keys()
    selection_options.sort()
    for entry in selection_options:
        print(entry, option_menu[entry])

    selection = input(r'Select an option: ')
    if selection == '1':
        get_linux_headers()
        env(linux_headers)
        lock_root(user_name)
        get_interface_name
        configure_network(ip_address, network_address, subnet_mask,
                          gateway_address, dns_address, interface, ipv6_link_local_address)
        install_packages
        install_vpn_server_packages()
        print(r'Reboot the OS before configuring wireguard: ')
        input()
    elif selection == '2':
        configure_ssh
        generate_ssh_key(user_name, r'y', r'n', r'n', key_name)
        setup_config_backups
        configure_ddclient(wireguard_public_dns_ip_address)
        setup_basic_wireguard_interface(
            wireguard_interface, wireguard_server_ip_address)
        generate_wireguard_key(user_name, wireguard_server_vpn_key_name)
        configure_wireguard_server_base(wireguard_interface, user_name, wireguard_server_vpn_key_name,
                                        wireguard_server_ip_address, wireguard_server_listen_port, interface, wireguard_server_network_prefix)
        generate_wireguard_key(user_name, wireguard_client_key_name)
        add_wireguard_peer(wireguard_interface, user_name,
                           wireguard_client_key_name, wireguard_client_ip_address)
        wireguard_create_client_config(user_name, wireguard_client_key_name, wireguard_server_vpn_key_name,
                                       wireguard_client_ip_address, wireguard_dns_server, wireguard_public_dns_ip_address, wireguard_server_listen_port)
        enable_wireguard_service(wireguard_interface)
        get_interface_name
        iptables_setup_base
        iptables_allow_ssh(network_prefix, interface)
        iptables_set_defaults
        iptables_allow_vpn_port(interface, wireguard_server_listen_port)
        iptables_allow_icmp(network_prefix, interface)
        iptables_allow_loopback
        iptables_allow_forwarding
        apt_configure_auto_update_reboot()
        log_rotate_configure(user_name)

    elif selection == '3':
        print(r'Enter wireguard client name: ')
        wireguard_client_key_name = input()
        print(r'Enter wireguard client ip address: ')
        wireguard_client_ip_address = input()
        generate_wireguard_key(user_name, wireguard_client_key_name)
        add_wireguard_peer(wireguard_interface, user_name,
                           wireguard_client_key_name, wireguard_client_ip_address)
        wireguard_create_client_config(user_name, wireguard_client_key_name, wireguard_server_vpn_key_name,
                                       wireguard_client_ip_address, wireguard_dns_server, wireguard_public_dns_ip_address, wireguard_server_listen_port)
    elif selection == '4':
        break
    else:
        print(r'Incorrect input')

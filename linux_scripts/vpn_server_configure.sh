#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.
# Run with sudo. Do not run while logged into root.
# Configuration script for the VPN server.

# Get needed scripts
wget -O 'vpn_server_scripts.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/VPN-Server-Configuration/stable/linux_scripts/vpn_server_scripts.sh'

# Source functions
source vpn_server_scripts.sh

# Default variables
release_name='buster'
key_name='vpn_key'
ip_address='10.1.10.6'
network_address='10.1.10.0'
subnet_mask='255.255.255.0'
gateway_address='10.1.10.1'
dns_address='1.1.1.1'
network_prefix='10.0.0.0/8'
limit_ssh='y'
limit_port_64640='y'
wireguard_interface='wg0'
wireguard_server_ip_address='10.3.0.1'
wireguard_server_vpn_key_name='wireguard_vpn_server'
wireguard_client_key_name='matthew_wireguard'
wireguard_server_listen_port='64640'
wireguard_client_ip_address='10.3.0.2'
wireguard_client_password=''
wireguard_dns_server='10.1.10.5'
wireguard_public_dns_ip_address='mattm.mooo.com'

# Prompts
read -r -p "Generate more than one wireguard client configs? [y/N] " wireguard_clients_response
read -r -p "Enter wireguard client password: " wireguard_client_password

# Call functions
lock_root
get_username
get_interface_name
configure_network "${ip_address}" "${network_address}" "${subnet_mask}" "${gateway_address}" "${dns_address}" "${interface}"
fix_apt_packages
install_vpn_server_packages
configure_ssh
generate_ssh_key "${user_name}" "y" "n" "n" "${key_name}"
configure_ufw_base
ufw_configure_rules "${network_prefix}" "${limit_ssh}" "${limit_port_64640}"
ufw_allow_default_forward
ufw_allow_ip_forwarding
configure_vpn_scripts
setup_basic_wireguard_interface "${wireguard_interface}" "${wireguard_server_ip_address}"
generate_wireguard_key "${user_name}" "${wireguard_server_vpn_key_name}"
configure_wireguard_server_base "${wireguard_interface}" "${user_name}" "${wireguard_server_vpn_key_name}" "${wireguard_server_ip_address}" "${wireguard_server_listen_port}"
generate_wireguard_key "${user_name}" "${wireguard_client_key_name}"
add_wireguard_peer "${wireguard_interface}" "${user_name}" "${wireguard_server_vpn_key_name}" "${wireguard_client_ip_address}" "${wireguard_client_password}"
wireguard_create_client_config "${wireguard_interface}" "${user_name}" "${wireguard_client_key_name}" "${wireguard_server_vpn_key_name}" "${wireguard_client_ip_address}" "${wireguard_client_password}" "${wireguard_dns_server}" "${wireguard_public_dns_ip_address}" "${wireguard_server_listen_port}"

while [[ "${wireguard_clients_response}" =~ ^([yY][eE][sS]|[yY])+$ ]]; do
    read -r -p "Enter wireguard client name: " wireguard_client_key_name
    read -r -p "Enter wireguard client ip address: " wireguard_client_ip_address
    read -r -p "Enter wireguard client password: " wireguard_client_password
    generate_wireguard_key "${user_name}" "${wireguard_client_key_name}"
    add_wireguard_peer "${wireguard_interface}" "${user_name}" "${wireguard_server_vpn_key_name}" "${wireguard_client_ip_address}" "${wireguard_client_password}"
    wireguard_create_client_config "${wireguard_interface}" "${user_name}" "${wireguard_client_key_name}" "${wireguard_server_vpn_key_name}" "${wireguard_client_ip_address}" "${wireguard_client_password}" "${wireguard_dns_server}" "${wireguard_public_dns_ip_address}" "${wireguard_server_listen_port}"
    read -r -p "Add another wireguard client? [y/N] " wireguard_clients_loop_response

    if [[ "${wireguard_clients_loop_response}" =~ ^([nN][oO]|[nN])+$ ]]; then
        break
    fi
done

apt_configure_auto_updates "${release_name}"
enable_ufw
enable_wireguard_service "${wireguard_interface}"

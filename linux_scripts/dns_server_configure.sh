#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.
# Run with sudo. Do not run while logged into root.
# Configuration script for a DNS server.

# Get needed scripts
wget -O 'dns_server_scripts.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/dns_server_scripts.sh'

# Source functions
source dns_server_scripts.sh

# Default variables
release_name='buster'
key_name='pihole_key'
ip_address='10.1.10.5'
network_address='10.1.10.0'
subnet_mask='255.255.255.0'
gateway_address='10.1.10.1'
dns_address='1.1.1.1'
network_prefix='10.0.0.0/8'
loopback='127.0.0.1'
ipv6_link_local_address='fe80::5'

# Call functions
lock_root
get_username
get_interface_name
configure_network "${ip_address}" "${network_address}" "${subnet_mask}" "${gateway_address}" "${dns_address}" "${interface}" "${ipv6_link_local_address}"
get_ipv6_link_local_address
fix_apt_packages
install_dns_server_packages
configure_ssh
generate_ssh_key "${user_name}" "y" "n" "n" "${key_name}"
iptables_setup_base "${interface}" "${network_prefix}"
iptables_allow_ssh "${network_prefix}" "${interface}"
iptables_allow_dns "${network_prefix}" "${interface}"
iptables_allow_http "${network_prefix}" "${interface}"
iptables_allow_https "${network_prefix}" "${interface}"
iptables_allow_icmp "${network_prefix}" "${interface}"
iptables_allow_loopback
iptables_set_defaults
apt_configure_auto_updates "${release_name}"
configure_dns_server_scripts
configure_unbound
configure_pihole

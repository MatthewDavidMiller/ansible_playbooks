#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.
# Run with sudo. Do not run while logged into root.
# Configuration script for the TP Link Omada Controller.

# Get needed scripts
wget -O 'omada_controller_scripts.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Access-Point-Controller-Configuration/stable/linux_scripts/omada_controller_scripts.sh'

# Source functions
source omada_controller_scripts.sh

# Default variables
release_name='buster'
key_name='omada_controller_key'
ip_address='10.1.10.7'
network_address='10.1.10.0'
subnet_mask='255.255.255.0'
gateway_address='10.1.10.1'
dns_address='1.1.1.1'
network_prefix='10.0.0.0/8'

# Call functions
lock_root
get_username
get_interface_name
configure_network "${ip_address}" "${network_address}" "${subnet_mask}" "${gateway_address}" "${dns_address}" "${interface}"
fix_apt_packages
install_omada_controller_packages
configure_ssh
generate_ssh_key "${user_name}" "y" "n" "n" "${key_name}"
iptables_setup_base "${interface}" "${network_prefix}"
iptables_allow_ssh "${network_prefix}" "${ip_address}"
iptables_allow_omada_controller "${network_prefix}" "${ip_address}"
iptables_set_defaults
apt_configure_auto_updates "${release_name}"
configure_omada_controller

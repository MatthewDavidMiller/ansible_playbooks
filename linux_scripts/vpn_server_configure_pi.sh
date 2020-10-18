#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.
# Run with sudo. Do not run while logged into root.
# Configuration script for the VPN server.

# Get needed scripts
wget -O 'vpn_server_scripts_pi.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/VPN-Server-Configuration/stable/linux_scripts/vpn_server_scripts_pi.sh'

# Source functions
source vpn_server_scripts_pi.sh

# Default variables
release_name='buster'
key_name='vpn_key'
ip_address='10.1.10.6'
network_address='10.1.10.0'
subnet_mask='255.255.255.0'
gateway_address='10.1.10.1'
dns_address='1.1.1.1'
network_prefix='10.0.0.0/8'
ipv6_link_local_address='fe80::6'
wireguard_interface='wg0'
wireguard_server_ip_address='10.3.0.1'
wireguard_server_network_prefix='10.3.0.0/24'
wireguard_server_vpn_key_name='wireguard_vpn_server'
wireguard_client_key_name='matthew'
wireguard_server_listen_port='64640'
wireguard_client_ip_address='10.3.0.2'
wireguard_dns_server='10.1.10.5'
wireguard_public_dns_ip_address='mattm.mooo.com'
swap_file_size='512'
user_name='matthew'

PS3='Select Configuration Option: '
options=("Set variables" "Base Configuration" "Configure Wireguard" "Add a wireguard Client" "Configure Iptables" "Configure Auto Updates" "Configure Log Rotate" "Quit")

select options_select in "${options[@]}"; do
    case $options_select in

    "Set variables")
        PS3='Select Variable to configure: '
        options=("Set the release name" "Set the key name" "Set the OS network" "Set the wireguard network" "Set the swap file size" "Set the user name" "Quit")

        select options_select in "${options[@]}"; do
            case $options_select in

            "Set the release name")
                read -r -p "Set the release name: " release_name
                read -r -p "Set the ip address of the OS: " ip_address
                ;;
            "Set the key name")
                read -r -p "Set the key name: " key_name
                ;;
            "Set the OS network")
                read -r -p "Set the network address of the OS: " network_address
                read -r -p "Set the subnet mask of the OS: " subnet_mask
                read -r -p "Set the gateway address of the OS: " gateway_address
                read -r -p "Set the dns address of the OS: " dns_address
                read -r -p "Set the network prefix of the OS: " network_prefix
                read -r -p "Set the ipv6 link local address of the OS: " ipv6_link_local_address
                ;;
            "Set the wireguard network")
                read -r -p "Set the wireguard interface name: " wireguard_interface
                read -r -p "Set the wireguard server ip address: " wireguard_server_ip_address
                read -r -p "Set the wireguard server network prefix: " wireguard_server_network_prefix
                read -r -p "Set the wireguard server vpn key name: " wireguard_server_vpn_key_name
                read -r -p "Set the wireguard client key name: " wireguard_client_key_name
                read -r -p "Set the wireguard dns server: " wireguard_dns_server
                read -r -p "Set the wireguard public dns name: " wireguard_public_dns_ip_address
                ;;
            "Set the swap file size")
                read -r -p "Set the swap file size: " swap_file_size
                ;;
            "Set the user name")
                read -r -p "Specify the user name of the Linux user: " user_name
                ;;
            "Quit")
                break
                ;;
            *) echo "$REPLY is not an option" ;;
            esac
        done
        ;;

    "Base Configuration")
        read -r -p "Enter code for dynamic dns: " dynamic_dns
        # get_username
        add_user_to_sudo
        create_swap_file "${swap_file_size}"
        set_shell_bash "${user_name}"
        add_backports_repository "${release_name}"
        lock_root
        get_interface_name
        configure_network "${ip_address}" "${network_address}" "${subnet_mask}" "${gateway_address}" "${dns_address}" "${interface}" "${ipv6_link_local_address}"
        fix_apt_packages
        install_vpn_server_packages "${release_name}"
        configure_ssh
        generate_ssh_key "${user_name}" "y" "n" "n" "${key_name}"
        configure_vpn_scripts "${dynamic_dns}" "${release_name}"
        read -r -p "Reboot the OS before configuring wireguard:"
        ;;
    "Configure Wireguard")
        setup_basic_wireguard_interface "${wireguard_interface}" "${wireguard_server_ip_address}"
        generate_wireguard_key "${user_name}" "${wireguard_server_vpn_key_name}"
        configure_wireguard_server_base "${wireguard_interface}" "${user_name}" "${wireguard_server_vpn_key_name}" "${wireguard_server_ip_address}" "${wireguard_server_listen_port}" "${interface}" "${wireguard_server_network_prefix}"
        generate_wireguard_key "${user_name}" "${wireguard_client_key_name}"
        add_wireguard_peer "${wireguard_interface}" "${user_name}" "${wireguard_client_key_name}" "${wireguard_client_ip_address}"
        wireguard_create_client_config "${user_name}" "${wireguard_client_key_name}" "${wireguard_server_vpn_key_name}" "${wireguard_client_ip_address}" "${wireguard_dns_server}" "${wireguard_public_dns_ip_address}" "${wireguard_server_listen_port}"
        enable_wireguard_service "${wireguard_interface}"
        ;;
    "Add a wireguard Client")
        read -r -p "Enter wireguard client name: " wireguard_client_key_name
        read -r -p "Enter wireguard client ip address: " wireguard_client_ip_address
        generate_wireguard_key "${user_name}" "${wireguard_client_key_name}"
        add_wireguard_peer "${wireguard_interface}" "${user_name}" "${wireguard_client_key_name}" "${wireguard_client_ip_address}"
        wireguard_create_client_config "${user_name}" "${wireguard_client_key_name}" "${wireguard_server_vpn_key_name}" "${wireguard_client_ip_address}" "${wireguard_dns_server}" "${wireguard_public_dns_ip_address}" "${wireguard_server_listen_port}"
        ;;
    "Configure Iptables")
        iptables_setup_base
        iptables_allow_ssh "${network_prefix}" "${interface}"
        iptables_set_defaults
        iptables_allow_vpn_port "${interface}" "${wireguard_server_listen_port}"
        iptables_allow_icmp "${network_prefix}" "${interface}"
        iptables_allow_loopback
        iptables_allow_forwarding
        ;;
    "Configure Auto Updates")
        apt_configure_auto_updates "${release_name}"
        ;;
    "Configure Log Rotate")
        log_rotate_configure "${user_name}"
        ;;
    "Quit")
        break
        ;;
    *) echo "$REPLY is not an option" ;;
    esac
done

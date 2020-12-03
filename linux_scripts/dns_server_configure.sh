#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.
# Run with sudo. Do not run while logged into root.
# Configuration script for a DNS server.

# Get needed scripts
wget -O 'dns_server_scripts.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/dns_server_scripts.sh'
wget -O 'apt_auto_updates.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/apt_auto_updates.sh'
wget -O 'configure_network.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/configure_network.sh'
wget -O 'configure_ssh.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/configure_ssh.sh'
wget -O 'create_swap_file.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/create_swap_file.sh'
wget -O 'functions.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/functions.sh'
wget -O 'generate_ssh_key.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/generate_ssh_key.sh'
wget -O 'iptables_base.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/iptables_base.sh'
wget -O 'iptables_rules.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/iptables_rules.sh'
wget -O 'log_rotate_configure.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/log_rotate_configure.sh'

# Source variables
source env.sh

# Source functions
source dns_server_scripts.sh
source apt_auto_updates.sh
source configure_network.sh
source configure_ssh.sh
source create_swap_file.sh
source functions.sh
source generate_ssh_key.sh
source iptables_base.sh
source iptables_rules.sh
source log_rotate_configure.sh

PS3='Select Configuration Option: '
options=("Set variables" "Base Configuration" "Configure Unbound" "Configure Pihole" "Configure Iptables" "Configure Auto Updates" "Configure Log Rotate" "Quit")

select options_select in "${options[@]}"; do
    case $options_select in

    "Set variables")
        PS3='Select Variable to configure: '
        options=("Set the release name" "Set the key name" "Set the OS network" "Set the swap file size" "Set the user name" "Set the hostname" "Quit")

        select options_select in "${options[@]}"; do
            case $options_select in

            "Set the release name")
                read -r -p "Set the release name: " release_name
                ;;
            "Set the key name")
                read -r -p "Set the key name: " key_name
                ;;
            "Set the OS network")
                read -r -p "Set the ip address of the OS: " ip_address
                read -r -p "Set the network address of the OS: " network_address
                read -r -p "Set the subnet mask of the OS: " subnet_mask
                read -r -p "Set the gateway address of the OS: " gateway_address
                read -r -p "Set the dns address of the OS: " dns_address
                read -r -p "Set the network prefix of the OS: " network_prefix
                read -r -p "Set the ipv6 link local address of the OS: " ipv6_link_local_address
                ;;
            "Set the swap file size")
                read -r -p "Set the swap file size: " swap_file_size
                ;;
            "Set the user name")
                read -r -p "Specify the user name of the Linux user: " user_name
                ;;
            "Set the hostname")
                read -r -p "Specify the hostname for the device: " device_hostname
                ;;
            "Quit")
                break
                ;;
            *) echo "$REPLY is not an option" ;;
            esac
        done
        ;;

    "Base Configuration")
        PS3='Select Configuration Option: '
        options=("Set the timezone" "Set the language" "Set the Hostname and hosts file" "Create an user" "Add user to sudo" "Create a swap file" "Set the shell to bash" "Lock root" "Configure Network" "Install DNS server packages" "Configure SSH" "Configure DNS Scripts" "Quit")

        select options_select in "${options[@]}"; do
            case $options_select in

            "Set the timezone")
                set_timezone
                ;;
            "Set the language")
                set_language
                ;;
            "Set the Hostname and hosts file")
                set_hostname "${device_hostname}"
                setup_hosts_file "${device_hostname}"
                ;;
            "Create an user")
                create_user "${user_name}"
                ;;
            "Add user to sudo")
                add_user_to_sudo "${user_name}"
                ;;
            "Create a swap file")
                create_swap_file "${swap_file_size}"
                ;;
            "Set the shell to bash")
                set_shell_bash "${user_name}"
                ;;
            "Lock root")
                lock_root "${user_name}"
                ;;
            "Configure Network")
                get_interface_name
                configure_network "${ip_address}" "${network_address}" "${subnet_mask}" "${gateway_address}" "${dns_address}" "${interface}" "${ipv6_link_local_address}"
                ;;
            "Install DNS server packages")
                fix_apt_packages
                install_dns_server_packages
                ;;
            "Configure SSH")
                configure_ssh
                generate_ssh_key "${user_name}" "y" "n" "n" "${key_name}"
                ;;
            "Configure DNS Scripts")
                configure_dns_server_scripts
                ;;
            "Quit")
                break
                ;;
            *) echo "$REPLY is not an option" ;;
            esac
        done
        ;;

    "Configure Unbound")
        configure_unbound
        ;;
    "Configure Pihole")
        configure_pihole
        ;;
    "Configure Iptables")
        get_interface_name
        iptables_setup_base
        iptables_allow_ssh "${network_prefix}" "${interface}"
        iptables_allow_dns "${network_prefix}" "${interface}"
        iptables_allow_http "${network_prefix}" "${interface}"
        iptables_allow_https "${network_prefix}" "${interface}"
        iptables_allow_icmp "${network_prefix}" "${interface}"
        iptables_allow_loopback
        iptables_set_defaults
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

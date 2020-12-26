#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.
# Run with sudo. Do not run while logged into root.
# Configuration script for a DNS server.
# Credit to, https://linuxize.com/post/bash-check-if-file-exists/

# Create driectory for scripts
if [ ! -d 'dns_server_configuration' ]; then
    mkdir -p 'dns_server_configuration'
fi

# Get needed scripts
wget -O 'dns_server_configuration/dns_server_scripts.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/dns_server_scripts.sh'
wget -O 'dns_server_configuration/apt_auto_updates.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/apt_auto_updates.sh'
wget -O 'dns_server_configuration/configure_network.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/configure_network.sh'
wget -O 'dns_server_configuration/configure_ssh.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/configure_ssh.sh'
wget -O 'dns_server_configuration/create_swap_file.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/create_swap_file.sh'
wget -O 'dns_server_configuration/functions.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/functions.sh'
wget -O 'dns_server_configuration/generate_ssh_key.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/generate_ssh_key.sh'
wget -O 'dns_server_configuration/iptables_base.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/iptables_base.sh'
wget -O 'dns_server_configuration/iptables_rules.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/iptables_rules.sh'
wget -O 'dns_server_configuration/log_rotate_configure.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/Bash-Common-Functions/main/functions/log_rotate_configure.sh'
wget -O 'dns_server_configuration/env_example.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/env_example.sh'
wget -O 'dns_server_configuration/set_variables.sh' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/set_variables.sh'
wget -O 'dns_server_configuration/allow_block_list_example.txt' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/allow_block_list_example.txt'
wget -O 'dns_server_configuration/domains_example.txt' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/domains_example.txt'
wget -O 'dns_server_configuration/lists_example.txt' 'https://raw.githubusercontent.com/MatthewDavidMiller/DNS-Server-Configuration/stable/linux_scripts/lists_example.txt'

if [ ! -f 'dns_server_configuration/env.sh' ]; then
    echo 'No env.sh file found. An example is available to see formatting.'
    read -r -p "Continue? [y/N] " response
    if [[ "${response}" =~ ^([nN][oO]|[nN])+$ ]]; then
        exit
    fi
fi

# Source variables
if [ -f 'dns_server_configuration/env.sh' ]; then
    source 'dns_server_configuration/env.sh'
fi

# Source functions
source 'dns_server_configuration/dns_server_scripts.sh'
source 'dns_server_configuration/apt_auto_updates.sh'
source 'dns_server_configuration/configure_network.sh'
source 'dns_server_configuration/configure_ssh.sh'
source 'dns_server_configuration/create_swap_file.sh'
source 'dns_server_configuration/functions.sh'
source 'dns_server_configuration/generate_ssh_key.sh'
source 'dns_server_configuration/iptables_base.sh'
source 'dns_server_configuration/iptables_rules.sh'
source 'dns_server_configuration/log_rotate_configure.sh'
source 'dns_server_configuration/set_variables.sh'

PS3='Select Configuration Option: '
options=(
    "Set variables"
    "Continue"
)

select options_select in "${options[@]}"; do
    case $options_select in

    "Set variables")
        set_variables
        ;;
    "Continue")
        break
        ;;
    *) echo "$REPLY is not an option" ;;
    esac
done

PS3='Select Configuration Option: '
options=(
    "Set the timezone"
    "Set the language"
    "Set the Hostname and hosts file"
    "Create an user"
    "Allow wheel group for sudo"
    "Add user to sudo"
    "Create a swap file"
    "Set the shell to bash"
    "Lock root"
    "Configure Network"
    "Install DNS server packages"
    "Configure SSH"
    "Configure DNS Scripts"
    "Configure Unbound"
    "Configure Pihole"
    "Configure Iptables"
    "Configure Auto Updates"
    "Configure Log Rotate"
    "Quit"
)

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

    "Allow wheel group for sudo")
        allow_wheel_sudo
        ;;

    "Add user to sudo")
        add_user_to_sudo_group "${user_name}"
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
        install_packages
        ;;
    "Configure SSH")
        configure_ssh
        generate_ssh_key "${user_name}" "y" "n" "n" "${key_name}"
        ;;
    "Configure DNS Scripts")
        configure_dns_server_scripts
        ;;

    "Configure Unbound")
        configure_unbound
        ;;
    "Configure Pihole")
        if [ -f 'dns_server_configuration/allow_block_list.txt' ]; then
            source 'dns_server_configuration/allow_block_list.txt'
        else
            echo 'No allow_block_list.txt file found, create one to continue. An example is available to see formatting.'
            exit
        fi

        if [ -f 'dns_server_configuration/domains.txt' ]; then
            source 'dns_server_configuration/domains.txt'
        else
            echo 'No domains.txt file found, create one to continue. An example is available to see formatting.'
            exit
        fi

        if [ -f 'dns_server_configuration/lists.txt' ]; then
            source 'dns_server_configuration/lists.txt'
        else
            echo 'No lists.txt file found, create one to continue. An example is available to see formatting.'
            exit
        fi

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

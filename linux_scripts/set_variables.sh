#!/bin/bash

function set_variables() {
    PS3='Select Variable to configure: '
    options=(
        "Set the release name"
        "Set the key name"
        "Set the OS network"
        "Set the swap file size"
        "Set the user name"
        "Set the hostname"
        "Quit"
    )

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
}

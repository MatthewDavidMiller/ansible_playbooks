#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.

# Compilation of functions for the VPN Server.

function install_vpn_server_packages() {
    # Parameters
    local release_name=${1}

    apt-get -t "${release_name}-backports" install -y wireguard
    apt-get install -y ddclient
}

function configure_vpn_scripts() {
    # Parameters
    release_name=${1}

    # Script to get emails on openvpn connections
    #wget 'https://raw.githubusercontent.com/MatthewDavidMiller/scripts/stable/linux_scripts/email_on_vpn_connections.sh'
    #mv 'email_on_vpn_connections.sh' '/usr/local/bin/email_on_vpn_connections.sh'
    #chmod +x '/usr/local/bin/email_on_vpn_connections.sh'
    #wget 'https://raw.githubusercontent.com/MatthewDavidMiller/scripts/stable/linux_scripts/email_on_vpn_connections.py'
    #mv 'email_on_vpn_connections.py' '/usr/local/bin/email_on_vpn_connections.py'
    #chmod +x '/usr/local/bin/email_on_vpn_connections.py'

    # Script to archive config files for backup
    wget 'https://raw.githubusercontent.com/MatthewDavidMiller/scripts/stable/linux_scripts/backup_configs.sh'
    mv 'backup_configs.sh' '/usr/local/bin/backup_configs.sh'
    chmod +x '/usr/local/bin/backup_configs.sh'

    # Configure cron jobs
    cat <<EOF >jobs.cron
@reboot apt-get update && apt-get -t ${release_name}-backports install -y wireguard &
* 0 * * 1 bash /usr/local/bin/backup_configs.sh &
#@reboot nohup bash /usr/local/bin/email_on_vpn_connections.sh &
* 0 * * * '/sbin/reboot'

EOF
    crontab jobs.cron
    rm -f jobs.cron
}

function setup_basic_wireguard_interface() {
    # Parameters
    local interface=${1}
    local ip_address=${2}

    # Create interface
    ip link add dev "${interface}" type wireguard
    # Set ip address
    ip address add dev "${interface}" "${ip_address}/24"
    # Activate interface
    ip link set up dev "${interface}"
}

function generate_wireguard_key() {
    # Parameters
    local user_name=${1}
    local key_name=${2}

    mkdir -p "/home/${user_name}/.wireguard_keys"
    umask 077
    wg genkey | tee "/home/${user_name}/.wireguard_keys/${key_name}" | wg pubkey >"/home/${user_name}/.wireguard_keys/${key_name}.pub"
    chmod -R 700 "/home/${user_name}/.wireguard_keys"
    chown "${user_name}" "/home/${user_name}/.wireguard_keys"
}

function configure_wireguard_server_base() {
    # Parameters
    local wireguard_interface=${1}
    local user_name=${2}
    local server_key_name=${3}
    local ip_address=${4}
    local listen_port=${5}
    local network_interface=${6}
    local vpn_network_prefix=${7}

    local private_key
    private_key=$(cat "/home/${user_name}/.wireguard_keys/${server_key_name}")

    cat <<EOF >"/etc/wireguard/${wireguard_interface}.conf"
[Interface]
Address = ${ip_address}/24
ListenPort = ${listen_port}
PrivateKey = ${private_key}
PostUp = iptables -A FORWARD -d "${vpn_network_prefix}" -i "${network_interface}" -o "${wireguard_interface}" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT; iptables -A FORWARD -s "${vpn_network_prefix}" -i "${wireguard_interface}" -o "${network_interface}" -j ACCEPT; iptables -t nat -I POSTROUTING -s "${vpn_network_prefix}" -o "${network_interface}" -j MASQUERADE
PostDown = iptables -A FORWARD -d "${vpn_network_prefix}" -i "${network_interface}" -o "${wireguard_interface}" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT; iptables -A FORWARD -s "${vpn_network_prefix}" -i "${wireguard_interface}" -o "${network_interface}" -j ACCEPT; iptables -t nat -I POSTROUTING -s "${vpn_network_prefix}" -o "${network_interface}" -j MASQUERADE
EOF

}

function add_wireguard_peer() {
    # Parameters
    local interface=${1}
    local user_name=${2}
    local client_key_name=${3}
    local ip_address=${4}

    local public_key
    public_key=$(cat "/home/${user_name}/.wireguard_keys/${client_key_name}.pub")

    cat <<EOF >>"/etc/wireguard/${interface}.conf"
# ${client_key_name}
[Peer]
PublicKey = ${public_key}
AllowedIPs = ${ip_address}/32

EOF
}

function wireguard_create_client_config() {
    # Parameters
    local user_name=${1}
    local client_key_name=${2}
    local server_key_name=${3}
    local ip_address=${4}
    local dns_server=${5}
    local public_dns_ip_address=${6}
    local listen_port=${7}

    local private_key
    private_key=$(cat "/home/${user_name}/.wireguard_keys/${client_key_name}")
    local public_key
    public_key=$(cat "/home/${user_name}/.wireguard_keys/${server_key_name}.pub")

    mkdir -p "/home/${user_name}/.wireguard_client_configs"
    cat <<EOF >>"/home/${user_name}/.wireguard_client_configs/${client_key_name}.conf"
[Interface]
Address = ${ip_address}
PrivateKey = ${private_key}
DNS = ${dns_server}

[Peer]
PublicKey = ${public_key}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = ${public_dns_ip_address}:${listen_port}
EOF
}

function enable_wireguard_service() {
    # Parameters
    local interface=${1}

    systemctl start "wg-quick@${interface}.service"
    systemctl enable "wg-quick@${interface}.service"
}

#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.

# Compilation of functions for the VPN Server.

function lock_root() {
    passwd --lock root
}

function get_username() {
    user_name=$(logname)
}

function get_interface_name() {
    interface="$(ip route get 8.8.8.8 | sed -nr 's/.*dev ([^\ ]+).*/\1/p')"
    echo "Interface name is ${interface}"
}

function configure_network() {
    # Parameters
    local ip_address=${1}
    local network_address=${2}
    local subnet_mask=${3}
    local gateway_address=${4}
    local dns_address=${5}
    local interface=${6}

    # Configure network
    rm -f '/etc/network/interfaces'
    cat <<EOF >'/etc/network/interfaces'
auto lo
iface lo inet loopback

iface ${interface} inet static
    address ${ip_address}
    network ${network_address}
    netmask ${subnet_mask}
    gateway ${gateway_address}
    dns-nameservers ${dns_address}

EOF

    # Restart network interface
    ifdown "${interface}" && ifup "${interface}"
}

function fix_apt_packages() {
    dpkg --configure -a
}

function install_vpn_server_packages() {
    apt-get update
    apt-get upgrade
    apt-get install -y wget vim git ufw ntp ssh apt-transport-https openssh-server unattended-upgrades wireguard
}

function configure_ssh() {
    # Turn off password authentication
    grep -q ".*PasswordAuthentication" '/etc/ssh/sshd_config' && sed -i "s,.*PasswordAuthentication.*,PasswordAuthentication no," '/etc/ssh/sshd_config' || printf '%s\n' 'PasswordAuthentication no' >>'/etc/ssh/sshd_config'

    # Do not allow empty passwords
    grep -q ".*PermitEmptyPasswords" '/etc/ssh/sshd_config' && sed -i "s,.*PermitEmptyPasswords.*,PermitEmptyPasswords no," '/etc/ssh/sshd_config' || printf '%s\n' 'PermitEmptyPasswords no' >>'/etc/ssh/sshd_config'

    # Turn off PAM
    grep -q ".*UsePAM" '/etc/ssh/sshd_config' && sed -i "s,.*UsePAM.*,UsePAM no," '/etc/ssh/sshd_config' || printf '%s\n' 'UsePAM no' >>'/etc/ssh/sshd_config'

    # Turn off root ssh access
    grep -q ".*PermitRootLogin" '/etc/ssh/sshd_config' && sed -i "s,.*PermitRootLogin.*,PermitRootLogin no," '/etc/ssh/sshd_config' || printf '%s\n' 'PermitRootLogin no' >>'/etc/ssh/sshd_config'

    # Enable public key authentication
    grep -q ".*AuthorizedKeysFile" '/etc/ssh/sshd_config' && sed -i "s,.*AuthorizedKeysFile\s*.ssh/authorized_keys\s*.ssh/authorized_keys2,AuthorizedKeysFile .ssh/authorized_keys," '/etc/ssh/sshd_config' || printf '%s\n' 'AuthorizedKeysFile .ssh/authorized_keys' >>'/etc/ssh/sshd_config'
    grep -q ".*PubkeyAuthentication" '/etc/ssh/sshd_config' && sed -i "s,.*PubkeyAuthentication.*,PubkeyAuthentication yes," '/etc/ssh/sshd_config' || printf '%s\n' 'PubkeyAuthentication yes' >>'/etc/ssh/sshd_config'
}

function generate_ssh_key() {
    # Parameters
    local user_name=${1}
    local ecdsa_response=${2}
    local rsa_response=${3}
    local dropbear_response=${4}
    local key_name=${5}

    # Generate ecdsa key
    if [[ "${ecdsa_response}" =~ ^([yY][eE][sS]|[yY])+$ ]]; then
        # Generate an ecdsa 521 bit key
        ssh-keygen -f "/home/$user_name/${key_name}" -t ecdsa -b 521
    fi

    # Generate rsa key
    if [[ "${rsa_response}" =~ ^([yY][eE][sS]|[yY])+$ ]]; then
        # Generate an rsa 4096 bit key
        ssh-keygen -f "/home/$user_name/${key_name}" -t rsa -b 4096
    fi

    # Authorize the key for use with ssh
    mkdir "/home/$user_name/.ssh"
    chmod 700 "/home/$user_name/.ssh"
    touch "/home/$user_name/.ssh/authorized_keys"
    chmod 600 "/home/$user_name/.ssh/authorized_keys"
    cat "/home/$user_name/${key_name}.pub" >>"/home/$user_name/.ssh/authorized_keys"
    printf '%s\n' '' >>"/home/$user_name/.ssh/authorized_keys"
    chown -R "$user_name" "/home/$user_name"
    python -m SimpleHTTPServer 40080 &
    server_pid=$!
    read -r -p "Copy the key from the webserver on port 40080 before continuing: " >>'/dev/null'
    kill "${server_pid}"

    # Dropbear setup
    if [[ "${dropbear_response}" =~ ^([yY][eE][sS]|[yY])+$ ]]; then
        cat "/home/$user_name/${key_name}.pub" >>'/etc/dropbear/authorized_keys'
        printf '%s\n' '' >>'/etc/dropbear/authorized_keys'
        chmod 0700 /etc/dropbear
        chmod 0600 /etc/dropbear/authorized_keys
    fi
}

function configure_ufw_base() {
    # Set default inbound to deny
    ufw default deny incoming

    # Set default outbound to allow
    ufw default allow outgoing
}

function ufw_configure_rules() {
    # Parameters
    local network_prefix=${1}
    local limit_ssh=${2}
    local limit_port_64640=${3}

    if [[ "${limit_ssh}" =~ ^([yY][eE][sS]|[yY])+$ ]]; then
        ufw limit proto tcp from "${network_prefix}" to any port 22
        ufw limit proto tcp from fe80::/10 to any port 22
    fi

    if [[ "${limit_port_64640}" =~ ^([yY][eE][sS]|[yY])+$ ]]; then
        ufw limit proto udp from any to any port 64640
    fi

}

function ufw_allow_default_forward() {
    grep -q ".*DEFAULT_FORWARD_POLICY=" '/etc/default/ufw' && sed -i "s,.*DEFAULT_FORWARD_POLICY=.*,DEFAULT_FORWARD_POLICY=\"ACCEPT\"," '/etc/default/ufw' || printf '%s\n' 'DEFAULT_FORWARD_POLICY="ACCEPT"' >>'/etc/default/ufw'
}

function ufw_allow_ip_forwarding() {
    grep -q ".*net/ipv4/ip_forward=" '/etc/ufw/sysctl.conf' && sed -i "s,.*net/ipv4/ip_forward=.*,net/ipv4/ip_forward=1," '/etc/ufw/sysctl.conf' || printf '%s\n' 'net/ipv4/ip_forward=1' >>'/etc/ufw/sysctl.conf'
    grep -q ".*net/ipv6/conf/default/forwarding=" '/etc/ufw/sysctl.conf' && sed -i "s,.*net/ipv6/conf/default/forwarding=.*,net/ipv6/conf/default/forwarding=1," '/etc/ufw/sysctl.conf' || printf '%s\n' 'net/ipv6/conf/default/forwarding=1' >>'/etc/ufw/sysctl.conf'
    grep -q ".*net/ipv6/conf/all/forwarding=" '/etc/ufw/sysctl.conf' && sed -i "s,.*net/ipv6/conf/all/forwarding=.*,net/ipv6/conf/all/forwarding=1," '/etc/ufw/sysctl.conf' || printf '%s\n' 'net/ipv6/conf/all/forwarding=1' >>'/etc/ufw/sysctl.conf'
}

function configure_vpn_scripts() {
    # Enter code for dynamic dns
    read -r -p "Enter code for dynamic dns: " dynamic_dns
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
#@reboot apt-get update && apt-get install -y openvpn &
* 0 * * 1 bash /usr/local/bin/backup_configs.sh &
#@reboot nohup bash /usr/local/bin/email_on_vpn_connections.sh &
3,8,13,18,23,28,33,38,43,48,53,58 * * * * sleep 29 ; wget --no-check-certificate -O - https://freedns.afraid.org/dynamic/update.php?${dynamic_dns} >> /tmp/freedns_mattm_mooo_com.log 2>&1 &
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
    local interface=${1}
    local user_name=${2}
    local server_key_name=${3}
    local ip_address=${4}
    local listen_port=${5}

    local private_key
    private_key=$(cat "/home/${user_name}/.wireguard_keys/${server_key_name}")

    cat <<EOF >"/etc/wireguard/${interface}.conf"
[Interface]
Address = ${ip_address}/24
ListenPort = ${listen_port}
PrivateKey = ${private_key}

EOF

}

function add_wireguard_peer() {
    # Parameters
    local interface=${1}
    local user_name=${2}
    local server_key_name=${3}
    local ip_address=${4}
    local preshared_key=${5}

    local public_key
    public_key=$(cat "/home/${user_name}/.wireguard_keys/${server_key_name}.pub")

    cat <<EOF >>"/etc/wireguard/${interface}.conf"
# ${server_key_name}
[Peer]
PublicKey = ${public_key}
PresharedKey = ${preshared_key}
AllowedIPs = ${ip_address}/32

EOF
}

function wireguard_create_client_config() {
    # Parameters
    local interface=${1}
    local user_name=${2}
    local client_key_name=${3}
    local server_key_name=${4}
    local ip_address=${5}
    local preshared_key=${6}
    local dns_server=${7}
    local public_dns_ip_address=${8}
    local listen_port=${9}

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
PresharedKey = ${preshared_key}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = ${public_dns_ip_address}:${listen_port}
EOF
}

function apt_configure_auto_updates() {
    # Parameters
    local release_name=${1}

    rm -f '/etc/apt/apt.conf.d/50unattended-upgrades'

    cat <<EOF >'/etc/apt/apt.conf.d/50unattended-upgrades'
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,n=${release_name},l=Debian";
        "origin=Debian,n=${release_name},l=Debian-Security";
        "origin=Debian,n=${release_name}-updates";
};

Unattended-Upgrade::Package-Blacklist {

};

Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";

EOF
}

function enable_ufw() {
    systemctl enable ufw.service
    ufw enable
}

function enable_wireguard_service() {
    # Parameters
    local interface=${1}

    systemctl start "wg-quick@${interface}.service"
    systemctl enable "wg-quick@${interface}.service"
}

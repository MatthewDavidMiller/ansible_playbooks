#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.

# Compilation of functions for the Omada Controller.

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

function install_omada_controller_packages() {
    apt-get update
    apt-get upgrade -y
    apt-get install -y wget vim git iptables iptables-persistent ntp ssh openssh-server jsvc curl unattended-upgrades
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

function configure_omada_controller() {
    # Download the controller software
    wget 'https://static.tp-link.com/2019/201911/20191108/omada_v3.2.4_linux_x64_20190925173425.deb'

    # Install the software
    dpkg -i 'omada_v3.2.4_linux_x64_20190925173425.deb'
}

function iptables_setup_base() {
    # Parameters
    interface=${1}
    network_prefix=${2}

    # Allow established connections
    iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6

}

function iptables_set_defaults() {
    # Drop inbound by default
    iptables -P INPUT DROP
    ip6tables -P INPUT DROP

    # Allow outbound by default
    iptables -P OUTPUT ACCEPT
    ip6tables -P OUTPUT ACCEPT

    # Drop forwarding by default
    iptables -P FORWARD DROP
    ip6tables -P FORWARD DROP
    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6

}

function iptables_allow_ssh() {
    # Parameters
    source=${1}
    destination=${2}

    # Allow ssh from a source and destination
    iptables -A INPUT -p tcp --dport 22 -s "${source}" -d "${destination}" -j ACCEPT

    # Log new connection ips and add them to a list called SSH
    iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --set --name SSH

    # Log ssh connections from an ip to 6 connections in 60 seconds.
    iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 6 --rttl --name SSH -j LOG --log-level info --log-prefix "Limit SSH"

    # Limit ssh connections from an ip to 6 connections in 60 seconds.
    iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 6 --rttl --name SSH -j DROP

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6

}

function iptables_allow_omada_controller() {
    # Parameters
    source=${1}
    destination=${2}

    # Allow omada controller from a source and destination
    iptables -A INPUT -p tcp --dport 8043 -s "${source}" -d "${destination}" -j ACCEPT
    iptables -A INPUT -p tcp --dport 8088 -s "${source}" -d "${destination}" -j ACCEPT
    iptables -A INPUT -p udp --dport 29810 -s "${source}" -d "${destination}" -j ACCEPT
    iptables -A INPUT -p tcp --dport 29811 -s "${source}" -d "${destination}" -j ACCEPT
    iptables -A INPUT -p tcp --dport 29812 -s "${source}" -d "${destination}" -j ACCEPT
    iptables -A INPUT -p tcp --dport 29813 -s "${source}" -d "${destination}" -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6

}

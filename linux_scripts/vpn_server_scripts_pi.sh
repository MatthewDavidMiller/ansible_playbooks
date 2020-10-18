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
    local ipv6_link_local_address=${7}

    # Configure network
    grep -q -E ".*auto ${interface}" '/etc/network/interfaces' && sed -i -E "s,.*auto ${interface}.*,auto ${interface}," '/etc/network/interfaces' || printf '%s\n' "auto ${interface}" >>'/etc/network/interfaces'
    grep -q -E ".*iface ${interface} inet " '/etc/network/interfaces' && sed -i -E "s,.*iface ${interface} inet .*\naddress\nnetwork\nnetmask\ngateway\ndns-nameservers,iface ${interface} inet static\naddress ${ip_address}\nnetwork ${network_address}\nnetmask ${subnet_mask}\ngateway ${gateway_address}\ndns-nameservers ${dns_address}," '/etc/network/interfaces' || cat <<EOF >>'/etc/network/interfaces'
iface ${interface} inet static
    address ${ip_address}
    network ${network_address}
    netmask ${subnet_mask}
    gateway ${gateway_address}
    dns-nameservers ${dns_address}
EOF

    grep -q -E ".*iface ${interface} inet6" '/etc/network/interfaces' && sed -i -E "s,.*iface ${interface} inet6.*\naddress\nnetmask 64\nscope link,iface ${interface} inet6 static\naddress ${ipv6_link_local_address}\nnetmask 64\nscope link," '/etc/network/interfaces' || cat <<EOF >>'/etc/network/interfaces'
iface ${interface} inet6 static
    address ${ipv6_link_local_address}
    netmask 64
    scope link
EOF

    # Restart network interface
    ifdown "${interface}" && ifup "${interface}"
}

function fix_apt_packages() {
    dpkg --configure -a
}

function install_vpn_server_packages() {
    # Parameters
    local release_name=${1}

    local linux_headers
    linux_headers="linux-headers-$(uname -r)"

    apt-get update
    apt-get upgrade
    apt-get install -y wget vim git iptables iptables-persistent ntp ssh apt-transport-https openssh-server unattended-upgrades qrencode sudo ${linux_headers}
    apt-get -t "${release_name}-backports" install -y wireguard
}

function configure_ssh() {
    # Turn off password authentication
    grep -q -E ".*PasswordAuthentication" '/etc/ssh/sshd_config' && sed -i -E "s,.*PasswordAuthentication.*,PasswordAuthentication no," '/etc/ssh/sshd_config' || printf '%s\n' 'PasswordAuthentication no' >>'/etc/ssh/sshd_config'

    # Do not allow empty passwords
    grep -q -E ".*PermitEmptyPasswords" '/etc/ssh/sshd_config' && sed -i -E "s,.*PermitEmptyPasswords.*,PermitEmptyPasswords no," '/etc/ssh/sshd_config' || printf '%s\n' 'PermitEmptyPasswords no' >>'/etc/ssh/sshd_config'

    # Turn off PAM
    grep -q -E ".*UsePAM" '/etc/ssh/sshd_config' && sed -i -E "s,.*UsePAM.*,UsePAM no," '/etc/ssh/sshd_config' || printf '%s\n' 'UsePAM no' >>'/etc/ssh/sshd_config'

    # Turn off root ssh access
    grep -q -E ".*PermitRootLogin" '/etc/ssh/sshd_config' && sed -i -E "s,.*PermitRootLogin.*,PermitRootLogin no," '/etc/ssh/sshd_config' || printf '%s\n' 'PermitRootLogin no' >>'/etc/ssh/sshd_config'

    # Enable public key authentication
    grep -q -E ".*AuthorizedKeysFile" '/etc/ssh/sshd_config' && sed -i -E "s,.*AuthorizedKeysFile\s*.ssh\/authorized_keys\s*.ssh\/authorized_keys2,AuthorizedKeysFile .ssh\/authorized_keys," '/etc/ssh/sshd_config' || printf '%s\n' 'AuthorizedKeysFile .ssh/authorized_keys' >>'/etc/ssh/sshd_config'
    grep -q -E ".*PubkeyAuthentication" '/etc/ssh/sshd_config' && sed -i -E "s,.*PubkeyAuthentication.*,PubkeyAuthentication yes," '/etc/ssh/sshd_config' || printf '%s\n' 'PubkeyAuthentication yes' >>'/etc/ssh/sshd_config'
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

function configure_vpn_scripts() {
    # Parameters
    dynamic_dns=${1}
    release_name=${2}

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

function apt_configure_auto_updates() {
    # Parameters
    local release_name=${1}

    grep -q -E ".*Unattended-Upgrade::Origins-Pattern {" '/etc/apt/apt.conf.d/50unattended-upgrades' && sed -i -E "s,.*Unattended-Upgrade::Origins-Pattern {.*\n.*\n.*\n.*\n.*,Unattended-Upgrade::Origins-Pattern {\n\"origin=Debian\,n=${release_name}\,l=Debian\";\n\"origin=Debian\,n=${release_name}\,l=Debian-Security\";\n\"origin=Debian\,n=${release_name}-updates\";\n};," '/etc/apt/apt.conf.d/50unattended-upgrades' || cat <<EOF >>"/etc/apt/apt.conf.d/50unattended-upgrades"
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,n=${release_name},l=Debian";
        "origin=Debian,n=${release_name},l=Debian-Security";
        "origin=Debian,n=${release_name}-updates";
};
EOF

    grep -q -E ".*Unattended-Upgrade::Automatic-Reboot" '/etc/apt/apt.conf.d/50unattended-upgrades' && sed -i -E "s,.*Unattended-Upgrade::Automatic-Reboot.*,Unattended-Upgrade::Automatic-Reboot \"true\";," '/etc/apt/apt.conf.d/50unattended-upgrades' || printf '%s\n' 'Unattended-Upgrade::Automatic-Reboot "true";' >>'/etc/apt/apt.conf.d/50unattended-upgrades'
    grep -q -E ".*Unattended-Upgrade::Automatic-Reboot-Time" '/etc/apt/apt.conf.d/50unattended-upgrades' && sed -i -E "s,.*Unattended-Upgrade::Automatic-Reboot-Time.*,Unattended-Upgrade::Automatic-Reboot-Time \"04:00\";," '/etc/apt/apt.conf.d/50unattended-upgrades' || printf '%s\n' 'Unattended-Upgrade::Automatic-Reboot-Time "04:00";' >>'/etc/apt/apt.conf.d/50unattended-upgrades'
}

function enable_wireguard_service() {
    # Parameters
    local interface=${1}

    systemctl start "wg-quick@${interface}.service"
    systemctl enable "wg-quick@${interface}.service"
}

function add_backports_repository() {
    # Parameters
    local release_name=${1}

    cat <<EOF >>'/etc/apt/sources.list'
deb https://mirrors.wikimedia.org/debian/ ${release_name}-backports main
deb-src https://mirrors.wikimedia.org/debian/ ${release_name}-backports main
EOF
}

function iptables_setup_base() {
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
    local source=${1}
    local interface=${2}
    local ipv6_link_local='fe80::/10'

    # Allow ssh from a source and interface
    iptables -A INPUT -p tcp --dport 22 -s "${source}" -i "${interface}" -j ACCEPT
    ip6tables -A INPUT -p tcp --dport 22 -s "${ipv6_link_local}" -i "${interface}" -j ACCEPT

    # Log new connection ips and add them to a list called SSH
    iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --set --name SSH
    ip6tables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --set --name SSH

    # Log ssh connections from an ip to 6 connections in 60 seconds.
    iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 6 --rttl --name SSH -j LOG --log-level info --log-prefix "Limit SSH"
    ip6tables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 6 --rttl --name SSH -j LOG --log-level info --log-prefix "Limit SSH"

    # Limit ssh connections from an ip to 6 connections in 60 seconds.
    iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 6 --rttl --name SSH -j DROP
    ip6tables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 6 --rttl --name SSH -j DROP

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6
}

function iptables_allow_vpn_port() {
    # Parameters
    local interface=${1}
    local vpn_port=${2}

    # Allow vpn port to a destination
    iptables -A INPUT -p udp --dport ${vpn_port} -i "${interface}" -j ACCEPT
    # ip6tables -A INPUT -p udp --dport ${vpn_port} -i "${interface}" -j ACCEPT

    # Log new connection ips and add them to a list called Wireguard
    iptables -A INPUT -p udp --dport ${vpn_port} -m state --state NEW -m recent --set --name Wireguard
    # ip6tables -A INPUT -p udp --dport ${vpn_port} -m state --state NEW -m recent --set --name Wireguard

    # Log vpn connections from an ip to 3 connections in 60 seconds.
    iptables -A INPUT -p udp --dport ${vpn_port} -m state --state NEW -m recent --update --seconds 60 --hitcount 3 --rttl --name Wireguard -j LOG --log-level info --log-prefix "Limit Wireguard"
    # ip6tables -A INPUT -p udp --dport ${vpn_port} -m state --state NEW -m recent --update --seconds 60 --hitcount 3 --rttl --name Wireguard -j LOG --log-level info --log-prefix "Limit Wireguard"

    # Limit vpn connections from an ip to 3 connections in 60 seconds.
    iptables -A INPUT -p udp --dport ${vpn_port} -m state --state NEW -m recent --update --seconds 60 --hitcount 3 --rttl --name Wireguard -j DROP
    # ip6tables -A INPUT -p udp --dport ${vpn_port} -m state --state NEW -m recent --update --seconds 60 --hitcount 3 --rttl --name Wireguard -j DROP

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6

}

function iptables_allow_forwarding() {
    grep -q -E ".*net\.ipv4\.ip_forward=" '/etc/sysctl.conf' && sed -i -E "s,.*net\.ipv4\.ip_forward=.*,net.ipv4.ip_forward=1," '/etc/sysctl.conf' || printf '%s\n' 'net.ipv4.ip_forward=1' >>'/etc/sysctl.conf'
    grep -q -E ".*net\.ipv6\.conf\.all\.forwarding=" '/etc/sysctl.conf' && sed -i -E "s,.*net\.ipv6\.conf\.all\.forwarding=.*,net.ipv6.conf.all.forwarding=1," '/etc/sysctl.conf' || printf '%s\n' 'net.ipv6.conf.all.forwarding=1' >>'/etc/sysctl.conf'
}

function iptables_allow_icmp() {
    # Parameters
    local source=${1}
    local interface=${2}
    local ipv6_link_local='fe80::/10'

    # Allow icmp from a source and interface
    iptables -A INPUT -p icmp -s "${source}" -i "${interface}" -j ACCEPT
    ip6tables -A INPUT -p icmpv6 -s "${ipv6_link_local}" -i "${interface}" -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6
}

function iptables_allow_loopback() {
    iptables -A INPUT -s '127.0.0.0/8' -i 'lo' -j ACCEPT
    ip6tables -A INPUT -s '::1' -i 'lo' -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6
}

function log_rotate_configure() {
    # Parameters
    user_name=${1}

    apt-get install -y logrotate
    touch -a '/etc/logrotate.conf'
    mkdir -p "/home/$user_name/config_backups"
    cp '/etc/logrotate.conf' "/home/$user_name/config_backups/logrotate.conf.backup"
    grep -q -E "(^\s*[#]*\s*daily\s*$)|(^\s*[#]*\s*weekly\s*$)|(^\s*[#]*\s*monthly\s*$)" '/etc/logrotate.conf' && sed -i -E "s,(^\s*[#]*\s*daily\s*$)|(^\s*[#]*\s*weekly\s*$)|(^\s*[#]*\s*monthly\s*$),daily," '/etc/logrotate.conf' || printf '%s\n' 'daily' >>'/etc/logrotate.conf'
    grep -q -E "^\s*[#]*\s*minsize.*$" '/etc/logrotate.conf' && sed -i -E "s,^\s*[#]*\s*minsize.*$,minsize 100M," '/etc/logrotate.conf' || printf '%s\n' 'minsize 100M' >>'/etc/logrotate.conf'
    grep -q -E "^\s*[#]*\s*rotate\s*[0-9]*$" '/etc/logrotate.conf' && sed -i -E "s,^\s*[#]*\s*rotate\s*[0-9]*$,rotate 4," '/etc/logrotate.conf' || printf '%s\n' 'rotate 4' >>'/etc/logrotate.conf'
    grep -q -E "^\s*[#]*\s*compress\s*$" '/etc/logrotate.conf' && sed -i -E "s,^\s*[#]*\s*compress\s*$,compress," '/etc/logrotate.conf' || printf '%s\n' 'compress' >>'/etc/logrotate.conf'
    grep -q -E "^\s*[#]*\s*create\s*$" '/etc/logrotate.conf' && sed -i -E "s,^\s*[#]*\s*create\s*$,create," '/etc/logrotate.conf' || printf '%s\n' 'create' >>'/etc/logrotate.conf'
}

function create_swap_file() {
    # Parameters
    local swap_file_size=${1}

    # Create swapfile
    dd if=/dev/zero of=/swapfile bs=1M count="${swap_file_size}" status=progress
    # Set file permissions
    # chmod 600
    chmod u=rw,g-rwx,o-rwx '/swapfile'
    # Format file to swap
    mkswap /swapfile
    # Activate the swap file
    swapon /swapfile
    # Add to fstab
    grep -q -E ".*\/swapfile" '/etc/fstab' && sed -i -E "s,.*\/swapfile.*,\/swapfile none swap defaults 0 0," '/etc/fstab' || printf '%s\n' "/swapfile none swap defaults 0 0" >>'/etc/fstab'
}

function set_shell_bash() {
    # Parameters
    local user_name=${1}

    chsh -s /bin/bash
    chsh -s /bin/bash "${user_name}"
}

function add_user_to_sudo() {
    # Parameters
    local user_name=${1}

    grep -q -E ".*${user_name}" '/etc/sudoers' && sed -i -E "s,.*${user_name}.*,${user_name} ALL=\(ALL\) ALL," '/etc/sudoers' || printf '%s\n' "${user_name} ALL=(ALL) ALL" >>'/etc/sudoers'
}

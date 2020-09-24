#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.

# Compilation of functions for the Pihole Server.

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

function install_dns_server_packages() {
    apt-get update
    apt-get upgrade -y
    apt-get install -y wget vim git iptables iptables-persistent ntp ssh openssh-server unbound unattended-upgrades sqlite3
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

function configure_dns_server_scripts() {
    # Script to archive config files for backup
    wget 'https://raw.githubusercontent.com/MatthewDavidMiller/scripts/stable/linux_scripts/backup_configs.sh'
    mv 'backup_configs.sh' '/usr/local/bin/backup_configs.sh'
    chmod +x '/usr/local/bin/backup_configs.sh'

    # Script to update root.hints file
    cat <<EOF >'/usr/local/bin/update_root_hints.sh'
#!/bin/bash
wget -O "/home/$user_name/root.hints" 'https://www.internic.net/domain/named.root'
mv -f "/home/$user_name/root.hints" '/var/lib/unbound/'

EOF
    chmod +x '/usr/local/bin/update_root_hints.sh'

    # Configure cron jobs
    cat <<EOF >jobs.cron
* 0 * * 1 bash /usr/local/bin/backup_configs.sh &
* 0 * * 1 bash /usr/local/bin/update_root_hints.sh &

EOF
    crontab jobs.cron
    rm -f jobs.cron
}

function configure_unbound() {
    wget -O root.hints 'https://www.internic.net/domain/named.root'
    mv root.hints /var/lib/unbound/
    systemctl enable unbound
    systemctl start unbound
    rm -f '/etc/unbound/unbound.conf.d/pi-hole.conf'
    cat <<\EOF >'/etc/unbound/unbound.conf.d/pi-hole.conf'
server:
    # If no logfile is specified, syslog is used
    # logfile: "/var/log/unbound/unbound.log"
    verbosity: 0

    port: 5353
    do-ip4: yes
    do-udp: yes
    do-tcp: yes

    # May be set to yes if you have IPv6 connectivity
    do-ip6: yes

    # Use this only when you downloaded the list of primary root servers!
    root-hints: "/var/lib/unbound/root.hints"

    # Trust glue only if it is within the servers authority
    harden-glue: yes

    # Require DNSSEC data for trust-anchored zones, if such data is absent, the zone becomes BOGUS
    harden-dnssec-stripped: yes

    # Don't use Capitalization randomization as it known to cause DNSSEC issues sometimes
    # see https://discourse.pi-hole.net/t/unbound-stubby-or-dnscrypt-proxy/9378 for further details
    use-caps-for-id: no

    # Reduce EDNS reassembly buffer size.
    # Suggested by the unbound man page to reduce fragmentation reassembly problems
    edns-buffer-size: 1472

    # Perform prefetching of close to expired message cache entries
    # This only applies to domains that have been frequently queried
    prefetch: yes

    # One thread should be sufficient, can be increased on beefy machines. In reality for most users running on small networks or on a single machine it should be unnecessary to seek performance enhancement by increasing num-threads above 1.
    num-threads: 1

    # Ensure kernel buffer is large enough to not lose messages in traffic spikes
    so-rcvbuf: 1m

    # Ensure privacy of local IP ranges
    private-address: 192.168.0.0/16
    private-address: 169.254.0.0/16
    private-address: 172.16.0.0/12
    private-address: 10.0.0.0/8
    private-address: fd00::/8
    private-address: fe80::/10

EOF
}

function configure_pihole() {
    git clone --depth 1 https://github.com/pi-hole/pi-hole.git Pi-hole
    cd 'Pi-hole/automated install/' || exit
    bash basic-install.sh
    cd || exit

    # Configure allowlist, denylist, and regex
    # Possible values: id, type, domain, enabled, date_added, date_modified, comment
    sqlite3 /etc/pihole/gravity.db <<EOF
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (1,3,'^.+\.(ru|cn|ro|ml|ga|gq|cf|tk|pw|ua|ug|ve|)$',1,'Block some country TLDs.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (2,3,'porn',1,'Block domains with the word porn in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (3,3,'sex',1,'Block domains with the word sex in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (4,0,'ntscorp.ru',1,'Openiv mod download domain.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (5,3,'date',1,'Block domains with the word date in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (6,3,'love',1,'Block domains with the word love in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (7,2,'update',1,'Allow domains with the word update in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (8,3,'hentai',1,'Block domains with the word hentai in them.');
EOF

    # Configure blocklists
    # Possible values: id, address, enabled, date_added, date_modified, comment
    sqlite3 /etc/pihole/gravity.db <<EOF
INSERT INTO adlist (id, address, enabled, comment) VALUES (1,'https://mirror1.malwaredomains.com/files/justdomains',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (2,'https://raw.githubusercontent.com/chadmayfield/my-pihole-blocklists/master/lists/pi_blocklist_porn_all.list',1,'A porn blocklist.');
INSERT INTO adlist (id, address, enabled, comment) VALUES (3,'https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts',0,'Default All in one blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (4,'https://s3.amazonaws.com/lists.disconnect.me/simple_tracking.txt',0,'Default Tracker blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (5,'https://s3.amazonaws.com/lists.disconnect.me/simple_ad.txt',0,'Default Ad blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (6,'https://raw.githubusercontent.com/DandelionSprout/adfilt/master/Alternate%20versions%20Anti-Malware%20List/AntiMalwareHosts.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (7,'https://osint.digitalside.it/Threat-Intel/lists/latestdomains.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (8,'https://s3.amazonaws.com/lists.disconnect.me/simple_malvertising.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (9,'https://v.firebog.net/hosts/Prigent-Crypto.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (10,'https://mirror.cedia.org.ec/malwaredomains/immortal_domains.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (11,'https://www.malwaredomainlist.com/hostslist/hosts.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (12,'https://bitbucket.org/ethanr/dns-blacklists/raw/8575c9f96e5b4a1308f2f12394abd86d0927a4a0/bad_lists/Mandiant_APT1_Report_Appendix_D.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (13,'https://phishing.army/download/phishing_army_blocklist_extended.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (14,'https://gitlab.com/quidsup/notrack-blocklists/raw/master/notrack-malware.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (15,'https://v.firebog.net/hosts/Shalla-mal.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (16,'https://raw.githubusercontent.com/Spam404/lists/master/main-blacklist.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (17,'https://raw.githubusercontent.com/FadeMind/hosts.extras/master/add.Risk/hosts',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (18,'https://urlhaus.abuse.ch/downloads/hostfile/',0,'malware blocklist');

EOF

    # Configure pihole settings
    grep -q -E 'DNSSEC=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNSSEC=.*/DNSSEC=true/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNSSEC=true' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'PIHOLE_DNS_1=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*PIHOLE_DNS_1=.*/PIHOLE_DNS_1=127.0.0.1#5353/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'PIHOLE_DNS_1=127.0.0.1#5053' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'PIHOLE_DNS_2=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*PIHOLE_DNS_2=.*/PIHOLE_DNS_2=::1#5353/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'PIHOLE_DNS_2=::1#5053' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'DNSMASQ_LISTENING=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNSMASQ_LISTENING=.*/DNSMASQ_LISTENING=all/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNSMASQ_LISTENING=all' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'CONDITIONAL_FORWARDING=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*CONDITIONAL_FORWARDING=.*/CONDITIONAL_FORWARDING=true/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'CONDITIONAL_FORWARDING=true' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'CONDITIONAL_FORWARDING_IP=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*CONDITIONAL_FORWARDING_IP=.*/CONDITIONAL_FORWARDING_IP=${gateway_address}/g" '/etc/pihole/setupVars.conf' || printf '%s\n' "CONDITIONAL_FORWARDING_IP=${gateway_address}" >>'/etc/pihole/setupVars.conf'
    grep -q -E 'CONDITIONAL_FORWARDING_DOMAIN=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*CONDITIONAL_FORWARDING_DOMAIN=.*/CONDITIONAL_FORWARDING_DOMAIN=lan/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'CONDITIONAL_FORWARDING_DOMAIN=lan' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'DNS_FQDN_REQUIRED=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNS_FQDN_REQUIRED=.*/DNS_FQDN_REQUIRED=false/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNS_FQDN_REQUIRED=false' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'DNS_BOGUS_PRIV=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNS_BOGUS_PRIV=.*/DNS_BOGUS_PRIV=false/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNS_BOGUS_PRIV=false' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'WEBTHEME=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*WEBTHEME=.*/WEBTHEME=default-dark/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'WEBTHEME=default-dark' >>'/etc/pihole/setupVars.conf'

    # Set custom domains
    cat <<EOF >'/etc/pihole/custom.list'
10.1.10.1 MattOpenwrt.miller.lan
10.1.10.3 matt-prox.miller.lan
10.1.10.4 matt-nas.miller.lan
10.1.10.5 matt-pihole.miller.lan
10.1.10.6 matt-vpn.miller.lan
10.1.1.213 MaryPrinter.miller.lan
EOF

    echo 'Set pihole password'
    pihole -a -p

    # Setup pihole folder permissions
    chown -R pihole:pihole '/etc/pihole'
    chmod 777 -R '/etc/pihole'
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

function iptables_allow_dns() {
    # Parameters
    local source=${1}
    local interface=${2}
    local ipv6_link_local='fe80::/10'

    # Allow dns from a source and interface
    iptables -A INPUT -p tcp --dport 53 -s "${source}" -i "${interface}" -j ACCEPT
    iptables -A INPUT -p udp --dport 53 -s "${source}" -i "${interface}" -j ACCEPT
    ip6tables -A INPUT -p tcp --dport 53 -s "${ipv6_link_local}" -i "${interface}" -j ACCEPT
    ip6tables -A INPUT -p udp --dport 53 -s "${ipv6_link_local}" -i "${interface}" -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6
}

function iptables_allow_http() {
    # Parameters
    local source=${1}
    local interface=${2}
    local ipv6_link_local='fe80::/10'

    # Allow http from a source and interface
    iptables -A INPUT -p tcp --dport 80 -s "${source}" -i "${interface}" -j ACCEPT
    ip6tables -A INPUT -p tcp --dport 80 -s "${ipv6_link_local}" -i "${interface}" -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6
}

function iptables_allow_https() {
    # Parameters
    local source=${1}
    local interface=${2}
    local ipv6_link_local='fe80::/10'

    # Allow https from a source and interface
    iptables -A INPUT -p tcp --dport 443 -s "${source}" -i "${interface}" -j ACCEPT
    ip6tables -A INPUT -p tcp --dport 443 -s "${ipv6_link_local}" -i "${interface}" -j ACCEPT

    # Save rules
    iptables-save >/etc/iptables/rules.v4
    ip6tables-save >/etc/iptables/rules.v6
}

function get_ipv6_link_local_address() {
    ipv6_link_local_address="$(ip address | grep '.*inet6 fe80' | sed -nr 's/.*inet6 ([^\ ]+)\/64.*/\1/p')"
    echo "ipv6 link local address is ${ipv6_link_local_address}"
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

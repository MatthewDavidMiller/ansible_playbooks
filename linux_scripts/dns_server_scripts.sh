#!/bin/bash

# Copyright (c) Matthew David Miller. All rights reserved.
# Licensed under the MIT License.

# Compilation of functions for the Pihole Server.

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
* 0 * 1,7 * bash /usr/local/bin/update_root_hints.sh &

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

function install_pihole() {
    sudo -u "${user_name}" git clone --depth 1 https://github.com/pi-hole/pi-hole.git "/home/$user_name/Pi-hole"
    cd "/home/$user_name/Pi-hole/automated install/" || exit
    sudo -u "${user_name}" bash "basic-install.sh"
    cd || exit
}

function configure_pihole() {
    # Configure allowlist, denylist, and regex
    # Possible values: id, type, domain, enabled, date_added, date_modified, comment
    mapfile -t allow_block_list <'dns_server_configuration/allow_block_list.txt'

    for i in "${allow_block_list[@]}"; do
        sqlite3 '/etc/pihole/gravity.db' <<EOF
$i
EOF
    done

    # Configure blocklists
    # Possible values: id, address, enabled, date_added, date_modified, comment

    mapfile -t lists <'dns_server_configuration/lists.txt'

    for i in "${lists[@]}"; do
        sqlite3 '/etc/pihole/gravity.db' <<EOF
$i
EOF
    done

    # Configure pihole settings
    grep -q -E 'DNSSEC=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNSSEC=.*/DNSSEC=true/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNSSEC=true' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'PIHOLE_DNS_1=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*PIHOLE_DNS_1=.*/PIHOLE_DNS_1=127.0.0.1#5353/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'PIHOLE_DNS_1=127.0.0.1#5053' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'PIHOLE_DNS_2=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*PIHOLE_DNS_2=.*/PIHOLE_DNS_2=::1#5353/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'PIHOLE_DNS_2=::1#5053' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'DNSMASQ_LISTENING=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNSMASQ_LISTENING=.*/DNSMASQ_LISTENING=all/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNSMASQ_LISTENING=all' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'CONDITIONAL_FORWARDING=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*CONDITIONAL_FORWARDING=.*/CONDITIONAL_FORWARDING=false/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'CONDITIONAL_FORWARDING=false' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'CONDITIONAL_FORWARDING_IP=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*CONDITIONAL_FORWARDING_IP=.*/CONDITIONAL_FORWARDING_IP=${gateway_address}/g" '/etc/pihole/setupVars.conf' || printf '%s\n' "CONDITIONAL_FORWARDING_IP=${gateway_address}" >>'/etc/pihole/setupVars.conf'
    grep -q -E 'CONDITIONAL_FORWARDING_DOMAIN=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*CONDITIONAL_FORWARDING_DOMAIN=.*/CONDITIONAL_FORWARDING_DOMAIN=lan/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'CONDITIONAL_FORWARDING_DOMAIN=lan' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'DNS_FQDN_REQUIRED=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNS_FQDN_REQUIRED=.*/DNS_FQDN_REQUIRED=false/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNS_FQDN_REQUIRED=false' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'DNS_BOGUS_PRIV=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*DNS_BOGUS_PRIV=.*/DNS_BOGUS_PRIV=false/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'DNS_BOGUS_PRIV=false' >>'/etc/pihole/setupVars.conf'
    grep -q -E 'WEBTHEME=' '/etc/pihole/setupVars.conf' && sed -i -E "s/.*WEBTHEME=.*/WEBTHEME=default-dark/g" '/etc/pihole/setupVars.conf' || printf '%s\n' 'WEBTHEME=default-dark' >>'/etc/pihole/setupVars.conf'

    # Set custom domains

    mapfile -t domains <'dns_server_configuration/domains.txt'

    for i in "${domains[@]}"; do
        cat <<EOF >>'/etc/pihole/custom.list'
$i
EOF
    done

    echo 'Set pihole password'
    pihole -a -p

    # Setup pihole folder permissions
    chown -R pihole:pihole '/etc/pihole'
    chmod 777 -R '/etc/pihole'
}

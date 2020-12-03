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

function configure_pihole() {
    git clone --depth 1 https://github.com/pi-hole/pi-hole.git Pi-hole
    cd 'Pi-hole/automated install/' || exit
    bash basic-install.sh
    cd || exit

    # Configure allowlist, denylist, and regex
    # Possible values: id, type, domain, enabled, date_added, date_modified, comment
    sqlite3 /etc/pihole/gravity.db <<EOF
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (10,3,'^.+\.(ru|cn|ro|ml|ga|gq|cf|tk|pw|ua|ug|ve|)$',1,'Block some country TLDs.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (11,3,'porn',1,'Block domains with the word porn in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (12,3,'sex',1,'Block domains with the word sex in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (13,0,'ntscorp.ru',1,'Allow domain.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (14,3,'date',1,'Block domains with the word date in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (15,3,'love',1,'Block domains with the word love in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (16,2,'update',1,'Allow domains with the word update in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (17,3,'hentai',1,'Block domains with the word hentai in them.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (18,0,'accounts.nvgs.nvidia.cn',1,'Allow domain.');
INSERT INTO domainlist (id, type, domain, enabled, comment) VALUES (19,0,'login.nvgs.nvidia.cn',1,'Allow domain.');
EOF

    # Configure blocklists
    # Possible values: id, address, enabled, date_added, date_modified, comment
    sqlite3 /etc/pihole/gravity.db <<EOF
INSERT INTO adlist (id, address, enabled, comment) VALUES (10,'https://mirror1.malwaredomains.com/files/justdomains',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES 11,'https://raw.githubusercontent.com/chadmayfield/my-pihole-blocklists/master/lists/pi_blocklist_porn_all.list',1,'A porn blocklist.');
INSERT INTO adlist (id, address, enabled, comment) VALUES (12,'https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts',0,'Default All in one blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (13,'https://s3.amazonaws.com/lists.disconnect.me/simple_tracking.txt',0,'Default Tracker blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (14,'https://s3.amazonaws.com/lists.disconnect.me/simple_ad.txt',0,'Default Ad blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (15,'https://raw.githubusercontent.com/DandelionSprout/adfilt/master/Alternate%20versions%20Anti-Malware%20List/AntiMalwareHosts.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (16,'https://osint.digitalside.it/Threat-Intel/lists/latestdomains.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (17,'https://s3.amazonaws.com/lists.disconnect.me/simple_malvertising.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (18,'https://v.firebog.net/hosts/Prigent-Crypto.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (19,'https://mirror.cedia.org.ec/malwaredomains/immortal_domains.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (20,'https://www.malwaredomainlist.com/hostslist/hosts.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (21,'https://bitbucket.org/ethanr/dns-blacklists/raw/8575c9f96e5b4a1308f2f12394abd86d0927a4a0/bad_lists/Mandiant_APT1_Report_Appendix_D.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (22,'https://phishing.army/download/phishing_army_blocklist_extended.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (23,'https://gitlab.com/quidsup/notrack-blocklists/raw/master/notrack-malware.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (24,'https://v.firebog.net/hosts/Shalla-mal.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (25,'https://raw.githubusercontent.com/Spam404/lists/master/main-blacklist.txt',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (26,'https://raw.githubusercontent.com/FadeMind/hosts.extras/master/add.Risk/hosts',1,'malware blocklist');
INSERT INTO adlist (id, address, enabled, comment) VALUES (27,'https://urlhaus.abuse.ch/downloads/hostfile/',0,'malware blocklist');

EOF

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
    cat <<EOF >'/etc/pihole/custom.list'
10.1.10.1 MattOpenwrt.miller.lan
10.1.10.3 matt-prox.miller.lan
10.1.10.4 matt-nas.miller.lan
10.1.10.5 Pihole.miller.lan
10.1.10.6 VPN.miller.lan
10.1.10.10 ESXIPi.miller.lan
10.1.10.12 AccessPoint.miller.lan
10.1.10.206 MattSwitch.miller.lan
10.1.1.201 TimSwitch.miller.lan
10.1.1.213 MaryPrinter.miller.lan
EOF

    echo 'Set pihole password'
    pihole -a -p

    # Setup pihole folder permissions
    chown -R pihole:pihole '/etc/pihole'
    chmod 777 -R '/etc/pihole'
}

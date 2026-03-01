# Inventory Variable Reference

Use `example_inventory.yml` as the template for your real inventory. This document describes every variable — its type, purpose, and example value.

---

## Global Variables (`homelab.vars`)

Applied to all hosts in the `homelab` group.

| Variable | Type | Description | Example |
|---|---|---|---|
| `ansible_become` | boolean | Run tasks with privilege escalation | `yes` |
| `ansible_become_method` | string | Escalation method | `sudo` |
| `default_interface` | string | Primary network interface name | `eth0` |
| `docker_username` | string | Docker Hub username for Podman registry login | `myuser` |
| `docker_password` | string | Docker Hub password | `mypassword` |
| `ip_ansible` | string | IP of the Ansible controller (CIDR) — whitelisted in firewalld | `192.168.1.1/32` |
| `management_network` | string | Management network CIDR — whitelisted in firewalld | `192.168.1.0/24` |
| `user_name` | string | Non-root user on managed hosts | `ansible` |
| `porkbun_api_key` | string | Porkbun API key for DNS-01 certificate challenge | `pk1_...` |
| `porkbun_api_key_secret` | string | Porkbun API secret | `sk1_...` |
| `top_domain` | string | Root domain for wildcard certificate | `example.com` |
| `swag_path` | path | Default SWAG config directory (can be overridden per host) | `/opt/swag` |
| `swag_dns_plugin` | string | Certbot DNS plugin name | `porkbun` |
| `nextcloud_dns_name` | string | Nextcloud FQDN | `nextcloud.example.com` |
| `nextcloud_rclone_user` | string | Nextcloud WebDAV username for rclone | `admin` |
| `nextcloud_rclone_pass` | string | Nextcloud WebDAV password for rclone | `secret` |
| `nextcloud_webdav_user` | string | Nextcloud WebDAV user | `admin` |
| `nextcloud_webdav_pass` | string | Nextcloud WebDAV password | `secret` |
| `nextcloud_webdav_path` | string | Nextcloud WebDAV URL | `https://nextcloud.example.com/remote.php/dav/files/user` |
| `locale` | string | System locale | `en_US.UTF-8` |
| `patching_weekday` | integer | Day of week for package update cron (0=Sun) | `1` |
| `patching_hour` | integer | Hour for package update cron | `12` |
| `patching_minute` | integer | Minute for package update cron | `30` |
| `patching_month` | string | Month for package update cron | `"1"` |
| `container_patching_weekday` | integer | Day of week for container update cron | `5` |
| `container_patching_hour` | integer | Hour for container update cron | `3` |
| `container_patching_minute` | integer | Minute for container update cron | `45` |
| `container_patching_month` | string | Month for container update cron | `"12"` |

---

## Per-Host Variables

### `vpn` host

| Variable | Type | Description | Example |
|---|---|---|---|
| `ansible_host` | string | Hostname or IP | `vpn.example.com` |
| `user_name` | string | Comma-separated WireGuard peer usernames | `user1,user2,user3` |
| `vpn_path` | path | WireGuard config directory | `/opt/wireguard` |
| `homelab_domain` | string | Root domain for DDNS A record | `example.com` |
| `homelab_subdomain` | string | Subdomain to update via DDNS | `vpn` |
| `unifi_host` | string | Hostname or IP of Unifi Cloud Gateway (for WAN IP lookup) | `192.168.1.1` |
| `unifi_api_key` | string | Unifi local API key | `api_key_...` |
| `unifi_site_id` | string | **Optional.** Unifi site ID. Defaults to `default`. | `default` |
| `listen_port` | string | WireGuard listen port | `51820` |
| `wireguard_dns_server` | string | DNS server pushed to clients | `192.168.1.1` |
| `wireguard_server_network_prefix` | string | WireGuard tunnel network | `10.0.0.0/24` |
| `wireguard_allowed_ips` | string | Comma-separated routes pushed to clients | `192.168.1.0/24, 10.0.0.1/32` |

---

### `vm1` host (VM1, ID 120)

This host runs all services consolidated. It uses `swag_networks` (list) instead of `swag_network` (scalar), and `semaphore_postgres_path` is distinct from `postgres_path` to prevent data directory collisions.

| Variable | Type | Description | Example |
|---|---|---|---|
| `ansible_host` | string | Hostname or IP | `192.168.1.120` |
| `homelab_domain` | string | Root domain for DDNS A record | `example.com` |
| `homelab_subdomain` | string | Subdomain to update via DDNS | `home` |
| `unifi_host` | string | Hostname or IP of Unifi Cloud Gateway (for WAN IP lookup) | `192.168.1.1` |
| `unifi_api_key` | string | Unifi local API key | `api_key_...` |
| `unifi_site_id` | string | **Optional.** Unifi site ID. Defaults to `default`. | `default` |
| `swag_networks` | list | All Podman networks SWAG must join | `[nextcloud_container_net, navidrome_container_net, ...]` |
| `swag_path` | path | SWAG config directory | `/opt/swag` |
| `swag_dns_plugin` | string | Certbot DNS plugin | `porkbun` |
| `swag_host_domain` | string | Comma-separated subdomains | `nextcloud,paperless,navidrome,vault,semaphore` |
| `proxy_config` | list | One entry per proxied service | — |
| `postgres_path` | path | PostgreSQL 15 data dir (Nextcloud + Paperless) | `/opt/postgres_nextcloud` |
| `nextcloud_path` | path | Nextcloud data directory | `/opt/nextcloud` |
| `nextcloud_disk` | string | UUID of Nextcloud data disk | `UUID=abc123...` |
| `nextcloud_database_name` | string | Nextcloud database | `nextcloud` |
| `nextcloud_database_user` | string | Nextcloud DB user | `nextcloud_user` |
| `nextcloud_database_user_password` | string | Nextcloud DB password | `secret` |
| `nextcloud_admin_user` | string | Nextcloud admin | `admin` |
| `nextcloud_admin_password` | string | Nextcloud admin password | `secret` |
| `nextcloud_trusted_domains` | string | Nextcloud trusted domains | `nextcloud.example.com` |
| `nextcloud_dns_name` | string | Nextcloud FQDN | `nextcloud.example.com` |
| `paperless_data_path` | path | Paperless data directory | `/opt/paperless/data` |
| `paperless_media_path` | path | Paperless media directory | `/opt/paperless/media` |
| `paperless_export_path` | path | Paperless export directory | `/opt/paperless/export` |
| `paperless_consume_path` | path | Paperless consume directory | `/opt/paperless/consume` |
| `paperless_database_name` | string | Paperless database | `paperless` |
| `paperless_database_user` | string | Paperless DB user | `paperless_user` |
| `paperless_database_user_password` | string | Paperless DB password | `secret` |
| `paperless_dns_name` | string | Paperless FQDN | `paperless.example.com` |
| `semaphore_postgres_path` | path | PostgreSQL 17 data dir (Semaphore only) | `/opt/postgres_semaphore` |
| `semaphore_database_name` | string | Semaphore database | `semaphore` |
| `semaphore_database_user` | string | Semaphore DB user | `semaphore_user` |
| `semaphore_database_user_password` | string | Semaphore DB password | `secret` |
| `semaphore_admin_name` | string | Semaphore admin username | `admin` |
| `semaphore_admin_email` | string | Semaphore admin email | `admin@example.com` |
| `semaphore_admin_password` | string | Semaphore admin password | `secret` |
| `semaphore_encryption_key` | string | 32-character Semaphore encryption key | `abc123...` |
| `navidrome_path` | path | Navidrome data directory | `/opt/navidrome` |
| `navidrome_local_music_path` | path | **Optional.** Path bind-mounted as `/music:ro,z` inside the Navidrome container. Defaults to `{{ navidrome_path }}/music` if not set. Use the Nextcloud on-disk path for the user's Music folder. | `/opt/nextcloud/data/admin/files/Music` |
| `nextcloud_borg_backup_path` | path | Local path for Borg backup repository (Nextcloud + Paperless) | `/opt/borg/nextcloud` |
| `nextcloud_paperless_backup_location` | path | rclone remote path for Borg repo sync | `Nextcloud:backup/nextcloud` |
| `vaultwarden_path` | path | Vaultwarden data directory | `/opt/vaultwarden` |
| `vaultwarden_backup_location` | string | rclone remote backup label | `Nextcloud:vaultwarden_backup` |
| `semaphore_backup_location` | string | rclone remote backup path for Semaphore DB dumps | `Nextcloud:semaphore_backup` |
| `container_service_names` | string | Space-separated systemd unit names for SWAG `After=` | `postgres_container redis_container nextcloud_container paperless_ngx navidrome_container vaultwarden semaphore_postgres semaphore` |
| `backup_host` | string | Backup server IP (CIDR) for firewalld | `192.168.1.50/32` |
| `borg_backup_path` | path | Borg repository root (also the second NVMe mount point) | `/opt/borg_backup` |
| `backup_disk` | string | UUID of the second NVMe disk for Borg | `UUID=abc123...` |
| `backup_local` | boolean | `true` — archives local `nextcloud_path` instead of SSHFS | `true` |

---

## Variable Naming Conventions

| Pattern | Meaning | Example |
|---|---|---|
| `{service}_path` | Root data directory for a service | `nextcloud_path`, `vaultwarden_path` |
| `{service}_database_name` | Database name | `nextcloud_database_name` |
| `{service}_database_user` | Database user | `nextcloud_database_user` |
| `{service}_database_user_password` | Database password | `nextcloud_database_user_password` |
| `{service}_admin_user` | Admin username | `nextcloud_admin_user` |
| `{service}_admin_password` | Admin password | `nextcloud_admin_password` |
| `{service}_dns_name` | Service FQDN | `nextcloud_dns_name` |
| `{service}_backup_location` | Backup destination label | `vaultwarden_backup_location` |

---

## `proxy_config` Object Schema

The `proxy_config` variable is a list of objects. Each object generates one nginx proxy-conf file in SWAG.

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `name` | string | Yes | Template and conf filename stem (must match a template in `roles/reverse_proxy/templates/`) | `nextcloud_proxy` |
| `proxy_fqdn` | string | No | Fully-qualified domain name for the subdomain | `nextcloud.example.com` |
| `proxy_upstream_port` | string | No | Upstream container port | `443` |
| `proxy_upstream_protocol` | string | No | Upstream protocol (`http` or `https`) | `https` |
| `container_destination` | string | No | Podman DNS name of the backend container | `nextcloud.dns.podman` |

---

## `swag_networks` vs `swag_network`

- **`swag_network`** (string) — used on single-service hosts where SWAG only needs to join one Podman network
- **`swag_networks`** (list) — used on VM1 where SWAG must join all four service networks

The `swag_container.sh.j2` template checks for `swag_networks` first. If defined, it generates one `--network` flag per entry. If not defined, it falls back to the scalar `swag_network`. This keeps existing single-service host inventories working without changes.

Hosts using `swag_network`: `unificontroller`, `pihole`, `apcontroller`
Hosts using `swag_networks`: `vm1`

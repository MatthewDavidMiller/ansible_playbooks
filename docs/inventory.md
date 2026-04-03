# Inventory Variable Reference

Use `example_inventory.yml` as the template for your real inventory. This document covers the maintained VM1 workflow only.

---

## Global Variables (`homelab.vars`)

Applied to the maintained homelab inventory.

| Variable | Type | Description | Example |
|---|---|---|---|
| `ansible_become` | boolean | Run tasks with privilege escalation | `yes` |
| `ansible_become_method` | string | Escalation method | `sudo` |
| `default_interface` | string | Primary network interface name | `eth0` |
| `secret_env_dir` | path | Root-only directory for runtime env files | `/etc/homelab/secrets` |
| `ip_ansible` | string | Ansible controller IP in CIDR form | `192.168.1.1/32` |
| `management_network` | string | Management network CIDR | `192.168.1.0/24` |
| `user_name` | string | Non-root SSH user on managed hosts | `ansible` |
| `porkbun_api_key` | string | Porkbun API key for DDNS and DNS-01 | `pk1_...` |
| `porkbun_api_key_secret` | string | Porkbun API secret | `sk1_...` |
| `top_domain` | string | Root domain | `example.com` |
| `nextcloud_dns_name` | string | Nextcloud FQDN used by clients and backups | `nextcloud.example.com` |
| `nextcloud_rclone_user` | string | Nextcloud WebDAV username for rclone | `admin` |
| `nextcloud_rclone_pass` | string | Nextcloud WebDAV password for rclone | `secret` |
| `nextcloud_webdav_user` | string | Nextcloud WebDAV username | `admin` |
| `nextcloud_webdav_pass` | string | Nextcloud WebDAV password | `secret` |
| `nextcloud_webdav_path` | string | Nextcloud WebDAV URL | `https://nextcloud.example.com/remote.php/dav/files/user` |
| `locale` | string | System locale | `en_US.UTF-8` |

---

## `vm1` Host

VM1 is the single maintained service host. It runs Traefik, PostgreSQL, Redis, Nextcloud, Paperless NGX, Navidrome, Vaultwarden, Semaphore, and the local backup workflow.

| Variable | Type | Description | Example |
|---|---|---|---|
| `ansible_host` | string | Hostname or IP | `192.168.1.120` |
| `homelab_domain` | string | Root domain used by DDNS | `example.com` |
| `homelab_subdomain` | string | DDNS subdomain for VM1 | `home` |
| `traefik_path` | path | Traefik data directory | `/opt/traefik` |
| `traefik_networks` | list | Podman networks Traefik must join | `[nextcloud_container_net, navidrome_container_net, vaultwarden_container_net, semaphore_container_net]` |
| `traefik_dashboard_fqdn` | string | FQDN for the Traefik dashboard | `traefik.example.com` |
| `traefik_acme_email` | string | ACME account email | `admin@example.com` |
| `proxy_config` | list | Traefik dynamic route definitions | — |
| `postgres_path` | path | Shared PostgreSQL data directory | `/opt/postgres` |
| `nextcloud_path` | path | Nextcloud base directory | `/opt/nextcloud` |
| `nextcloud_disk` | string | UUID entry for the Nextcloud data disk | `UUID=...` |
| `nextcloud_borg_backup_path` | path | Local Borg repo for Nextcloud + Paperless backups | `/opt/nextcloud/borg` |
| `nextcloud_paperless_backup_location` | string | Remote sync target for that Borg repo | `Nextcloud:backup/nextcloud` |
| `nextcloud_uid` | string | Host-side Nextcloud UID | `33` |
| `nextcloud_gid` | string | Host-side Nextcloud GID | `33` |
| `postgres_admin_user` | string | Shared PostgreSQL admin role | `postgres_admin` |
| `postgres_admin_password` | string | Shared PostgreSQL admin password | `secret` |
| `postgres_legacy_bootstrap_user` | string | Optional legacy bootstrap role | `""` |
| `postgres_legacy_bootstrap_password` | string | Optional legacy bootstrap password | `""` |
| `nextcloud_database_name` | string | Nextcloud database name | `nextcloud` |
| `nextcloud_homelab_user` | string | Nextcloud username used for local backup destinations | `admin` |
| `nextcloud_db_user` | string | Nextcloud DB role | `nextcloud_user` |
| `nextcloud_db_password` | string | Nextcloud DB password | `secret` |
| `nextcloud_admin_user` | string | Nextcloud admin user | `admin` |
| `nextcloud_admin_password` | string | Nextcloud admin password | `secret` |
| `nextcloud_trusted_domains` | string | Trusted domain list passed to Nextcloud | `nextcloud.example.com` |
| `nextcloud_dns_name` | string | Nextcloud public FQDN | `nextcloud.example.com` |
| `paperless_path` | path | Paperless base directory | `/opt/paperless` |
| `paperless_data_path` | path | Paperless data directory | `/opt/paperless/data` |
| `paperless_media_path` | path | Paperless media directory | `/opt/paperless/media` |
| `paperless_export_path` | path | Paperless export directory | `/opt/paperless/export` |
| `paperless_consume_path` | path | Paperless consume directory | `/opt/paperless/consume` |
| `paperless_database_name` | string | Paperless database name | `paperless` |
| `paperless_db_user` | string | Paperless DB role | `paperless_user` |
| `paperless_db_password` | string | Paperless DB password | `secret` |
| `paperless_dns_name` | string | Paperless public FQDN | `paperless.example.com` |
| `semaphore_database_name` | string | Semaphore database name | `semaphore` |
| `semaphore_db_user` | string | Semaphore DB role | `semaphore_user` |
| `semaphore_db_password` | string | Semaphore DB password | `secret` |
| `semaphore_admin_name` | string | Semaphore admin username | `admin` |
| `semaphore_admin_email` | string | Semaphore admin email | `admin@example.com` |
| `semaphore_admin_password` | string | Semaphore admin password | `secret` |
| `semaphore_encryption_key` | string | Semaphore encryption key | `abc123...` |
| `semaphore_known_hosts` | string | Known-host block mounted into Semaphore | `192.168.1.10 ssh-ed25519 AAAA...` |
| `semaphore_backup_location` | string | Local or rclone destination label | `Nextcloud:semaphore_backup` |
| `navidrome_path` | path | Navidrome base directory | `/opt/navidrome` |
| `navidrome_backup_location` | string | Navidrome backup destination label | `Nextcloud:navidrome_backup` |
| `navidrome_local_music_path` | path | Optional host path mounted as `/music` | `/opt/nextcloud/data/admin/files/Music` |
| `navidrome_uid` | string | Navidrome runtime UID | `33` |
| `navidrome_gid` | string | Navidrome runtime GID | `33` |
| `vaultwarden_path` | path | Vaultwarden base directory | `/opt/vaultwarden` |
| `vaultwarden_backup_location` | string | Vaultwarden backup destination label | `Nextcloud:vaultwarden_backup` |
| `vaultwarden_signups_allowed` | boolean | Public signup toggle | `false` |
| `container_service_names` | string | Space-separated units for Traefik `After=` | `postgres_container redis_container nextcloud_container paperless_ngx navidrome_container vaultwarden semaphore` |
| `backup_host` | string | Backup server IP in CIDR form | `192.168.1.50/32` |
| `borg_backup_path` | path | Borg repository root on the backup disk | `/opt/borg_backup` |
| `backup_disk` | string | UUID entry for the backup disk | `UUID=...` |
| `backup_local` | boolean | Use local Nextcloud-backed service backups | `true` |

---

## Artifact Locks

Maintained container images are resolved in `vm1.yml` from `artifacts/containers.lock.yml` as upstream digest refs. Inventory does not set service image refs directly in the maintained path.

`artifacts/cloud_images.lock.yml` serves the same role for the Proxmox Rocky image and must contain a versioned URL plus SHA256 before provisioning.

---

## Variable Naming Conventions

| Pattern | Meaning | Example |
|---|---|---|
| `{service}_path` | Root data directory for a service | `nextcloud_path` |
| `{service}_database_name` | Database name | `paperless_database_name` |
| `{service}_db_user` | Per-service PostgreSQL application user | `semaphore_db_user` |
| `{service}_db_password` | Per-service PostgreSQL application password | `nextcloud_db_password` |
| `{service}_dns_name` | Public FQDN | `paperless_dns_name` |
| `{service}_backup_location` | Backup destination label | `vaultwarden_backup_location` |

---

## `proxy_config` Object Schema

Each `proxy_config` entry renders one Traefik dynamic config file in `{{ traefik_path }}/config/`.

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `name` | string | Yes | Router/service name stem | `nextcloud_proxy` |
| `proxy_fqdn` | string | Yes | Router `Host()` value | `nextcloud.example.com` |
| `proxy_upstream_port` | string | Yes | Upstream container port | `80` |
| `proxy_upstream_protocol` | string | Yes | Upstream protocol | `http` |
| `container_destination` | string | Yes | Podman DNS backend name | `nextcloud.dns.podman` |
| `proxy_allow_encoded_slash` | boolean | No | Enable encoded-slash forwarding when needed | `true` |
| `proxy_management_only` | boolean | No | Restrict the route to the management network | `true` |

All entries use the generic `service_proxy.yml.j2` template.

---

## `traefik_networks`

`traefik_networks` lists every Podman network Traefik must join so it can reach proxied backends by Podman DNS name (`<container>.dns.podman`).

On VM1, Traefik joins each service network that hosts a proxied container.

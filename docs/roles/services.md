# Service Roles Reference

Each service role deploys one or more containers using the Podman + systemd pattern. See [CLAUDE.md](../../CLAUDE.md) for the pattern description and [architecture.md](../architecture.md) for network design.

---

### `reverse_proxy`

Deploys SWAG (linuxserver.io nginx + Certbot) for TLS termination and reverse proxying. Generates per-service nginx proxy configs from the `proxy_config` inventory variable.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/linuxserver/swag:latest`

**Ports:** 443/tcp (via Podman `-p 443:443/tcp`; no explicit firewalld rule needed — Podman's DNAT rules in PREROUTING preempt zone filtering)

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `swag_path` | path | SWAG config directory | `/opt/swag` |
| `top_domain` | string | Root domain for wildcard cert | `example.com` |
| `swag_host_domain` | string | Comma-separated subdomains | `nextcloud,paperless` |
| `swag_dns_plugin` | string | Certbot DNS plugin name | `porkbun` |
| `porkbun_api_key` | string | Porkbun API key | `pk1_...` |
| `porkbun_api_key_secret` | string | Porkbun API secret | `sk1_...` |
| `proxy_config` | list | Proxy config objects — see [inventory.md](../inventory.md#proxy_config-object-schema) | — |
| `swag_network` | string | Podman network to join (single-service hosts) | `nextcloud_container_net` |
| `swag_networks` | list | Podman networks to join (AllServices VM) — takes precedence over `swag_network` if defined | `[nextcloud_container_net, ...]` |
| `container_service_names` | string | Space-separated systemd unit names for `After=` in SWAG service | `nextcloud_container postgres_container` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `swag_container.sh.j2` | `/usr/local/bin/swag_container.sh` | `podman run` command; supports both `swag_network` and `swag_networks` |
| `swag_container.service.j2` | `/etc/systemd/system/swag_container.service` | Systemd unit for SWAG |
| `porkbun.ini.j2` | `{{ swag_path }}/dns-conf/porkbun.ini` | Porkbun DNS challenge credentials |
| `{name}_proxy.conf.j2` | `{{ swag_path }}/nginx/proxy-confs/{name}.subdomain.conf` | Per-service nginx subdomain proxy config (one per `proxy_config` entry) |
| `ssl.conf.j2` | `{{ swag_path }}/nginx/ssl.conf` | TLS settings |
| `default.conf.j2` | `{{ swag_path }}/nginx/site-confs/default.conf` | Default nginx site config |
| `proxy.conf.j2` | `{{ swag_path }}/nginx/proxy.conf` | Shared proxy settings |

**Notes:**
- The `swag_container.sh.j2` template checks `swag_networks is defined` — if true, generates one `--network` flag per list entry; otherwise uses the scalar `swag_network`
- Per-service proxy config templates are named `{proxy_config[].name}_proxy.conf.j2` and must exist in `roles/reverse_proxy/templates/`

---

### `nextcloud`

Deploys Nextcloud with PostgreSQL 15 and Redis. Also sets up Borg backup and creates the container network used by Paperless NGX.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container images:** `docker.io/postgres:15`, `docker.io/redis:latest`, `docker.io/nextcloud:latest`

**Data directories:** `{{ postgres_path }}`, `{{ nextcloud_path }}`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `postgres_path` | path | PostgreSQL 15 data directory | `/opt/postgres` |
| `nextcloud_path` | path | Nextcloud data directory | `/opt/nextcloud` |
| `nextcloud_disk` | string | UUID of Nextcloud data disk | `UUID=abc123...` |
| `nextcloud_database_name` | string | Database name | `nextcloud` |
| `nextcloud_database_user` | string | Database user | `nextcloud_user` |
| `nextcloud_database_user_password` | string | Database password | `secret` |
| `nextcloud_admin_user` | string | Admin username | `admin` |
| `nextcloud_admin_password` | string | Admin password | `secret` |
| `nextcloud_trusted_domains` | string | Trusted domains | `nextcloud.example.com` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `postgres_container.sh.j2` | `/usr/local/bin/postgres_container.sh` | PostgreSQL 15 container launch script |
| `postgres_container.service.j2` | `/etc/systemd/system/postgres_container.service` | Systemd unit |
| `redis_container.sh.j2` | `/usr/local/bin/redis_container.sh` | Redis container launch script |
| `redis_container.service.j2` | `/etc/systemd/system/redis_container.service` | Systemd unit |
| `nextcloud_container.sh.j2` | `/usr/local/bin/nextcloud_container.sh` | Nextcloud container launch script |
| `nextcloud_container.service.j2` | `/etc/systemd/system/nextcloud_container.service` | Systemd unit |
| `db_wrapper.sh.j2` | `/usr/local/bin/db_wrapper.sh` | Database maintenance wrapper |
| `backup_nextcloud_paperless.sh.j2` | `/usr/local/bin/backup_nextcloud_paperless.sh` | Daily Borg backup script for Nextcloud + Paperless |

**Systemd services installed:** `postgres_container`, `redis_container`, `nextcloud_container`

---

### `paperless_ngx`

Deploys Paperless NGX. Depends on the PostgreSQL 15 and Redis containers created by the `nextcloud` role — run `nextcloud` before `paperless_ngx`.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/paperlessngx/paperless-ngx:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `paperless_data_path` | path | Paperless data directory | `/opt/paperless/data` |
| `paperless_media_path` | path | Paperless media directory | `/opt/paperless/media` |
| `paperless_export_path` | path | Paperless export directory | `/opt/paperless/export` |
| `paperless_consume_path` | path | Paperless consume directory | `/opt/paperless/consume` |
| `paperless_database_name` | string | Database name (in PG15) | `paperless` |
| `paperless_database_user` | string | Database user | `paperless_user` |
| `paperless_database_user_password` | string | Database password | `secret` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `paperless_ngx.sh.j2` | `/usr/local/bin/paperless_ngx.sh` | Container launch script |
| `paperless_ngx.service.j2` | `/etc/systemd/system/paperless_ngx.service` | Systemd unit |

**Systemd services installed:** `paperless_ngx`

---

### `semaphore`

Deploys Semaphore CI/CD with its own PostgreSQL 17 instance. Uses `semaphore_postgres_path` (not `postgres_path`) to keep the data directory separate from the Nextcloud PostgreSQL 15 instance — critical on the AllServices VM where both run on the same host.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container images:** `docker.io/postgres:17`, `docker.io/semaphoreui/semaphore:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `semaphore_postgres_path` | path | PostgreSQL 17 data directory | `/opt/postgres_semaphore` |
| `semaphore_database_name` | string | Database name | `semaphore` |
| `semaphore_database_user` | string | Database user | `semaphore_user` |
| `semaphore_database_user_password` | string | Database password | `secret` |
| `semaphore_admin_name` | string | Admin username | `admin` |
| `semaphore_admin_email` | string | Admin email | `admin@example.com` |
| `semaphore_admin_password` | string | Admin password | `secret` |
| `semaphore_encryption_key` | string | 32-character encryption key | `abc123...` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `semaphore_postgres.sh.j2` | `/usr/local/bin/semaphore_postgres.sh` | PostgreSQL 17 container launch script |
| `semaphore_postgres.service.j2` | `/etc/systemd/system/semaphore_postgres.service` | Systemd unit |
| `semaphore.sh.j2` | `/usr/local/bin/semaphore.sh` | Semaphore container launch script |
| `semaphore.service.j2` | `/etc/systemd/system/semaphore.service` | Systemd unit |

**Systemd services installed:** `semaphore_postgres`, `semaphore`

**Notes:**
- `semaphore_postgres_path` is intentionally a different variable from `postgres_path`. On the AllServices VM, `postgres_path` points to PostgreSQL 15 data (Nextcloud) and `semaphore_postgres_path` points to PostgreSQL 17 data (Semaphore). Using the same variable would cause data directory collision.
- On single-host Semaphore deployments (e.g., the `ansible` VM), define `semaphore_postgres_path` in the host's inventory entry — do not use `postgres_path` for Semaphore.

---

### `vaultwarden`

Deploys Vaultwarden password manager with SQLite. Sets up a daily backup cron job.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/vaultwarden/server:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `vaultwarden_path` | path | Vaultwarden data directory | `/opt/vaultwarden` |
| `vaultwarden_backup_location` | string | rclone remote backup path | `gdrive:vaultwarden_backup` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `vaultwarden.sh.j2` | `/usr/local/bin/vaultwarden.sh` | Container launch script |
| `vaultwarden.service.j2` | `/etc/systemd/system/vaultwarden.service` | Systemd unit |
| `backup_db.j2` | `/usr/local/bin/backup_vaultwarden.sh` | Daily SQLite backup script |

**Systemd services installed:** `vaultwarden`

---

### `navidrome`

Deploys Navidrome music server. Mounts music files via rclone (WebDAV) FUSE mount. Sets up a check timer to restart the mount if it becomes stale.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/deluan/navidrome:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `navidrome_path` | path | Navidrome data directory | `/opt/navidrome` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `navidrome_container.sh.j2` | `/usr/local/bin/navidrome_container.sh` | Container launch script |
| `navidrome_container.service.j2` | `/etc/systemd/system/navidrome_container.service` | Systemd unit |
| `rclone_mount_music.sh.j2` | `/usr/local/bin/rclone_mount_music.sh` | rclone FUSE mount script |
| `rclone_mount_music.service.j2` | `/etc/systemd/system/rclone_mount_music.service` | Systemd unit for rclone mount |
| `check_music_rclone.sh.j2` | `/usr/local/bin/check_music_rclone.sh` | Health check script |
| `check_music_rclone.service.j2` | `/etc/systemd/system/check_music_rclone.service` | One-shot service for health check |
| `check_music_rclone.timer.j2` | `/etc/systemd/system/check_music_rclone.timer` | Periodic timer for health check |
| `backup_navidrome.sh.j2` | `/usr/local/bin/backup_navidrome.sh` | Daily backup script |
| `davfs2_secrets.j2` | `/etc/davfs2/secrets` | WebDAV credentials |

**Systemd services installed:** `navidrome_container`, `rclone_mount_music`, `check_music_rclone.timer`

**Notes:** On Rocky Linux 10 the `virt_use_fusefs` SELinux boolean must be set before starting the container — handled by `standard_selinux`.

---

### `vpn`

Deploys WireGuard in a container. Sets up Porkbun DDNS to keep the server's dynamic IP registered in DNS.

**Distributions:** Rocky Linux 10 (also Debian/Arch with condition gates)

**Container image:** `docker.io/linuxserver/wireguard:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `vpn_path` | path | WireGuard config directory | `/opt/wireguard` |
| `user_name` | string | Comma-separated peer usernames | `user1,user2` |
| `homelab_domain` | string | Root domain for DDNS | `example.com` |
| `homelab_subdomain` | string | Subdomain for DDNS | `vpn` |
| `listen_port` | string | WireGuard listen port | `51820` |
| `wireguard_dns_server` | string | DNS server for clients | `192.168.1.1` |
| `wireguard_server_network_prefix` | string | Tunnel network | `10.0.0.0/24` |
| `wireguard_allowed_ips` | string | Routes pushed to clients | `192.168.1.0/24, 10.0.0.1/32` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `wireguard.sh.j2` | `/usr/local/bin/wireguard.sh` | Container launch script |
| `wireguard.service.j2` | `/etc/systemd/system/wireguard.service` | Systemd unit |
| `porkbun-ddns.sh.j2` | `/usr/local/bin/porkbun-ddns.sh` | DDNS update script |
| `porkbun-ddns.service.j2` | `/etc/systemd/system/porkbun-ddns.service` | Systemd unit for DDNS |
| `wireguard_module.j2` | `/etc/modules-load.d/wireguard.conf` | Kernel module load config |

**Systemd services installed:** `wireguard`, `porkbun-ddns`

---

### `backup`

Installs Borg backup server (Debian 12 only). Sets up an SSHFS mount and backup scripts for Nextcloud.

**Distributions:** Debian 12 only

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `borg_backup_path` | path | Borg repository root | `/opt/borg` |
| `ssh_mount_path` | path | SSHFS mount point | `/mnt/nextcloud_backup` |
| `backup_disk` | string | UUID of backup disk | `UUID=abc123...` |
| `nextcloud_host` | string | Nextcloud server hostname | `nextcloud.example.com` |
| `nextcloud_backup_path` | path | Borg repo path for Nextcloud | `/opt/borg/nextcloud` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `init_backup_repo.sh.j2` | `/usr/local/bin/init_backup_repo.sh` | Initialises Borg repository |
| `backup_files.sh.j2` | `/usr/local/bin/backup_files.sh` | Daily backup script |

---

### `dns`

Deploys Pi-hole in a container with a custom network subnet. Disables `systemd-resolved` (conflicts with Pi-hole's DNS port). Sets up daily database backup.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/pihole/pihole:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `pihole_path` | path | Pi-hole data directory | `/opt/pihole` |
| `pihole_container_network` | string | Podman network name | `pihole_net` |
| `pihole_container_ip_address` | string | Pi-hole container IP | `172.16.1.2` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `pihole.sh.j2` | `/usr/local/bin/pihole.sh` | Container launch script |
| `pihole.service.j2` | `/etc/systemd/system/pihole.service` | Systemd unit |
| `backup_db.j2` | `/usr/local/bin/backup_pihole.sh` | Daily DB backup script |

**Systemd services installed:** `pihole`

---

### `unificontroller`

Deploys the Ubiquiti Unifi Controller.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/linuxserver/unifi-network-application:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `unificontroller_path` | path | Unifi data directory | `/opt/unifi` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `unificontroller.sh.j2` | `/usr/local/bin/unificontroller.sh` | Container launch script |
| `unificontroller.service.j2` | `/etc/systemd/system/unificontroller.service` | Systemd unit |

**Systemd services installed:** `unificontroller`

---

### `omadacontroller`

Deploys the TP-Link Omada Controller.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/mbentley/omada-controller:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `unificontroller_path` | path | Omada data directory (reuses variable name) | `/opt/omada` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `apcontroller.sh.j2` | `/usr/local/bin/apcontroller.sh` | Container launch script |
| `apcontroller.service.j2` | `/etc/systemd/system/apcontroller.service` | Systemd unit |

**Systemd services installed:** `apcontroller`

---

### `ansible`

Installs Ansible and sshpass so the host can run playbooks.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

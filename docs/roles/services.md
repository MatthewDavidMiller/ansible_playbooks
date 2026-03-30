# Service Roles Reference

Each service role deploys one or more containers using the Podman + systemd pattern. See [architecture.md](../architecture.md) for network design and [playbooks.md](../playbooks.md) for playbook composition.

---

### `dynamic_dns`

Updates a Porkbun DNS A record with the host's current WAN IP, retrieved from the Porkbun ping endpoint.

**Distributions:** Rocky Linux 10

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `homelab_domain` | string | Root domain for the A record | `example.com` |
| `homelab_subdomain` | string | Subdomain to update | `vpn` |
| `porkbun_api_key` | string | Porkbun API key (global) | `pk1_...` |
| `porkbun_api_key_secret` | string | Porkbun API secret (global) | `sk1_...` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `dynamic_dns.py.j2` | `/usr/local/bin/dynamic_dns.py` | Python script; fetches WAN IP via Porkbun ping, compares to cache, updates Porkbun A record only when changed |

**Notable tasks:**
- Installs `python3-requests` via dnf
- Writes `/etc/logrotate.d/dynamic_dns` (weekly, 4 weeks retained, compressed)
- Installs a cron job running every 5 minutes; output appended to `/var/log/dynamic_dns.log`

**Log file:** `/var/log/dynamic_dns.log` — rotated at 1 MB, 5 backups retained. Also echoes to stderr, so manual runs show output directly.

**Cache file:** `/var/cache/dynamic_dns_ip` — stores the last successfully applied IP. When the cached IP matches the current WAN IP the script exits immediately with no API calls.

---

### `reverse_proxy`

Deploys Traefik v3 for TLS termination and reverse proxying. Uses Traefik's built-in ACME engine with Porkbun DNS-01 challenge for per-FQDN certificates, and the file provider for dynamic routing config.

**Distributions:** Rocky Linux 10

**Container image:** `docker.io/traefik:v3`

**Ports:** 80/tcp (HTTP→HTTPS redirect) + 443/tcp (HTTPS). Both exposed via Podman `-p`; no explicit firewalld rules needed — Podman's DNAT rules in PREROUTING preempt zone filtering.

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `traefik_path` | path | Traefik data directory | `/opt/traefik` |
| `traefik_networks` | list | All Podman networks Traefik must join | `[nextcloud_container_net, ...]` |
| `traefik_dashboard_fqdn` | string | FQDN for Traefik dashboard (gets its own cert) | `traefik.example.com` |
| `traefik_acme_email` | string | Email for Let's Encrypt ACME account registration | `admin@example.com` |
| `porkbun_api_key` | string | Porkbun API key | `pk1_...` |
| `porkbun_api_key_secret` | string | Porkbun API secret | `sk1_...` |
| `management_network` | string | Management network CIDR — for dashboard `ipAllowList` | `192.168.1.0/24` |
| `ip_ansible` | string | Ansible controller IP (CIDR) — for dashboard `ipAllowList` | `192.168.1.1/32` |
| `proxy_config` | list | Proxy config objects — see [inventory.md](../inventory.md#proxy_config-object-schema) | — |
| `container_service_names` | string | Space-separated systemd unit names for `After=` in Traefik service | `nextcloud_container postgres_container` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `traefik_container.sh.j2` | `/usr/local/bin/traefik_container.sh` | `podman run` command; iterates `traefik_networks` for `--network` flags |
| `traefik_container.service.j2` | `/etc/systemd/system/traefik_container.service` | Systemd unit for Traefik |
| `traefik.yml.j2` | `{{ traefik_path }}/traefik.yml` | Traefik static config (entrypoints, ACME resolver, file provider) |
| `tls.yml.j2` | `{{ traefik_path }}/config/tls.yml` | TLS options: min TLS 1.2, cipher suites, SNI strict |
| `security.yml.j2` | `{{ traefik_path }}/config/security.yml` | Middlewares: `security-headers` (HSTS, X-Frame-Options, etc.) and `ip-allowlist-mgmt` |
| `dashboard.yml.j2` | `{{ traefik_path }}/config/dashboard.yml` | Dashboard router — HTTPS only, restricted to management network |
| `service_proxy.yml.j2` | `{{ traefik_path }}/config/{{ name }}.yml` | Generic service router + backend (one file per `proxy_config` entry) |

**Notes:**
- `acme.json` is initialised with `force: false` — an existing file (with live certs) is never overwritten by Ansible
- Setting `certResolver: porkbun` on the `websecure` entrypoint without specifying wildcard `domains` causes Traefik to request individual certs for each router's exact `Host()` FQDN
- The generic `service_proxy.yml.j2` template is used for all `proxy_config` entries — no per-service template is needed

---

### `nextcloud`

Deploys Nextcloud with PostgreSQL 17 and Redis. Also sets up Borg backup and creates the container network used by Paperless NGX. PostgreSQL 17 is shared with Paperless NGX and Semaphore.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container images:** `docker.io/postgres:17`, `docker.io/redis:latest`, `docker.io/nextcloud:latest`

**Data directories:** `{{ postgres_path }}`, `{{ nextcloud_path }}`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `postgres_path` | path | PostgreSQL 17 data directory (shared with Paperless and Semaphore) | `/opt/postgres` |
| `nextcloud_path` | path | Nextcloud data directory | `/opt/nextcloud` |
| `nextcloud_disk` | string | UUID of Nextcloud data disk | `UUID=abc123...` |
| `nextcloud_database_name` | string | Database name | `nextcloud` |
| `postgres_database_user` | string | PostgreSQL superuser role (shared with Paperless and Semaphore) | `nextcloud_user` |
| `postgres_database_user_password` | string | PostgreSQL superuser password | `secret` |
| `nextcloud_admin_user` | string | Admin username | `admin` |
| `nextcloud_admin_password` | string | Admin password | `secret` |
| `nextcloud_trusted_domains` | string | Trusted domains | `nextcloud.example.com` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `postgres_container.sh.j2` | `/usr/local/bin/postgres_container.sh` | PostgreSQL 17 container launch script |
| `postgres_container.service.j2` | `/etc/systemd/system/postgres_container.service` | Systemd unit |
| `redis_container.sh.j2` | `/usr/local/bin/redis_container.sh` | Redis container launch script |
| `redis_container.service.j2` | `/etc/systemd/system/redis_container.service` | Systemd unit |
| `nextcloud_container.sh.j2` | `/usr/local/bin/nextcloud_container.sh` | Nextcloud container launch script |
| `nextcloud_container.service.j2` | `/etc/systemd/system/nextcloud_container.service` | Systemd unit |
| `db_wrapper.sh.j2` | `/usr/local/bin/db_wrapper.sh` | Database maintenance wrapper |
| `backup_nextcloud_paperless.sh.j2` | `/usr/local/bin/backup_nextcloud_paperless.sh` | Daily Borg backup script for Nextcloud + Paperless |

**Systemd services installed:** `postgres_container`, `redis_container`, `nextcloud_container`

**Notes:**
- PostgreSQL runs as UID/GID `999:999`; the `custom-init/db_wrapper.sh` wrapper must be owned by `999:999` so the image entrypoint can execute it after `--user=999:999` is applied.
- Redis uses `--cap-drop=ALL` with `CHOWN`, `FOWNER`, and `DAC_OVERRIDE` added back for startup-time filesystem handling inside the image.

---

### `paperless_ngx`

Deploys Paperless NGX. Depends on the PostgreSQL 17 and Redis containers created by the `nextcloud` role — run `nextcloud` before `paperless_ngx`.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/paperlessngx/paperless-ngx:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `paperless_data_path` | path | Paperless data directory | `/opt/paperless/data` |
| `paperless_media_path` | path | Paperless media directory | `/opt/paperless/media` |
| `paperless_export_path` | path | Paperless export directory | `/opt/paperless/export` |
| `paperless_consume_path` | path | Paperless consume directory | `/opt/paperless/consume` |
| `paperless_database_name` | string | Database name | `paperless` |
| `postgres_database_user` | string | PostgreSQL superuser role (shared — defined in `nextcloud` role) | `nextcloud_user` |
| `postgres_database_user_password` | string | PostgreSQL superuser password | `secret` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `paperless_ngx.sh.j2` | `/usr/local/bin/paperless_ngx.sh` | Container launch script |
| `paperless_ngx.service.j2` | `/etc/systemd/system/paperless_ngx.service` | Systemd unit |

**Systemd services installed:** `paperless_ngx`

**Notes:**
- Paperless NGX uses `--cap-drop=ALL` with `CHOWN`, `SETUID`, `SETGID`, `FOWNER`, and `DAC_OVERRIDE` added back to support `USERMAP_UID/GID` and entrypoint privilege transitions.

---

### `semaphore`

Deploys Semaphore CI/CD. Uses the shared PostgreSQL 17 database created by the `nextcloud` role. The daily backup script (`backup_semaphore.sh`) dumps the Semaphore database to `/tmp/semaphore_db_<date>.sql`, then:
- When `backup_local: true`: copies the dump directly to `{{ nextcloud_path }}/data/{{ nextcloud_admin_user }}/files/{{ semaphore_backup_location | replace('Nextcloud:', '') }}` and runs `occ files:scan`.
- Otherwise: uploads via `rclone copy` to `Nextcloud:{{ semaphore_backup_location }}`.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/semaphoreui/semaphore:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `semaphore_database_name` | string | Database name (in shared PostgreSQL 17) | `semaphore` |
| `postgres_database_user` | string | PostgreSQL superuser role (shared — defined in `nextcloud` role) | `nextcloud_user` |
| `postgres_database_user_password` | string | PostgreSQL superuser password | `secret` |
| `semaphore_admin_name` | string | Admin username | `admin` |
| `semaphore_admin_email` | string | Admin email | `admin@example.com` |
| `semaphore_admin_password` | string | Admin password | `secret` |
| `semaphore_encryption_key` | string | 32-character encryption key | `abc123...` |
| `semaphore_backup_location` | string | Backup destination label | `Nextcloud:semaphore_backup` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `semaphore.sh.j2` | `/usr/local/bin/semaphore.sh` | Semaphore container launch script |
| `semaphore.service.j2` | `/etc/systemd/system/semaphore.service` | Systemd unit |
| `backup_semaphore.sh.j2` | `/usr/local/bin/backup_semaphore.sh` | Daily database dump; local cp or rclone based on `backup_local` |

**Systemd services installed:** `semaphore`

**Cron jobs installed:** `Backup Semaphore` (daily)

**Notes:**
- Semaphore connects to the shared PostgreSQL 17 instance via Podman DNS (`postgres.dns.podman`) on the `semaphore_container_net` network.

---

### `vaultwarden`

Deploys Vaultwarden password manager with SQLite. Sets up a daily backup cron job.

The backup script (`backup_db.j2`) takes a SQLite hot copy, then:
- When `backup_local: true`: copies it directly to `{{ nextcloud_path }}/data/{{ nextcloud_admin_user }}/files/{{ vaultwarden_backup_location | replace('Nextcloud:', '') }}` and runs `occ files:scan`.
- Otherwise: uploads via `rclone copy` to `Nextcloud:{{ vaultwarden_backup_location }}`.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Container image:** `docker.io/vaultwarden/server:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `vaultwarden_path` | path | Vaultwarden data directory | `/opt/vaultwarden` |
| `vaultwarden_backup_location` | string | Backup destination label | `Nextcloud:vaultwarden_backup` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `vaultwarden.sh.j2` | `/usr/local/bin/vaultwarden.sh` | Container launch script |
| `vaultwarden.service.j2` | `/etc/systemd/system/vaultwarden.service` | Systemd unit |
| `backup_db.j2` | `/usr/local/bin/backup_vaultwarden.sh` | Daily SQLite backup; local cp or rclone based on `backup_local` |

**Systemd services installed:** `vaultwarden`

**Notes:**
- Vaultwarden uses `--cap-drop=ALL` with `NET_BIND_SERVICE` added back.

---

### `navidrome`

Deploys Navidrome music server. Music files are served from a local path bind-mounted as `/music:ro,z` inside the container. Set `navidrome_local_music_path` to use the Nextcloud on-disk Music folder directly (e.g., on VM1 where Nextcloud is colocated); otherwise the role falls back to `{{ navidrome_path }}/music`.

The daily backup script (`backup_navidrome.sh`) branches on `backup_local`:
- When `backup_local: true`: copies `.db` files directly to `{{ nextcloud_path }}/data/{{ nextcloud_admin_user }}/files/{{ navidrome_backup_location | replace('Nextcloud:', '') }}` and runs `occ files:scan`. Prunes files older than 30 days using `find`.
- Otherwise: uploads via `rclone copy` to `Nextcloud:{{ navidrome_backup_location }}` and prunes via `rclone delete --min-age 30d`.

**Distributions:** Rocky Linux 10

**Container image:** `docker.io/deluan/navidrome:latest`

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `navidrome_path` | path | Navidrome data directory | `/opt/navidrome` |
| `navidrome_local_music_path` | path | **Optional.** Local path to bind-mount as `/music:ro,z`. Defaults to `{{ navidrome_path }}/music`. | `/opt/nextcloud/data/admin/files/Music` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `navidrome_container.sh.j2` | `/usr/local/bin/navidrome_container.sh` | Container launch script; uses `navidrome_local_music_path` if defined, else `navidrome_path/music` |
| `navidrome_container.service.j2` | `/etc/systemd/system/navidrome_container.service` | Systemd unit; waits for the configured music path and orders after Nextcloud when using the local Nextcloud data tree |
| `backup_navidrome.sh.j2` | `/usr/local/bin/backup_navidrome.sh` | Daily backup script; local cp or rclone based on `backup_local` |

**Systemd services installed:** `navidrome_container`

**Notes:**
- Navidrome uses `--cap-drop=ALL` with `DAC_READ_SEARCH` added back so the non-root process can traverse the mounted music library.
- When `navidrome_local_music_path` points into `{{ nextcloud_path }}/data/...`, the systemd unit waits for that path and starts after `nextcloud_container.service` so the library is present after boot.

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

**Notes:**
- Pi-hole uses `--cap-drop=ALL` with `NET_BIND_SERVICE` added back because it binds port `53/tcp` and `53/udp`.

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

---

### `podman_service` (reusable library role)

A generic scaffolding role that encapsulates the standard four-step container deployment pattern. It is a reusable building block for future service roles — current service roles use their own custom templates rather than this role.

**Purpose:** Centralises the repetitive work of creating data directories, writing a `podman run` shell script, writing a systemd unit, and enabling the service. Service roles that adopt it pass configuration via variables rather than maintaining per-role templates.

**Variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `podman_service_name` | string | Service name (used for script and unit filenames) | `vaultwarden` |
| `podman_service_image` | string | Container image | `docker.io/vaultwarden/server:latest` |
| `podman_service_dirs` | list | Directories to create with owner/mode | `[{path: /opt/vw, owner: "1000", mode: "0770"}]` |
| `podman_service_ports` | list | Port mappings | `["8080:80"]` |
| `podman_service_volumes` | list | Volume mounts | `["/opt/vw:/data:Z"]` |
| `podman_service_env` | dict | Environment variables | `{TZ: America/New_York}` |
| `podman_service_memory` | string | Memory limit | `256m` |
| `podman_service_caps_add` | list | Capabilities to add (after cap-drop=ALL) | `[NET_BIND_SERVICE]` |
| `podman_service_extra_args` | string | Additional `podman run` flags verbatim | `--pids-limit=200` |

**Templates:**

| Template | Description |
|---|---|
| `podman_run.sh.j2` | Generic `podman run` command builder |
| `podman_service.service.j2` | Generic systemd unit |

**See also:** `roles/podman_service/README.md` for full usage examples.

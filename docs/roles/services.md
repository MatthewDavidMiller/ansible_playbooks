# Service Roles Reference

These are the maintained service roles used by `vm1.yml`. Historical service roles live under the archive.

---

### `dynamic_dns`

Updates the VM1 Porkbun A record when the WAN IP changes.

**Required variables:** `homelab_domain`, `homelab_subdomain`, `porkbun_api_key`, `porkbun_api_key_secret`, `secret_env_dir`

**Templates:** `dynamic_dns.py.j2`, `dynamic_dns.env.j2`

**Key behavior:** writes a root-only env file, caches the last applied IP, logs to `/var/log/dynamic_dns.log`, and runs from cron every five minutes.

---

### `reverse_proxy`

Deploys Traefik v3 for HTTPS termination and service routing on VM1.

**Required variables:** `traefik_path`, `traefik_networks`, `traefik_dashboard_fqdn`, `traefik_acme_email`, `proxy_config`, `container_service_names`, `management_network`, `ip_ansible`, `secret_env_dir`, `traefik_image`

**Templates:** `traefik_container.sh.j2`, `traefik_container.service.j2`, `traefik.yml.j2`, `tls.yml.j2`, `security.yml.j2`, `dashboard.yml.j2`, `service_proxy.yml.j2`, `traefik.env.j2`

**Key behavior:** publishes ports 80 and 443, requests per-FQDN certificates through Porkbun DNS-01, renders dynamic route files from `proxy_config`, and runs only against pre-pulled approved digest refs.

---

### `nextcloud`

Deploys the shared PostgreSQL container, Redis container, and Nextcloud itself.

**Required variables:** `postgres_image`, `redis_image`, `nextcloud_image`, `postgres_path`, `nextcloud_path`, `nextcloud_disk`, `postgres_admin_user`, `postgres_admin_password`, `nextcloud_database_name`, `nextcloud_db_user`, `nextcloud_db_password`, `nextcloud_admin_user`, `nextcloud_admin_password`, `nextcloud_trusted_domains`, `secret_env_dir`

**Templates:** `postgres_container.sh.j2`, `postgres_container.service.j2`, `redis_container.sh.j2`, `redis_container.service.j2`, `nextcloud_container.sh.j2`, `nextcloud_container.service.j2`, `postgres.env.j2`, `nextcloud.env.j2`

**Key behavior:** owns the shared database layer for Nextcloud, Paperless, and Semaphore, and must run before those consumers.

---

### `paperless_ngx`

Deploys Paperless NGX on top of the PostgreSQL and Redis containers created by `nextcloud`.

**Required variables:** `paperless_path`, `paperless_data_path`, `paperless_media_path`, `paperless_export_path`, `paperless_consume_path`, `paperless_database_name`, `paperless_db_user`, `paperless_db_password`, `paperless_image`, `secret_env_dir`

**Templates:** `paperless_ngx.sh.j2`, `paperless_ngx.service.j2`, `paperless.env.j2`

---

### `navidrome`

Deploys Navidrome with an explicit non-root runtime user and a local backup workflow.

**Required variables:** `navidrome_path`, `navidrome_backup_location`, `navidrome_uid`, `navidrome_gid`, `navidrome_image`

**Key behavior:** either bind-mounts `navidrome_local_music_path` or falls back to the role's own music path.

---

### `vaultwarden`

Deploys Vaultwarden and its SQLite-backed backup workflow.

**Required variables:** `vaultwarden_path`, `vaultwarden_backup_location`, `vaultwarden_signups_allowed`, `vaultwarden_image`

**Templates:** `vaultwarden.sh.j2`, `vaultwarden.service.j2`, `backup_db.j2`

---

### `semaphore`

Deploys Semaphore and backs up its PostgreSQL database into the local Nextcloud data tree when `backup_local: true`.

**Required variables:** `semaphore_database_name`, `semaphore_db_user`, `semaphore_db_password`, `semaphore_admin_name`, `semaphore_admin_email`, `semaphore_admin_password`, `semaphore_encryption_key`, `semaphore_known_hosts`, `semaphore_backup_location`, `semaphore_image`, `secret_env_dir`

**Templates:** `semaphore.sh.j2`, `semaphore.service.j2`, `semaphore.env.j2`, `backup_semaphore.sh.j2`, `ssh_known_hosts.j2`

---

### `backup`

Manages the local Borg backup disk and the daily backup scripts for VM1.

**Required variables:** `nextcloud_borg_backup_path`, `nextcloud_paperless_backup_location`, `borg_backup_path`, `backup_disk`, `backup_host`, `backup_local`

**Templates:** `init_backup_repo.sh.j2`, `backup_files.sh.j2`

**Key behavior:** initializes the Borg repo if needed, mounts the backup disk, and keeps the VM1 backup workflow local-first.

---

### `ansible`

Installs the host-side Ansible runtime and supporting dependencies used by Semaphore-triggered jobs on VM1.

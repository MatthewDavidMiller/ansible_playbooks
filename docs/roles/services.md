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

**Required variables:** `traefik_path`, `traefik_egress_network`, `traefik_dashboard_fqdn`, `traefik_dashboard_basic_auth_users`, `traefik_acme_email`, `proxy_config`, `container_service_names`, `management_network`, `ip_ansible`, `secret_env_dir`, `traefik_image`

**Templates:** `traefik_container.sh.j2`, `traefik_container.service.j2`, `traefik.yml.j2`, `tls.yml.j2`, `security.yml.j2`, `dashboard.yml.j2`, `service_proxy.yml.j2`, `traefik.env.j2`

**Key behavior:** publishes ports 80 and 443, requests per-FQDN certificates through Porkbun DNS-01, protects the dashboard with both management-source allowlisting and BasicAuth, renders dynamic route files from `proxy_config`, derives Traefik app-network membership from route-owned `proxy_network` values, pins Traefik to its `route_proxy_traefik_ips` address on every route network so Podman cannot allocate it the address the service container requests, queues legacy non-internal or wrong-subnet route networks for deferred replacement during staged VM1 runs, and runs only against pre-pulled approved digest refs.

---

### `nextcloud`

Deploys the shared PostgreSQL container, Redis container, and Nextcloud itself.

**Required variables:** `postgres_image`, `redis_image`, `nextcloud_image`, `postgres_path`, `nextcloud_path`, `nextcloud_disk`, `postgres_admin_user`, `postgres_admin_password`, `nextcloud_database_name`, `nextcloud_db_user`, `nextcloud_db_password`, `nextcloud_admin_user`, `nextcloud_admin_password`, `nextcloud_trusted_domains`, `secret_env_dir`

**Optional variables:** `password_minimum_length` defaults to `16` and controls validation of the PostgreSQL admin and Nextcloud database passwords.

**Templates:** `postgres_container.sh.j2`, `postgres_container.service.j2`, `redis_container.sh.j2`, `redis_container.service.j2`, `nextcloud_container.sh.j2`, `nextcloud_container.service.j2`, `nextcloud_configure.sh.j2`, `nextcloud_configure.service.j2`, `postgres.env.j2`, `nextcloud.env.j2`

**Key behavior:** owns the shared database layer for Nextcloud, Paperless, and Semaphore, creates missing internal backend/proxy networks, queues legacy non-internal or wrong-subnet Nextcloud networks for deferred replacement during staged VM1 runs, normalizes directory and file modes in one walk of each configured user files tree, reconciles persistent `config.php` values after Nextcloud starts, and must run before those consumers.

---

### `paperless_ngx`

Deploys Paperless NGX on top of the PostgreSQL and Redis containers created by `nextcloud`.

**Required variables:** `paperless_path`, `paperless_data_path`, `paperless_media_path`, `paperless_export_path`, `paperless_consume_path`, `paperless_database_name`, `paperless_db_user`, `paperless_db_password`, `paperless_image`, `secret_env_dir`

**Optional variables:** `password_minimum_length` defaults to `16` and controls validation of the Paperless database password.

**Templates:** `paperless_ngx.sh.j2`, `paperless_ngx.service.j2`, `paperless.env.j2`

**Key behavior:** creates the Paperless proxy network as internal, queues legacy non-internal or wrong-subnet proxy networks for deferred replacement during staged VM1 runs, and runs only after the shared database/cache containers are configured.

---

### `navidrome`

Deploys Navidrome with an explicit non-root runtime user and a local backup workflow.

**Required variables:** `navidrome_path`, `navidrome_backup_location`, `navidrome_uid`, `navidrome_gid`, `navidrome_image`

**Key behavior:** creates the Navidrome proxy network as internal, queues legacy non-internal or wrong-subnet proxy networks for deferred replacement during staged VM1 runs, and either bind-mounts `navidrome_local_music_path` or falls back to the role's own music path. With `backup_local: true` the daily backup installs the SQLite dumps into the Nextcloud data tree and then re-indexes them; see [Indexing local backups into Nextcloud](#indexing-local-backups-into-nextcloud).

---

### `vaultwarden`

Deploys Vaultwarden and its SQLite-backed backup workflow.

**Required variables:** `vaultwarden_path`, `vaultwarden_backup_location`, `vaultwarden_signups_allowed`, `vaultwarden_image`

**Templates:** `vaultwarden.sh.j2`, `vaultwarden.service.j2`, `backup_db.j2`

**Key behavior:** keeps public signup disabled, creates the Vaultwarden proxy network as internal, and queues legacy non-internal or wrong-subnet proxy networks for deferred replacement during staged VM1 runs. With `backup_local: true` the daily backup installs the SQLite copy into the Nextcloud data tree and then re-indexes it; see [Indexing local backups into Nextcloud](#indexing-local-backups-into-nextcloud).

---

### `semaphore`

Deploys Semaphore and backs up its PostgreSQL database into the local Nextcloud data tree when `backup_local: true`.

**Required variables:** `semaphore_database_name`, `semaphore_db_user`, `semaphore_db_password`, `semaphore_admin_name`, `semaphore_admin_email`, `semaphore_admin_password`, `semaphore_encryption_key` (at least 32 characters), `semaphore_known_hosts`, `semaphore_backup_location`, `semaphore_image`, `secret_env_dir`

**Templates:** `semaphore.sh.j2`, `semaphore.service.j2`, `semaphore.env.j2`, `backup_semaphore.sh.j2`, `ssh_known_hosts.j2`, `migrate_container_networks.sh.j2`

**Key behavior:** creates the Semaphore proxy and egress networks, queues legacy non-internal or wrong-subnet Semaphore proxy networks for deferred replacement during staged VM1 runs, and runs last in `vm1.yml` so it can schedule the delayed container-network migration after all service configuration has been rendered. The migration job stops Traefik and the configured `container_service_names`, replaces queued networks as internal networks, restarts services, and logs to `/var/log/homelab-container-network-migration.log`.

---

### `backup`

Manages the local Borg backup disk and the daily backup scripts for VM1.

**Required variables:** `nextcloud_borg_backup_path`, `nextcloud_paperless_backup_location`, `borg_backup_path`, `backup_disk`, `backup_host`, `backup_local`

**Templates:** `init_backup_repo.sh.j2`, `backup_files.sh.j2`

**Key behavior:** initializes the Borg repo if needed, mounts the backup disk, and keeps the VM1 backup workflow local-first. Remote (`backup_local: false`) runs unmount the SSHFS mount with `fusermount3`, since Rocky 10 ships FUSE 3 only.

---

### Indexing local backups into Nextcloud

With `backup_local: true`, the `navidrome`, `vaultwarden`, and `semaphore` backup scripts write their dumps directly into `{{ nextcloud_path }}/data/<nextcloud_homelab_user>/files/...` as `nextcloud_uid:nextcloud_gid`. A file placed there is invisible to Nextcloud clients until it is added to the file cache, so each script finishes with `occ files:scan --path=...`.

`occ` refuses to run as root — it must run as the owner of `config/config.php` — so the scan must be invoked as `podman exec --user {{ nextcloud_uid }}:{{ nextcloud_gid }} nextcloud php occ`, the same form used by `nextcloud_configure.sh`. A scan failure is logged to the service's backup log and does not fail the run, because the dump itself is already safely on disk.

Dumps are installed with `nextcloud_user_files_directory_mode` and `nextcloud_user_files_file_mode` rather than literal modes. The `nextcloud` role normalizes every file under `data/<user>/files` to those modes on each run, so a script that writes a different mode leaves each backup wrong until the next playbook run silently corrects it. For the same reason the per-service "Repair … ownership" tasks set ownership only: a recursive `mode` would also rewrite the backup files themselves.

Both properties are covered by `tests/test_ansible_regressions.py` and by the rendered-script assertions in `scripts/test_shell_secret_env.sh`.

---

### `ansible`

Installs the host-side Ansible runtime and supporting dependencies used by Semaphore-triggered jobs on VM1.

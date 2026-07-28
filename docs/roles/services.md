# Service Roles Reference

These are the maintained service roles used by `vm1.yml`. Historical service roles are preserved on the branch described in [archive.md](../archive.md).

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

**Key behavior:** owns the shared database layer for Nextcloud, Paperless, and Semaphore, reconciles its internal backend and proxy networks through the shared [`container_network`](standard.md#container_network) role, normalizes directory and file modes in one walk of each configured user files tree, reporting only how many files that walk fixed, keeps the `container_file_t` file context rule for its mounted volume so host-written backups are labeled correctly at creation, reconciles persistent `config.php` values after Nextcloud starts, and must run before those consumers.

---

### `paperless_ngx`

Deploys Paperless NGX on top of the PostgreSQL and Redis containers created by `nextcloud`.

**Required variables:** `paperless_path`, `paperless_data_path`, `paperless_media_path`, `paperless_export_path`, `paperless_consume_path`, `paperless_database_name`, `paperless_db_user`, `paperless_db_password`, `paperless_secret_key`, `paperless_image`, `secret_env_dir`

**Optional variables:** `password_minimum_length` defaults to `16` and controls validation of the Paperless database password. `secret_key_minimum_length` defaults to `32` and controls validation of `paperless_secret_key`.

**Templates:** `paperless_ngx.sh.j2`, `paperless_ngx.service.j2`, `paperless.env.j2`

**Key behavior:** reconciles the Paperless proxy network through the shared [`container_network`](standard.md#container_network) role, and runs only after the shared database/cache containers are configured.

**Paperless 3.0 configuration notes:** `PAPERLESS_SECRET_KEY` has no built-in default in 3.0, so the container exits at startup unless `paperless_secret_key` is set. `PAPERLESS_DBENGINE` is rendered as `postgresql` because 3.0 requires PostgreSQL and MariaDB users to declare the engine explicitly instead of inferring it from `PAPERLESS_DBHOST`. `PAPERLESS_TRUSTED_PROXIES` names the single Traefik hop on `paperless_proxy_net` so allauth rate limiting reads the real client IP from `X-Forwarded-For` rather than a spoofable value. The 3.0 upgrade also rebuilds the full-text index (Whoosh to Tantivy) on first start and clears task history; both are automatic and need no configuration.

---

### `navidrome`

Deploys Navidrome with an explicit non-root runtime user and a local backup workflow.

**Required variables:** `navidrome_path`, `navidrome_backup_location`, `navidrome_uid`, `navidrome_gid`, `navidrome_image`

**Key behavior:** reconciles the Navidrome proxy network through the shared [`container_network`](standard.md#container_network) role, and either bind-mounts `navidrome_local_music_path` or falls back to the role's own music path. With `backup_local: true` the daily backup installs the SQLite dumps into the Nextcloud data tree and then re-indexes them; see [Indexing local backups into Nextcloud](#indexing-local-backups-into-nextcloud).

---

### `vaultwarden`

Deploys Vaultwarden and its SQLite-backed backup workflow.

**Required variables:** `vaultwarden_path`, `vaultwarden_backup_location`, `vaultwarden_signups_allowed`, `vaultwarden_image`

**Templates:** `vaultwarden.sh.j2`, `vaultwarden.service.j2`, `backup_db.j2`

**Key behavior:** keeps public signup disabled, and reconciles the Vaultwarden proxy network through the shared [`container_network`](standard.md#container_network) role. With `backup_local: true` the daily backup installs the SQLite copy into the Nextcloud data tree and then re-indexes it; see [Indexing local backups into Nextcloud](#indexing-local-backups-into-nextcloud).

---

### `semaphore`

Deploys Semaphore and backs up its PostgreSQL database into the local Nextcloud data tree when `backup_local: true`.

**Required variables:** `semaphore_database_name`, `semaphore_db_user`, `semaphore_db_password`, `semaphore_admin_name`, `semaphore_admin_email`, `semaphore_admin_password`, `semaphore_encryption_key` (at least 32 characters), `semaphore_known_hosts`, `semaphore_backup_location`, `semaphore_image`, `secret_env_dir`

**Templates:** `semaphore.sh.j2`, `semaphore.service.j2`, `semaphore.env.j2`, `backup_semaphore.sh.j2`, `ssh_known_hosts.j2`

**Key behavior:** reconciles the Semaphore proxy and egress networks through the shared [`container_network`](standard.md#container_network) role. The final [`container_network_migration`](standard.md#container_network_migration) role owns cross-service scheduling and recovery.

---

### `backup`

Manages the local Borg backup disk and the daily backup scripts for VM1.

**Required variables:** `nextcloud_borg_backup_path`, `nextcloud_paperless_backup_location`, `borg_backup_path`, `backup_disk`, `backup_host`, `backup_local`

**Templates:** `init_backup_repo.sh.j2`, `backup_files.sh.j2`

**Key behavior:** initializes the Borg repo if needed, mounts the backup disk, and keeps the VM1 backup workflow local-first. Remote (`backup_local: false`) runs unmount the SSHFS mount with `fusermount3`, since Rocky 10 ships FUSE 3 only.

---

### Indexing local backups into Nextcloud

With `backup_local: true`, the `navidrome`, `vaultwarden`, and `semaphore` backup scripts write their dumps directly into `{{ nextcloud_path }}/data/<nextcloud_homelab_user>/files/...` as `nextcloud_uid:nextcloud_gid`. A file placed there is invisible to Nextcloud clients until it is added to the file cache, so each script passes its destination to `/usr/local/bin/nextcloud_scan_path.sh`.

Ownership and mode are not sufficient on their own. Podman's `:Z` relabel only covers what exists when the container starts, so a dump the host writes from cron afterwards takes the policy default for that path, `default_t`, which the container is denied `getattr` on. `occ files:scan` then reports `Error during scan: stat(): stat failed`, skips the file, and still exits zero. The `nextcloud` role therefore carries a persistent `container_file_t` rule for `nextcloud_path`, so every host-written backup is labeled correctly when it is created; see [SELinux](../architecture.md#selinux).

The `nextcloud` role owns that helper so every service uses the same `occ files:scan` invocation. It uses an explicit working directory and absolute `occ` path and runs as `nextcloud_uid:nextcloud_gid`.

Every caller is a cron job, so the helper cannot inherit anything from its environment. It exports its own `PATH`, `HOME`, and `LC_ALL`, calls every binary through an absolute path, and reads `/dev/null` for stdin instead of relying on a terminal.

The helper runs in these stages:

1. **Reject an unusable request.** `occ` resolves `--path` against the global root, where each account is mounted at `/<user id>/`, and it reports a bad account without failing. A path that is not `<user>/files/<path>` — the shape an empty `nextcloud_homelab_user` renders — is refused up front, as is a path that does not exist under `nextcloud_path/data`.
2. **Serialize.** All local service backups run `@daily` and can reach `files:scan` at the same time, so scans take a `flock` on `/run/lock/nextcloud-files-scan.lock`.
3. **Wait for a usable instance.** `podman container exists` is also true for a created or stopped container, so the helper waits until `occ status` answers and reports neither maintenance nor a pending database upgrade. The daily backups can start while the container is still restarting after a reboot or an image update, and `occ` still answers `status` in maintenance mode while refusing to load the commands a scan needs.
4. **Scan, then confirm.** `files:scan` can print an unknown user, lock contention, a maintenance notice, or a scan exception while still exiting zero, so the helper checks the output text as well as the process status. It also fails on `Error during scan`, which reports one unreadable file, skips it, and lets the command exit zero — the way a backup goes unindexed while the cron job reports success. The same failures are counted in the summary table, so the helper reads the `Errors` column too, locating it by its header so a future table layout cannot shift the count. Because the command can additionally exit zero without indexing anything, a successful scan is confirmed with `occ info:file` before the helper reports success. If a future image drops `info:file`, the confirmation is skipped rather than failing a backup that is already on disk.

Every `occ` call runs under `timeout`, so a hung command is killed instead of holding the shared lock and the cron job all night. After the retry budget is exhausted, the helper returns failure and the calling service records the failure in its backup log. The service backup remains non-fatal because the dump itself is already safely on disk.

Navidrome prunes its destination on the same schedule, so it scans after pruning: one scan then indexes both the new dump and the removals, instead of leaving deleted backups in the file cache until the next full scan.

Dumps are installed with `nextcloud_user_files_directory_mode` and `nextcloud_user_files_file_mode` rather than literal modes. The `nextcloud` role normalizes every file under `data/<user>/files` to those modes on each run, so a script that writes a different mode leaves each backup wrong until the next playbook run silently corrects it. For the same reason the per-service "Repair … ownership" tasks set ownership only: a recursive `mode` would also rewrite the backup files themselves.

The scan-helper and file-mode properties are covered by `tests/test_ansible_regressions.py` and by the rendered-script assertions in `scripts/test_shell_secret_env.sh`.

---

### `ansible`

Installs the host-side Ansible runtime and supporting dependencies used by Semaphore-triggered jobs on VM1.

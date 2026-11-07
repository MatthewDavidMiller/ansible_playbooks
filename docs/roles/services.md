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

**Required variables:** `traefik_dashboard_fqdn`, `traefik_dashboard_basic_auth_users`, `traefik_acme_email`, `homelab_internal_domain`, `proxy_config` (from `network/vm1.yml`), `container_service_names`, `management_network`, `ip_ansible`, `secret_env_dir`, `traefik_image`

**Templates:** `traefik_container.sh.j2`, `traefik_container.service.j2`, `traefik.yml.j2`, `tls.yml.j2`, `security.yml.j2`, `dashboard.yml.j2`, `service_proxy.yml.j2`, `traefik.env.j2`

**Key behavior:** publishes ports 80 and 443, requests per-FQDN certificates through Porkbun DNS-01, protects the dashboard with both management-source allowlisting and BasicAuth, renders dynamic route files from `proxy_config`, derives Traefik app-network membership from route-owned `proxy_network` values, pins Traefik to its `route_proxy_traefik_ips` address on every route network so Podman cannot allocate it the address the service container requests, queues legacy non-internal or wrong-subnet route networks for deferred replacement during staged VM1 runs, and runs only against pre-pulled approved digest refs.

---

### `vaultwarden`

Deploys Vaultwarden and its SQLite-backed backup workflow.

**Required variables:** `vaultwarden_backup_location`, `vaultwarden_image`

**Templates:** `vaultwarden.sh.j2`, `vaultwarden.service.j2`, `backup_db.j2`

**Key behavior:** keeps public signup disabled, and reconciles the Vaultwarden proxy network through the shared [`container_network`](standard.md#container_network) role. The daily backup stores the SQLite copy in homedrive through `homedrive_import_path.sh`, so the role needs homedrive deployed and `homedrive_backup_user` set to one of its accounts.

---

### `playbook_runner`

Deploys [playbook-runner](https://github.com/MatthewDavidMiller/playbook-runner), a first-party web interface that runs and schedules playbooks from this repository. `vm1.yml` enables the role (`playbook_runner_enabled`). It refuses an empty `playbook_runner_image`, so the image must have a reviewed entry in `artifacts/containers.lock.yml` (it does, as a [first-party image](../guides/container-image-updates.md#first-party-images)). See [guides/playbook-runner-migration.md](../guides/playbook-runner-migration.md).

**Required variables (when enabled):** `playbook_runner_master_key` (64 hex digits), `playbook_runner_backup_location`, `playbook_runner_image`, `secret_env_dir`

**Templates:** `playbook_runner.sh.j2`, `playbook_runner.service.j2`, `backup_playbook_runner.sh.j2`

**Key behavior:** the master key and optional first admin password are rendered to root-only files under `secret_env_dir` and turned into Podman secrets mounted read-only for the container user (uid 10001); the key never appears in an environment variable or the launch script. The runner keeps no database: everything in its data directory (secrets, inventories, records, run records, run logs, and the admin password hash) is AES-256-GCM sealed with the master key, so the daily backup, which archives it into the Nextcloud tree (or rclone), holds only ciphertext. Runs execute in a noexec tmpfs, and memory is capped without swap. The container joins only its proxy network and a dedicated egress network for git and SSH, never the backend network. Its proxy network is in `reverse_proxy_deferred_route_networks`, because the runner may be the container running the playbook. An optional `playbook_runner_known_hosts` seeds the managed known_hosts file once; after that it is edited in the interface. Collections are built into the runner image, never downloaded at run time: before each run the runner resolves this repository's `collections/requirements.yml` against them offline and fails the run on a mismatch. So a change to `collections/requirements.yml` needs a matching update to `runtime/collections.yml` in playbook-runner, a new release, and a new pin here.

---

### `music_server`

Deploys [music-server](https://github.com/MatthewDavidMiller/music-server), the first-party Subsonic music server. `vm1.yml` enables the role once `artifacts/containers.lock.yml` has a reviewed `music_server` digest. See [guides/music-server-migration.md](../guides/music-server-migration.md).

**Required variables (when enabled):** `music_server_music_path`, `music_server_master_key` (64 hex digits), `music_server_users`, `music_server_backup_location`, `music_server_image`, `secret_env_dir`

**Templates:** `music_server.sh.j2`, `music_server.service.j2`, `backup_music_server.sh.j2`

**Key behavior:** the master key and the users file (every account's password) are rendered to root-only files under `secret_env_dir` and turned into Podman secrets mounted read-only for the container user (uid 10001). Neither appears in an environment variable or the launch script. The server reads the users file at startup and keeps the passwords in memory only; the roster and each user's playlists, stars, and plays are AES-256-GCM sealed in `data/`, which the daily backup archives (`cache/` is rebuildable and skipped). A changed users file or key restarts the service on non-staged runs. The music is mounted read-only and readable through `--group-add {{ music_server_music_gid }}`, and the unit waits for it after Nextcloud. The container joins only its internal route network: it needs no egress. Set `proxy_access_log: false` on its route; Subsonic apps send credentials in the query string.

---

### `backup`

Mounts the backup disk and makes sure the local Borg repository on it exists. homedrive's store backup (`backup_homedrive.sh`) writes its `homedrive-*` archives into it.

**Required variables:** `backup_disk`

**Templates:** `init_backup_repo.sh.j2`

**Key behavior:** initializes the Borg repo if needed and mounts the backup disk. The older `nextcloud_backup-*` archives in the repository are no longer pruned by anything; delete them by hand when they are no longer wanted.

---

### `ansible`

Installs the host-side Ansible runtime and supporting dependencies used by playbook-runner jobs on VM1.

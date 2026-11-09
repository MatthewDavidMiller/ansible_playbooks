# Variables

This document lists the inventory variables used by the maintained `vm1.yml`
playbook. Create a gitignored `inventory.yml` and define every variable
required for the hosts you intend to manage.

`Required` means that the maintained playbook needs a real value. `Conditional`
means that the variable is required only when the described feature is enabled.
Variables with a default may be omitted unless the default does not fit the
environment. Paths must be absolute. CIDRs must not be `0.0.0.0/0`.

Do not commit passwords, API keys, encryption keys, or app passwords. Store a
real inventory containing secrets outside the repository or encrypt it with
Ansible Vault.

## Shared inventory variables

Define these under `all.vars`, `homelab.vars`, or on each applicable host.

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `ansible_host` | string | Yes, per host | Address Ansible uses to connect to `vm1`. | `192.168.1.120` |
| `user_name` | string | Yes | Existing non-root login and script owner. The playbooks add it to the SSH allowlist. | `example_user` |
| `default_interface` | string | No | Host interface assigned to the public firewalld zone. | `eth0` (default) |
| `management_network` | list | Yes | Trusted management IPv4 CIDRs. | `["192.168.1.0/24"]` |
| `ip_ansible` | string | Yes | Ansible controller address in IPv4 CIDR notation. | `192.168.1.10/32` |
| `ansible_become` | boolean | Yes | Enables privilege escalation; the playbooks set no play-level `become`. | `true` |
| `ansible_become_method` | string | No | Privilege-escalation method. | `sudo` |
| `secret_env_dir` | path | No | Root-only directory for rendered service environment files. | `/etc/homelab/secrets` |

Standard Ansible connection variables such as `ansible_user`,
`ansible_port`, and `ansible_ssh_private_key_file` may also be set when the
environment cannot use Ansible's normal SSH defaults.

## VM1 required variables

VM1 runs the service stack. All variables in this section need real values for
`vm1.yml` unless marked conditional.

### DNS and Traefik

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `homelab_domain` | string | Yes | Porkbun-managed base domain used by dynamic DNS. | `example.com` |
| `homelab_subdomain` | string | Yes | Record below `homelab_domain` updated with the WAN address. | `home` |
| `porkbun_api_key` | string | Yes, secret | Porkbun API key used by DDNS and ACME DNS-01. | Ansible Vault value |
| `porkbun_api_key_secret` | string | Yes, secret | Porkbun API secret. | Ansible Vault value |
| `traefik_path` | path | No | Traefik configuration and data root. | `/traefik` (default) |
| `traefik_dashboard_fqdn` | string | Yes | Unique dashboard hostname. | `traefik.example.com` |
| `traefik_dashboard_basic_auth_users` | list | Yes, secret | One or more `user:htpasswd-hash` entries. | `["admin:$apr1$..."]` |
| `traefik_acme_email` | string | Yes | ACME account email address. | `admin@example.com` |
| `homelab_internal_domain` | string | Yes | Internal DNS domain the Traefik routes sit under; VM1's routes are `<service>.<this domain>` (`vaultwarden`, `playbook-runner`, `music`, `drive`). | `example.lan` |
| `proxy_config` | list | Set by `network/vm1.yml` | Dynamic routes; see [Proxy entries](#proxy-entries). VM1's list lives in `network/vm1.yml`, which outranks inventory. | One entry per exposed service |
| `container_service_names` | string | Set by `vm1.yml` | Space-separated systemd service order used by Traefik and deferred network migration. `vm1.yml` builds it, adding `playbook_runner` and `music_server` only when their roles are enabled; an inventory value is ignored. | `vaultwarden playbook_runner homedrive` |
| `container_network_migration_delay` | string | No | Positive systemd time span before a queued network migration starts. | `2min` |
| `traefik_egress_network` | string | No | Dedicated non-internal Traefik egress network. | `traefik_egress_net` |

Generate a dashboard password hash with `htpasswd`; quote the complete value in
YAML so its dollar signs are preserved.

### Data disk and backup disk

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `data_disk` | string | Yes | Data disk filesystem device identifier, mounted by the `data_disk` role. It holds homedrive's store and exports. | `UUID=example-uuid` |
| `data_disk_mount_path` | path | No | Data disk mount point. | `/data_drive` (default) |
| `backup_disk` | string | Yes | Host backup filesystem device identifier. | `UUID=example-backup-uuid` |
| `borg_backup_path` | path | No | Mount point and Borg repository root for the host backup disk. homedrive's store backup writes here. | `/borg_backups` (default) |

### rclone/WebDAV

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `homedrive_rclone_pass` | string | Yes once homedrive is deployed, secret | A device token from homedrive's Devices page for the `Homedrive:` rclone remote, as `rclone obscure <token>` prints it. The remote is written only once this is set. | Ansible Vault value |
| `homedrive_webdav_url` | string | No | WebDAV URL for that remote. | `https://drive.<homelab_internal_domain>/dav/<homedrive_rclone_user>` when homedrive is deployed |
| `homedrive_rclone_user` | string | No | homedrive account for that remote. | `homedrive_backup_user` |

### Backups

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `homedrive_main_user` | string | Yes | The homedrive account, one of `homedrive_users`, that the services' backups, the Music export and the rclone remote use unless set separately. | `example_user` |
| `homedrive_backup_user` | string | No | The homedrive account whose drive holds the vaultwarden, playbook-runner and music-server backups. Each `<service>_backup_location` is the folder in it. The backups keep their dated names, and the old playbook-runner and music-server files (over 30 days) go to the drive's trash through `homedrive_prune_path.sh`. Vaultwarden keeps every day. | `homedrive_main_user` |

The three service backups need homedrive deployed (`homedrive_deploy`); their roles refuse to run without it.


### playbook-runner

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `playbook_runner_enabled` | boolean | Set by `vm1.yml` | Deploy playbook-runner. `vm1.yml` sets it to `true` as a play variable, so it cannot be overridden from inventory. | `true` on VM1 |
| `playbook_runner_path` | path | No | Host data directory (owned by uid 10001, mode 0700). | `/playbook-runner` (default) |
| `playbook_runner_master_key` | string | Yes, secret | 64 hex digits from `playbook-runner gen-key`. Also keep a copy in Vaultwarden: the stored secrets cannot be recovered without it. | Ansible Vault value |
| `playbook_runner_admin_password` | string | No, secret | Initial admin password, 12-128 characters. Empty means a one-time setup token is logged instead. | `""` |
| `playbook_runner_backup_location` | string | Yes | The folder in `homedrive_backup_user`'s drive that holds the backups (a legacy `Nextcloud:` prefix is ignored). | `playbook_runner_backup` |
| `playbook_runner_known_hosts` | string | No | `known_hosts` entries written once when the runner's file does not exist yet. | `host ssh-ed25519 AAAA...` |
| `playbook_runner_timezone` | string | No | Zone schedules use and times are shown in. | `America/New_York` |
| `playbook_runner_keep_runs` | integer | No | Finished runs kept. | `500` |
| `playbook_runner_egress_network` | string | No | Dedicated non-backend outbound git/SSH network. | `playbook_runner_egress_net` |

### music-server

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `music_server_enabled` | boolean | Set by `vm1.yml` | Deploy music-server. `vm1.yml` sets it to true once `artifacts/containers.lock.yml` has a reviewed `music_server` digest. | derived |
| `music_server_path` | path | No | Host directory holding `data/` (sealed, backed up) and `cache/` (rebuildable). | `/music_server` (default) |
| `music_server_library` | string | No | Where the library comes from: `homedrive` (homedrive's read-only Music export) whenever homedrive is deployed, otherwise `path` (`music_server_music_path`). Tracks are identified by their path in the library, which the export keeps, so playlists and stars carry across. | `homedrive` once homedrive is deployed |
| `music_server_homedrive_library` | path | No | homedrive's Music export. | `<homedrive_export_path>/music` |
| `music_server_music_path` | path | When `music_server_library` is `path` | The library folder, mounted read-only. | `/path/to/music` |
| `music_server_master_key` | string | Yes, secret | 64 hex digits from `music-server gen-key`. Keep a copy in Vaultwarden. | Ansible Vault value |
| `music_server_users` | list | Yes, secret | Accounts: `{name, password, admin}`. 1-50 entries, unique names of `A-Z a-z 0-9 . _ -`, 8-128 character passwords, at least one admin. A removed name is disabled with its data kept. | Ansible Vault value |
| `music_server_backup_location` | string | Yes | The folder in `homedrive_backup_user`'s drive that holds the backups (a legacy `Nextcloud:` prefix is ignored). | `music_server_backup` |
| `music_server_scan_interval_minutes` | integer | No | Library rescan interval; `0` scans only at startup. | `60` |
| `music_server_max_transcodes` | integer | No | Concurrent ffmpeg transcodes (0-8). | `2` |
| `music_server_memory` | string | No | Container memory ceiling, without swap. | `512m` |
| `music_server_music_gid` | string | No | Supplementary group that can read the music when `music_server_library` is `path`. | `33` |

### Vaultwarden

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `vaultwarden_path` | path | No | Vaultwarden data root. | `/vaultwarden` (default) |
| `vaultwarden_backup_location` | string | Yes | The folder in `homedrive_backup_user`'s drive that holds the backups (a legacy `Nextcloud:` prefix is ignored). | `vaultwarden_backup` |
| `vaultwarden_signups_allowed` | boolean | No | Must remain `false`; the role rejects public signup. | `false` |

## Network maps

VM1's container address plan lives in [`network/vm1.yml`](../network/vm1.yml),
which `vm1.yml` loads with `vars_files`. That outranks inventory, so these
dictionaries are not set in inventory at all; an inventory copy is ignored and
can be deleted. To change an address, edit the plan file and keep each
network's subnet, service address, and Traefik address consistent;
`tests/test_ansible_regressions.py` checks that they are.

| Variable | Type | Required | Description |
|---|---|---|---|
| `route_proxy_network_subnets` | dictionary | Set by `network/vm1.yml` | Internal subnet keyed by each route network. |
| `route_proxy_container_ips` | dictionary | Set by `network/vm1.yml` | Backend address keyed by route network for Traefik `/etc/hosts`. |
| `route_proxy_traefik_ips` | dictionary | Set by `network/vm1.yml` | Address Traefik claims on each route network; must differ from `route_proxy_container_ips`. |
| `container_static_ips` | dictionary | Set by `network/vm1.yml` | Static address keyed by container alias. |
| `container_dns` | dictionary | Set by `network/vm1.yml` | Podman DNS domain plus logical alias map. |
| `reverse_proxy_deferred_route_networks` | list | No | Route networks whose replacement is deferred to their owning role; default is `playbook_runner_container_net`. |

### Proxy entries

Every item in `proxy_config` accepts these fields:

| Field | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `name` | string | Yes | Unique router/service name. | `vaultwarden` |
| `proxy_fqdn` | string | Yes | Unique `Host()` match, different from the dashboard FQDN. | `vaultwarden.example.com` |
| `proxy_upstream_protocol` | string | Yes | Upstream scheme: `http` or `https`. | `http` |
| `proxy_upstream_port` | string | Yes | Port from `1` through `65535`. | `80` |
| `container_destination` | string | Yes | Podman DNS name visible on `proxy_network`. | `vaultwarden-proxy.dns.podman` |
| `proxy_network` | string | Yes | Route network present in `route_proxy_container_ips`. | `vaultwarden_container_net` |
| `proxy_allow_encoded_slash` | boolean | No | Enables encoded-slash forwarding. | `false` |
| `proxy_management_only` | boolean | No | Restricts the route to `management_network`. | `false` |

## Optional shared role overrides

These variables have working defaults and normally do not belong in inventory.
They are listed here so every maintained role input is discoverable.

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `patching_minute` | string | `0` | Cron minute for the patching job. |
| `patching_hour` | string | `0` | Cron hour. |
| `patching_weekday` | string | `0` | Cron weekday. |
| `patching_month` | string | `*` | Cron month. |
| `standard_cleanup_prune_podman_images` | boolean | `false` | Opts into pruning unused images. |
| `standard_cleanup_prune_podman_containers` | boolean | `false` | Opts into pruning stopped containers. |
| `standard_selinux_extra_booleans` | list | `[]` | Extra `{name, state}` SELinux booleans. |
| `standard_selinux_extra_fcontexts` | list | `[]` | Extra SELinux file-context rules. |
| `standard_ssh_allow_users` | list | set by playbooks | sshd account allowlist. |
| `standard_ssh_allow_tcp_forwarding` | boolean | `false` | Compatibility toggle used when the explicit mode is not set. |
| `standard_ssh_tcp_forwarding_mode` | string | `no` | TCP forwarding mode: `no`, `local`, `remote`, or `yes`. |
| `standard_ssh_allow_agent_forwarding` | boolean | `false` | Enables SSH agent forwarding. |
| `standard_ssh_streamlocal_forwarding_mode` | string | `no` | Unix-socket forwarding mode. |
| `standard_ssh_max_sessions` | integer | `2` | Maximum SSH sessions per connection, from `1` through `100`. |
| `standard_update_apply_full_updates` | boolean | `true` | Applies every available package update on each run; set `false` to skip patching for a one-off run. |
| `standard_update_enable_epel` | boolean | `true` | Enables EPEL and CRB. |
| `<job>_backup_hour`, `<job>_backup_minute` | string | see the next column | When each nightly job runs, VM1's local time: `vaultwarden_backup_*`, `playbook_runner_backup_*` and `music_server_backup_*` at `0`:`0`, `homedrive_backup_*` at `1`:`30`. The store's backup must come after the jobs that store into it. |
| `homedrive_import_accepted` | multi-line string | No | Reviewed differences for `homedrive_import.yml`'s checks: lines of `<sha256>  <path>`, the path under the source and the SHA-256 of the source content that was reviewed. Inventory only: it names files. Needs homedrive 0.1.8. | empty (default) |
| `homedrive_prune_keep` | integer | `7` | How many of a folder's newest dated backups `homedrive_prune_path.sh` always keeps, however old. |

`apply_runtime_changes_on_reboot`, `approved_container_images`,
`traefik_image`, `vaultwarden_image`, `playbook_runner_image`, `music_server_image`,
and `standard_ssh_allow_users` are assembled by the maintained playbooks.
Container image values come from `artifacts/containers.lock.yml`; do not
override them in inventory.

## Standalone playbook variable

`standalone_tasks/generate_ssh_key.yml` is outside the maintained VM1
orchestration. When running it, define `user_name` and `key_name`; `key_name` is
the filename created below `/home/{{ user_name }}` (for example,
`id_ansible_ed25519`).

## Obsolete variables

The Nextcloud, Paperless NGX, PostgreSQL and Redis variables (`nextcloud_*`,
`paperless_*`, `postgres_*`, `redis_*`, `backup_local`, `backup_destination`,
`password_minimum_length`, `secret_key_minimum_length`, and the files-backup
variables `ssh_mount_path`, `nextcloud_host`, `nextcloud_backup_path`,
`backup_ssh_known_hosts`, `borg_backup_hour` and `borg_backup_minute`) went
with those services. Three of them live on under homedrive's names:
`nextcloud_disk` is now `data_disk`, `nextcloud_disk_mount_path` is
`data_disk_mount_path`, and `nextcloud_homelab_user` is `homedrive_main_user`.
The rest are unused and can be deleted from an inventory.

`locale`, `top_domain`, `backup_host`, `swag_path`, `swag_dns_plugin`,
`standard_update_apply_security_updates`, and the `container_patching_*`
variables are not referenced by any maintained playbook or role and do not
need to be defined. `apply_runtime_changes_on_reboot` and
`standard_ssh_allow_users` are set by `vm1.yml`, which outranks inventory. The timezone is currently fixed
to `US/Eastern` by `configure_timezone`.

# Variables

This document lists the inventory variables used by the maintained `vm1.yml`
and `vm2.yml` playbooks. Create a gitignored `inventory.yml` and define every
variable required for the hosts you intend to manage.

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
| `ansible_host` | string | Yes, per host | Address Ansible uses to connect to `vm1` or `vm2`. | `192.168.1.120` |
| `user_name` | string | Yes | Existing non-root login and script owner. The playbooks add it to the SSH allowlist. | `example_user` |
| `default_interface` | string | Yes | Host interface assigned to the public firewalld zone. | `ens18` |
| `management_network` | list | Yes | Trusted management IPv4 CIDRs. | `["192.168.1.0/24"]` |
| `ip_ansible` | string | Yes | Ansible controller address in IPv4 CIDR notation. | `192.168.1.10/32` |
| `ansible_become` | boolean | No | Enables privilege escalation. | `true` |
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
| `traefik_path` | path | Yes | Traefik configuration and data root. | `/path/to/traefik` |
| `traefik_dashboard_fqdn` | string | Yes | Unique dashboard hostname. | `traefik.example.com` |
| `traefik_dashboard_basic_auth_users` | list | Yes, secret | One or more `user:htpasswd-hash` entries. | `["admin:$apr1$..."]` |
| `traefik_acme_email` | string | Yes | ACME account email address. | `admin@example.com` |
| `proxy_config` | list | Yes | Dynamic routes; see [Proxy entries](#proxy-entries). | One entry per exposed service |
| `container_service_names` | string | Yes | Space-separated systemd service order used by Traefik and deferred network migration. | `postgres_container redis_container nextcloud_container paperless_ngx navidrome_container vaultwarden semaphore` |
| `container_network_migration_delay` | string | No | Positive systemd time span before a queued network migration starts. | `2min` |
| `traefik_egress_network` | string | No | Dedicated non-internal Traefik egress network. | `traefik_egress_net` |

Generate a dashboard password hash with `htpasswd`; quote the complete value in
YAML so its dollar signs are preserved.

### PostgreSQL, Nextcloud, and local Borg storage

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `postgres_path` | path | Yes | Shared PostgreSQL data root. | `/path/to/postgres` |
| `postgres_admin_user` | string | Yes | PostgreSQL bootstrap/admin role. | `postgres_admin` |
| `postgres_admin_password` | string | Yes, secret | PostgreSQL admin password; must satisfy `password_minimum_length`. | Ansible Vault value |
| `nextcloud_path` | path | Yes | Nextcloud data root and disk mount point. | `/path/to/nextcloud` |
| `nextcloud_disk` | string | Yes | Nextcloud filesystem device identifier. | `UUID=example-uuid` |
| `nextcloud_database_name` | string | Yes | Nextcloud database name. | `nextcloud` |
| `nextcloud_db_user` | string | Yes | Nextcloud PostgreSQL role. | `nextcloud_user` |
| `nextcloud_db_password` | string | Yes, secret | Nextcloud database password; must satisfy `password_minimum_length`. | Ansible Vault value |
| `nextcloud_admin_user` | string | Yes | Initial Nextcloud administrator. | `admin` |
| `nextcloud_admin_password` | string | Yes, secret | Initial Nextcloud administrator password. | Ansible Vault value |
| `nextcloud_trusted_domains` | string | Yes | Space-separated trusted domains passed to Nextcloud. | `nextcloud.example.com` |
| `nextcloud_dns_name` | string | Yes | Public Nextcloud FQDN. | `nextcloud.example.com` |
| `nextcloud_homelab_user` | string | Yes when `backup_local` is `true` | Nextcloud account whose `files` tree receives local service backups. | `example_user` |
| `nextcloud_borg_backup_path` | path | Yes | Local Borg repository for Nextcloud and Paperless. | `/path/to/nextcloud/borg/backup` |
| `nextcloud_paperless_backup_location` | string | Yes | rclone destination for the Nextcloud/Paperless Borg repository. | `Nextcloud:backup/nextcloud` |
| `borg_backup_path` | path | Yes | Mount point and Borg repository root for the host backup disk. | `/path/to/borg_backup` |
| `backup_disk` | string | Yes | Host backup filesystem device identifier. | `UUID=example-backup-uuid` |
| `backup_local` | boolean | Yes | `true` when Nextcloud is on VM1; `false` selects remote SSHFS backup inputs. | `true` |
| `nextcloud_uid` | string | No | Host UID that owns Nextcloud files. | `33` (also fixed by `vm1.yml`) |
| `nextcloud_gid` | string | No | Host GID that owns Nextcloud files. | `33` (also fixed by `vm1.yml`) |
| `postgres_legacy_bootstrap_user` | string | Conditional | Old PostgreSQL admin used only during a cluster migration. | `""` |
| `postgres_legacy_bootstrap_password` | string | Conditional, secret | Password for the legacy bootstrap role. | `""` |

When `backup_local: false`, also define the following variables:

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `ssh_mount_path` | path | Conditional | Local SSHFS mount point. | `/path/to/nextcloud-remote` |
| `nextcloud_host` | string | Conditional | SSH hostname or address of the remote Nextcloud server. | `nextcloud.example.com` |
| `nextcloud_backup_path` | path | Conditional | Nextcloud path exported over SSHFS. | `/path/to/nextcloud` |
| `backup_ssh_known_hosts` | string | Conditional | One or more complete, pinned SSH `known_hosts` lines for `nextcloud_host`. | `host ssh-ed25519 AAAA...` |

### rclone/WebDAV

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `nextcloud_webdav_path` | string | Yes | Full Nextcloud WebDAV URL. | `https://nextcloud.example.com/remote.php/dav/files/example_user` |
| `nextcloud_rclone_user` | string | Yes | Nextcloud account used by the rclone remote. | `example_user` |
| `nextcloud_rclone_pass` | string | Yes, secret | Prefer a Nextcloud app password. | Ansible Vault value |
| `nextcloud_webdav_user` | string | Yes | WebDAV account rendered for Navidrome's DAV configuration. | `example_user` |
| `nextcloud_webdav_pass` | string | Yes, secret | WebDAV/app password rendered for Navidrome. | Ansible Vault value |

### Paperless NGX

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `paperless_path` | path | Yes | Paperless base directory. | `/path/to/paperless` |
| `paperless_data_path` | path | Yes | Application data directory. | `/path/to/paperless/data` |
| `paperless_media_path` | path | Yes | Media directory. | `/path/to/paperless/media` |
| `paperless_export_path` | path | Yes | Export directory included in backup. | `/path/to/paperless/export` |
| `paperless_consume_path` | path | Yes | Document inbox directory. | `/path/to/paperless/consume` |
| `paperless_database_name` | string | Yes | PostgreSQL database name. | `paperless` |
| `paperless_db_user` | string | Yes | PostgreSQL application role. | `paperless_user` |
| `paperless_db_password` | string | Yes, secret | Database password; must satisfy `password_minimum_length`. | Ansible Vault value |
| `paperless_secret_key` | string | Yes, secret | Django signing key rendered as `PAPERLESS_SECRET_KEY`; must satisfy `secret_key_minimum_length`. Paperless 3.0 dropped the built-in default and refuses to start without it. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`. | Ansible Vault value |
| `secret_key_minimum_length` | integer | No | Minimum accepted length for `paperless_secret_key`. | `32` |
| `paperless_dns_name` | string | Yes | Public Paperless FQDN. | `paperless.example.com` |

### Semaphore

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `semaphore_database_name` | string | Yes | PostgreSQL database name. | `semaphore` |
| `semaphore_db_user` | string | Yes | PostgreSQL application role. | `semaphore_user` |
| `semaphore_db_password` | string | Yes, secret | Database password. | Ansible Vault value |
| `semaphore_admin_name` | string | Yes | Initial Semaphore administrator name. | `admin` |
| `semaphore_admin_email` | string | Yes | Valid administrator email address. | `admin@example.com` |
| `semaphore_admin_password` | string | Yes, secret | Initial administrator password. | Ansible Vault value |
| `semaphore_encryption_key` | string | Yes, secret | Access-key encryption key; at least 32 characters. | Ansible Vault value |
| `semaphore_known_hosts` | string | Yes | Complete pinned SSH `known_hosts` entries mounted into Semaphore. | `host ssh-ed25519 AAAA...` |
| `semaphore_backup_location` | string | Yes | Local label or rclone backup destination. | `Nextcloud:semaphore_backup` |
| `semaphore_egress_network` | string | No | Dedicated non-backend outbound SSH network. | `semaphore_egress_net` |

### Navidrome and Vaultwarden

| Variable | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `navidrome_path` | path | Yes | Navidrome data root. | `/path/to/navidrome` |
| `navidrome_backup_location` | string | Yes | Local label or rclone backup destination. | `Nextcloud:navidrome_backup` |
| `navidrome_local_music_path` | path | No | Read-only host music library; an empty value uses `navidrome_path/music`. | `""` |
| `navidrome_uid` | string | No | Numeric container/host UID. | `33` |
| `navidrome_gid` | string | No | Numeric container/host GID. | `33` |
| `vaultwarden_path` | path | Yes | Vaultwarden data root. | `/path/to/vaultwarden` |
| `vaultwarden_backup_location` | string | Yes | Local label or rclone backup destination. | `Nextcloud:vaultwarden_backup` |
| `vaultwarden_signups_allowed` | boolean | No | Must remain `false`; the role rejects public signup. | `false` |

## Network maps

The maintained defaults below are valid as one coordinated set. Define the
complete maps in inventory only when the default address space conflicts with
the environment. Do not change one address without keeping its subnet and
corresponding maps consistent.

| Variable | Type | Required | Description |
|---|---|---|---|
| `nextcloud_backend_network_subnet` | string | No | Shared PostgreSQL/Redis/Nextcloud backend subnet; default `172.16.1.0/28`. |
| `route_proxy_network_subnets` | dictionary | No | Internal subnet keyed by each route network. |
| `route_proxy_container_ips` | dictionary | No | Backend address keyed by route network for Traefik `/etc/hosts`. |
| `route_proxy_traefik_ips` | dictionary | No | Address Traefik claims on each route network; must differ from `route_proxy_container_ips`. |
| `container_static_ips` | dictionary | No | Static address keyed by container alias. |
| `container_dns` | dictionary | No | Podman DNS domain plus logical alias map. |
| `reverse_proxy_deferred_route_networks` | list | No | Route networks whose replacement is deferred to their owning role; default is `semaphore_container_net`. |

The complete default values are:

```yaml
nextcloud_backend_network_subnet: 172.16.1.0/28
route_proxy_network_subnets:
  nextcloud_proxy_net: 172.16.1.32/29
  paperless_proxy_net: 172.16.1.40/29
  navidrome_container_net: 172.16.1.24/29
  vaultwarden_container_net: 172.16.1.16/29
  semaphore_container_net: 172.16.1.48/29
route_proxy_container_ips:
  nextcloud_proxy_net: 172.16.1.34
  paperless_proxy_net: 172.16.1.42
  navidrome_container_net: 172.16.1.26
  vaultwarden_container_net: 172.16.1.18
  semaphore_container_net: 172.16.1.50
route_proxy_traefik_ips:
  nextcloud_proxy_net: 172.16.1.35
  paperless_proxy_net: 172.16.1.43
  navidrome_container_net: 172.16.1.27
  vaultwarden_container_net: 172.16.1.19
  semaphore_container_net: 172.16.1.51
container_static_ips:
  postgres_backend: 172.16.1.2
  redis_backend: 172.16.1.3
  nextcloud_backend: 172.16.1.4
  paperless_backend: 172.16.1.5
  semaphore_backend: 172.16.1.6
  nextcloud_proxy: 172.16.1.34
  paperless_proxy: 172.16.1.42
  navidrome_proxy: 172.16.1.26
  vaultwarden_proxy: 172.16.1.18
  semaphore_proxy: 172.16.1.50
container_dns:
  domain: dns.podman
  aliases:
    postgres_backend: postgres-backend
    redis_backend: redis-backend
    nextcloud_backend: nextcloud-backend
    nextcloud_proxy: nextcloud-proxy
    paperless_backend: paperless-backend
    paperless_proxy: paperless-proxy
    navidrome_proxy: navidrome-proxy
    vaultwarden_proxy: vaultwarden-proxy
    semaphore_backend: semaphore-backend
    semaphore_proxy: semaphore-proxy
    semaphore_egress: semaphore-egress
    traefik_proxy: traefik-proxy
    traefik_egress: traefik-egress
```

### Proxy entries

Every item in `proxy_config` accepts these fields:

| Field | Type | Required | Description | Example/default |
|---|---|---|---|---|
| `name` | string | Yes | Unique router/service name. | `nextcloud_proxy` |
| `proxy_fqdn` | string | Yes | Unique `Host()` match, different from the dashboard FQDN. | `nextcloud.example.com` |
| `proxy_upstream_protocol` | string | Yes | Upstream scheme: `http` or `https`. | `http` |
| `proxy_upstream_port` | string | Yes | Port from `1` through `65535`. | `80` |
| `container_destination` | string | Yes | Podman DNS name visible on `proxy_network`. | `nextcloud-proxy.dns.podman` |
| `proxy_network` | string | Yes | Route network present in `route_proxy_container_ips`. | `nextcloud_proxy_net` |
| `proxy_allow_encoded_slash` | boolean | No | Enables encoded-slash forwarding. | `false` |
| `proxy_management_only` | boolean | No | Restricts the route to `management_network`. | `false` |

## VM2 variables

Beyond the shared variables, VM2 only requires its `ansible_host`; the `dev_vm`
role derives its user and paths from `user_name`. These variables customize the
development environment:

| Variable | Type | Required | Description | Default |
|---|---|---|---|---|
| `dev_vm_user` | string | No | Owner of interactive development tools. | `{{ user_name }}` |
| `dev_vm_npm_prefix` | path | No | User-owned npm global prefix under `/home`. | `/home/{{ dev_vm_user }}/.npm-global` |
| `dev_vm_tmux_session` | string | No | Session opened by the `devmux` helper. | `dev` |
| `dev_vm_workspace_path` | path | No | Workspace directory created for the user. | `/home/{{ dev_vm_user }}/matt_dev` |
| `dev_vm_packages` | list | No | DNF packages and package groups installed on VM2, including the Rocky 10 c-ares ABI floor required by Node.js 22. | See role defaults |
| `dev_vm_removed_docker_packages` | list | No | Docker packages declaratively removed. | See role defaults |
| `dev_vm_rootless_subid_start` | integer | No | Start of rootless Podman's subordinate UID/GID range; at least `65536`. | `100000` |
| `dev_vm_rootless_subid_count` | integer | No | Size of subordinate UID/GID range; at least `65536`. | `65536` |
| `dev_vm_npm_global_packages` | list | No | User-local npm agent CLIs. | `@openai/codex`, `@anthropic-ai/claude-code` |
| `dev_vm_npm_global_state` | string | No | npm package state, either `present` or `latest`. | `present` |
| `dev_vm_python_user_base` | path | No | User-local Python installation root. | `/home/{{ dev_vm_user }}/.local` |
| `dev_vm_python_user_packages` | list | No | Version-pinned validator CLI packages. | See role defaults |
| `dev_vm_git_user_name` | string | No | Global Git `user.name`; empty leaves it unset. | `""` |
| `dev_vm_git_user_email` | string | No | Global Git `user.email`; empty leaves it unset. | `""` |
| `dev_vm_install_project_collections` | boolean | No | Installs repository-pinned Ansible collections when the checkout exists. | `true` |
| `dev_vm_ansible_project_path` | path | No | Repository checkout on VM2. | `/home/{{ dev_vm_user }}/matt_dev/ansible_playbooks` |
| `dev_vm_ansible_collection_requirements` | path | No | Collection requirements file. | `{{ dev_vm_ansible_project_path }}/collections/requirements.yml` |
| `dev_vm_ansible_collection_path` | path | No | Collection install destination. | `{{ dev_vm_ansible_project_path }}/collections` |
| `dev_vm_path_entries` | list | No | Paths added to login and interactive shells. | npm and Python user bin directories |
| `vm2_selinux_extra_booleans` | list | No | Extra SELinux boolean objects passed to the standard role. | `[{name: domain_can_mmap_files, state: true}]` |

`vm2.yml` sets `standard_update_enable_epel: true`,
`standard_ssh_tcp_forwarding_mode: local`,
`standard_ssh_allow_agent_forwarding: true`, and
`standard_ssh_max_sessions: 10`; inventory does not need to repeat them.

## Optional shared role overrides

These variables have working defaults and normally do not belong in inventory.
They are listed here so every maintained role input is discoverable.

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `patching_minute` | string | `30` | Cron minute for the patching job. |
| `patching_hour` | string | `12` | Cron hour. |
| `patching_weekday` | string | `1` | Cron weekday. |
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
| `standard_update_apply_security_updates` | boolean | `true` | Applies security updates during normal convergence. |
| `standard_update_apply_full_updates` | boolean | `false` | Applies the full installed-package update set. |
| `standard_update_enable_epel` | boolean | `false` | Enables EPEL and CRB. |
| `nextcloud_normalize_user_files_permissions` | boolean | `true` | Normalizes permissions below every Nextcloud user's `files` tree. |
| `nextcloud_user_files_directory_mode` | string | `0770` | Directory mode used during normalization. |
| `nextcloud_user_files_file_mode` | string | `0660` | Regular-file mode used during normalization. |
| `password_minimum_length` | integer | `16` | Minimum length for the validated PostgreSQL admin, Nextcloud database, and Paperless database passwords; must be at least `1`. |

`apply_runtime_changes_on_reboot`, `approved_container_images`,
`traefik_image`, `postgres_image`, `redis_image`, `nextcloud_image`,
`paperless_image`, `navidrome_image`, `vaultwarden_image`, `semaphore_image`,
and `standard_ssh_allow_users` are assembled by the maintained playbooks.
Container image values come from `artifacts/containers.lock.yml`; do not
override them in inventory.

## Standalone playbook variable

`standalone_tasks/generate_ssh_key.yml` is outside the maintained VM1/VM2
orchestration. When running it, define `user_name` and `key_name`; `key_name` is
the filename created below `/home/{{ user_name }}` (for example,
`id_ansible_ed25519`).

## Obsolete variables

`locale`, `top_domain`, and `backup_host` are not referenced by any maintained
playbook or role and do not need to be defined. The timezone is currently fixed
to `US/Eastern` by `configure_timezone`.

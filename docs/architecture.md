# Architecture

This document covers the maintained VM topology, container/runtime patterns, firewall design, and SELinux posture. For common commands see [README.md](../README.md); for playbook composition see [playbooks.md](playbooks.md).

---

## Active Topology

| VM ID | Name | OS | Services |
|---|---|---|---|
| 120 | VM1 | Rocky Linux 10 | Nextcloud, Paperless NGX, Navidrome, Vaultwarden, Semaphore, PostgreSQL 17, Redis, Traefik reverse proxy, Borg backup |
| 121 | VM2 | Rocky Linux 10 | SSH/tmux dev VM for Codex, Claude Code, rootless Podman, and local development tooling |

Templates: VMID 400 (Debian 12 cloud-init), VMID 401 (Rocky Linux 10 cloud-init)

All VMs are provisioned via `scripts/proxmox_initial_setup.py`. See [guides/proxmox-setup.md](guides/proxmox-setup.md).

---

## Deployment Target

The maintained deployment target is Rocky Linux 10 on VM1 and VM2. Some roles still contain cross-distribution guards, but the maintained workflow documented in this repo is the Rocky Linux path.

---

## VM1 Consolidated VM (ID 120)

VM1 runs all maintained services on a single Rocky Linux 10 host to reduce resource overhead.

**Resource budget:**

| Service | Est. RAM |
|---|---|
| Nextcloud (Apache/PHP) | 2.0 GB |
| PostgreSQL 17 (shared engine, per-service roles) | 2.0 GB |
| Redis | 256 MB |
| Paperless NGX (OCR) | 1.5 GB |
| Navidrome | 256 MB |
| Vaultwarden | 256 MB |
| Semaphore | 384 MB |
| Traefik | 256 MB |
| OS + overhead | 1.5 GB |
| **Total hard cap** | **~8.4 GB (fits within VM1's 16 GB allocation)** |

**Key design decisions:**

- Traefik joins only route-declared proxy networks plus its dedicated egress network; it is not a member of the backend database/cache network.
- SELinux stays enforcing.
- PostgreSQL is shared across Nextcloud, Paperless, and Semaphore, but each application gets its own role and password.
- Runtime secrets are rendered to root-only env files in `secret_env_dir`.
- The Traefik dashboard requires both management-source allowlisting and BasicAuth.

---

## Container Network Isolation

Publicly proxied services have internal proxy-facing Podman networks, while PostgreSQL and Redis stay on an internal backend-only network. Traefik resolves backends through route-declared proxy networks and does not join the database/cache network. Latency-sensitive service names are backed by static container IPs and `/etc/hosts` entries inside client containers, so hot-path database/cache/proxy traffic does not depend on Podman DNS lookup order across multiple networks. Container egress is denied by default except for dedicated egress networks assigned to Traefik and Semaphore.

**VM1 networks:**

| Network | Subnet | Members |
|---|---|---|
| `nextcloud_container_net` | 172.16.1.0/28 | postgres (`container_dns.aliases.postgres_backend`), redis (`container_dns.aliases.redis_backend`), nextcloud (`container_dns.aliases.nextcloud_backend`), paperless (`container_dns.aliases.paperless_backend`), semaphore (`container_dns.aliases.semaphore_backend`) |
| `nextcloud_proxy_net` | 172.16.1.32/29 | nextcloud (`container_dns.aliases.nextcloud_proxy`, .34), traefik (`container_dns.aliases.traefik_proxy`, .35) |
| `paperless_proxy_net` | 172.16.1.40/29 | paperless (`container_dns.aliases.paperless_proxy`, .42), traefik (`container_dns.aliases.traefik_proxy`, .43) |
| `navidrome_container_net` | 172.16.1.24/29 | navidrome (`container_dns.aliases.navidrome_proxy`, .26), traefik (`container_dns.aliases.traefik_proxy`, .27) |
| `vaultwarden_container_net` | 172.16.1.16/29 | vaultwarden (`container_dns.aliases.vaultwarden_proxy`, .18), traefik (`container_dns.aliases.traefik_proxy`, .19) |
| `semaphore_container_net` | 172.16.1.48/29 | semaphore (`container_dns.aliases.semaphore_proxy`, .50), traefik (`container_dns.aliases.traefik_proxy`, .51) |
| `traefik_egress_net` | (auto) | traefik (`container_dns.aliases.traefik_egress`) |
| `semaphore_egress_net` | (auto) | semaphore (`container_dns.aliases.semaphore_egress`) |

The app/backend networks are created with Podman's `--internal` flag. Every role that owns a network reconciles it by including the shared `container_network` role once per network, so the create/replace rules exist in one implementation rather than once per service. Missing internal networks are created inline. If an existing app/backend network is not marked internal, or its subnet does not match the configured value, non-staged runs remove and recreate it immediately; staged VM1 runs queue the replacement. The drift decision itself is the `homelab_network_needs_replacement` filter, which parses the `podman network inspect` output once and is unit tested against both the current `internal` and legacy `Internal` key spellings. The final `container_network_migration` role schedules `/usr/local/bin/migrate_container_networks.sh` with `systemd-run --on-active=2min`. That delay lets playbooks launched from the Semaphore container finish before the job stops containers and replaces legacy networks. An exit trap always attempts to restore service availability, while stop, replacement, and restart errors make the transient unit fail and remain visible in the migration log at `/var/log/homelab-container-network-migration.log`.

Every member of a route proxy network holds a static address: the service takes its `container_static_ips` entry and Traefik takes its `route_proxy_traefik_ips` entry. Both are required. Podman's IPAM hands a container without a requested address the first free address in the subnet, which is the address the service container requests, so a dynamically addressed Traefik makes whichever container starts second fail with `IPAM error: requested ip address ... is already allocated`. Existing hosts adopt the pinned addresses on the reboot that follows the playbook run.

Traefik route files still use backend names derived from `container_dns.aliases.*` and `container_dns.domain`, and Traefik derives its app-facing network list from each `proxy_config[*].proxy_network` value. The maintained launch scripts add host-file entries for those names using static IPs, avoiding multi-network DNS latency while preserving readable route targets. Services that also join backend-only networks use proxy-network-specific dictionary entries for Traefik routes and backend-specific dictionary entries for database/cache connections.

See [inventory.md — Route Proxy Networks](inventory.md#route-proxy-networks) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Firewall Design

`standard_firewalld` creates a `homelab` zone with DROP-by-default policy and keeps firewalld running during the play. The `public` zone interface binding ensures all traffic hits the `homelab` zone rules.

Allowed traffic in `homelab` zone:

- SSH from `management_network` and `ip_ansible`
- ICMP echo-request (ping)

Ports 80 and 443 remain intentionally public on VM1. Rootful Podman's `-p 80:80/tcp -p 443:443/tcp` flags add DNAT rules before firewalld zone filtering, so these ports should be treated as explicit public ingress to Traefik.

The firewall role validates `default_interface`, `management_network`, and `ip_ansible` before applying policy. When runtime changes are enabled, rules are applied immediately and persisted; when `apply_runtime_changes_on_reboot` is true, the role stages permanent rules for the next reboot.

See [roles/standard.md#standard_firewalld](roles/standard.md#standard_firewalld) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Certificate Management

Traefik v3 handles TLS termination using its built-in ACME engine. It uses the Porkbun DNS-01 challenge to issue individual Let's Encrypt certificates for each service FQDN.

Setting `certResolver: porkbun` on the `websecure` entrypoint without wildcard `domains` causes Traefik to request one certificate per router `Host()` rule. Dynamic routing config is generated from `proxy_config` using the generic `service_proxy.yml.j2` template.

See [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy) and [inventory.md#proxy_config-object-schema](inventory.md#proxy_config-object-schema).

---

## SELinux

Rocky Linux 10 ships with SELinux in enforcing mode (targeted policy). The `standard_selinux` role ensures this and sets the booleans required by the VM1 Podman workflow:

- `virt_use_fusefs`
- `container_manage_cgroup`

VM2 also enables `domain_can_mmap_files` for interactive development tools that memory-map generated files, package-manager artifacts, or local build outputs.

All container volume mounts use `:Z`, which relabels the volume when the container starts. That covers content the container itself writes, but not content the host writes afterwards: a path outside the shipped file context rules defaults to `default_t`, which containers are denied `getattr` on. Any volume the host also writes into therefore needs a persistent rule.

The Nextcloud data disk is the one such volume, because the daily service backups install their dumps into it from cron. The `nextcloud` role owns that rule (`nextcloud_path(/.*)?` as `container_file_t`) and restores contexts on the data tree, because both are only correct once the role has mounted the disk. `restorecon` runs without `-F` so the MCS categories `:Z` applied survive. The Borg repository paths have the same exposure and are handled manually during restores; see [guides/dr-restore.md](guides/dr-restore.md).

Host-level contexts unrelated to a specific role go through `standard_selinux_extra_fcontexts` instead.

After deploying to a new host, audit for remaining denials:

```bash
ausearch -m avc -ts recent
sealert -a /var/log/audit/audit.log
```

See [roles/standard.md#standard_selinux](roles/standard.md#standard_selinux).

---

## VM2 Dev VM

VM2 is the interactive development host. Users connect over SSH, start or reattach to a tmux session with `devmux`, detach with `Ctrl-b`, then `d`, and run Codex or Claude Code from that persistent shell.

**Key design decisions:**

- VM2 uses the same Rocky Linux 10 baseline and SSH/firewall hardening as VM1.
- The dev tooling is owned by the existing `user_name` account.
- npm global packages install under `/home/{{ user_name }}/.npm-global` instead of a root-owned global prefix.
- Agent CLI PATH is managed via `/etc/profile.d/dev-vm-path.sh` (login) and a user snippet sourced from interactive `~/.bashrc` so tmux and editor terminals see npm and pip user bins.
- Root-owned Codex and Claude Code managed policies disable Codex analytics, optional telemetry exporters, feedback, error reporting, publishing, and device remote control. Connectors, automatic updates, Claude Code feature-flag retrieval, local resumable history, memory, prompt caching, and ordinary model/web requests remain available. Claude Code's application telemetry cannot be disabled independently of feature-flag retrieval, so that coupled channel remains enabled to preserve capability.
- Rootless Podman is the only container engine. Docker Engine and root-equivalent `docker` group membership are removed while `/var/lib/docker` is preserved.
- Provider auth (API keys / OAuth) is interactive and not stored in Ansible inventory.
- The playbook installs the `devmux` helper but does not automatically attach SSH logins to tmux, so Ansible, scp, and noninteractive SSH remain predictable.
- Interactive SSH logins show the dev user how to run `devmux` and detach from the tmux session.

**First login checklist:** SSH as `user_name` → `devmux` → complete Codex/Claude auth → `command -v codex claude podman`.

---

## Role Execution Order

Most standard roles run first, in this order, before any service roles:

1. `standard_ssh`
2. `standard_qemu_guest_agent`
3. `standard_update_packages`
4. `configure_timezone`
5. `standard_cron`
6. `standard_firewalld`
7. `standard_podman`
8. `standard_rclone`
9. `standard_selinux`

Service roles follow. `nextcloud` must run before `paperless_ngx` and `semaphore` because it owns the shared PostgreSQL 17 and Redis containers.

`standard_cleanup` runs after every service role, so Podman image prune only sees the currently deployed images as in use and does not delete the latest cached image before services restart. The orchestration-only `container_network_migration` role runs last so a queued disruptive migration is scheduled only after all host changes finish.

VM2 follows the same baseline order through firewall setup, then runs `dev_vm` before `standard_selinux` and `standard_cleanup`.

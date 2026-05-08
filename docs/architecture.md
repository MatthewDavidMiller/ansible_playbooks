# Architecture

This document covers the maintained VM topology, container/runtime patterns, firewall design, and SELinux posture. For common commands see [README.md](../README.md); for playbook composition see [playbooks.md](playbooks.md).

---

## Active Topology

| VM ID | Name | OS | Services |
|---|---|---|---|
| 120 | VM1 | Rocky Linux 10 | Nextcloud, Paperless NGX, Navidrome, Vaultwarden, Semaphore, PostgreSQL 17, Redis, Traefik reverse proxy, Borg backup |
| 121 | VM2 | Rocky Linux 10 | SSH/tmux dev VM for Codex, Claude Code, and local development tooling |

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
| `nextcloud_proxy_net` | 172.16.1.32/29 | nextcloud (`container_dns.aliases.nextcloud_proxy`), traefik (`container_dns.aliases.traefik_proxy`) |
| `paperless_proxy_net` | 172.16.1.40/29 | paperless (`container_dns.aliases.paperless_proxy`), traefik (`container_dns.aliases.traefik_proxy`) |
| `navidrome_container_net` | 172.16.1.24/29 | navidrome (`container_dns.aliases.navidrome_proxy`), traefik (`container_dns.aliases.traefik_proxy`) |
| `vaultwarden_container_net` | 172.16.1.16/29 | vaultwarden (`container_dns.aliases.vaultwarden_proxy`), traefik (`container_dns.aliases.traefik_proxy`) |
| `semaphore_container_net` | 172.16.1.48/29 | semaphore (`container_dns.aliases.semaphore_proxy`), traefik (`container_dns.aliases.traefik_proxy`) |
| `traefik_egress_net` | (auto) | traefik (`container_dns.aliases.traefik_egress`) |
| `semaphore_egress_net` | (auto) | semaphore (`container_dns.aliases.semaphore_egress`) |

The app/backend networks are created with Podman's `--internal` flag. Missing internal networks are created inline. If an old non-internal app/backend network already exists, non-staged runs remove it and recreate it immediately; staged VM1 runs queue the replacement and let the final `semaphore` role schedule `/usr/local/bin/migrate_container_networks.sh` with `systemd-run --on-active=2min`. That delay lets playbooks launched from the Semaphore container finish before the job stops containers, replaces legacy networks, and starts services again. The job logs to `/var/log/homelab-container-network-migration.log`.

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

All container volume mounts use `:Z`, which triggers automatic SELinux file context relabeling. No manual `sefcontext` tasks are needed.

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
- The playbook installs the `devmux` helper but does not automatically attach SSH logins to tmux, so Ansible, scp, and noninteractive SSH remain predictable.
- Interactive SSH logins show the dev user how to run `devmux` and detach from the tmux session.

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

`standard_cleanup` runs last, after service roles, so Podman image prune only sees the currently deployed images as in use and does not delete the latest cached image before services restart.

VM2 follows the same baseline order through firewall setup, then runs `dev_vm` before `standard_selinux` and `standard_cleanup`.

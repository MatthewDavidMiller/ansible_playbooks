# Architecture

For architecture patterns (container pattern, firewall pattern, role conventions, running playbooks) see [CLAUDE.md](../CLAUDE.md). This document covers the host topology, network design, SELinux policy, and the consolidated AllServices VM.

---

## Host Topology

| VM ID | Name | OS | Services |
|---|---|---|---|
| 100 | Ansible | Rocky Linux 10 | Semaphore (CI/CD), PostgreSQL 17, SWAG reverse proxy |
| 106 | Backup | Debian 12 | Borg backup server |
| 110 | VPN | Rocky Linux 10 | WireGuard, Porkbun DDNS |
| 111 | Pihole | Rocky Linux 10 | Pi-hole DNS, SWAG reverse proxy |
| 112 | NetworkController | Rocky Linux 10 | TP-Link Omada Controller, SWAG reverse proxy |
| 113 | Nextcloud | Rocky Linux 10 | Nextcloud, Paperless NGX, PostgreSQL 15, Redis, SWAG reverse proxy |
| 114 | Navidrome | Rocky Linux 10 | Navidrome music server, SWAG reverse proxy |
| 115 | Vaultwarden | Rocky Linux 10 | Vaultwarden password manager, SWAG reverse proxy |
| 116 | UnifiController | Rocky Linux 10 | Ubiquiti Unifi Controller, SWAG reverse proxy |
| 120 | AllServices | Rocky Linux 10 | Nextcloud, Paperless NGX, Navidrome, Vaultwarden, Semaphore, PostgreSQL 15, PostgreSQL 17, Redis, SWAG reverse proxy |

Templates: VMID 400 (Debian 12 cloud-init), VMID 401 (Rocky Linux 10 cloud-init)

All VMs are provisioned via `scripts/proxmox_initial_setup.py`. See [guides/proxmox-setup.md](guides/proxmox-setup.md).

---

## Distribution Targets

| Distribution | Hosts | Package manager |
|---|---|---|
| Rocky Linux 10 | All service VMs, AllServices VM | `dnf` |
| Debian 12 | Backup server | `apt` |
| Arch Linux | Laptop | `pacman` |

Role tasks are gated with `when: ansible_facts['distribution'] == '...'` to support all three. See [CLAUDE.md](../CLAUDE.md) for the convention.

---

## AllServices Consolidated VM (ID 120)

VM 120 runs all services on a single Rocky Linux 10 host to reduce resource overhead.

**Resource budget:**

| Service | Est. RAM |
|---|---|
| Nextcloud (PHP-FPM) | 1.0 GB |
| PostgreSQL 15 (Nextcloud + Paperless, shared) | 512 MB |
| Redis | 128 MB |
| Paperless NGX (OCR) | 1.0 GB |
| Navidrome | 256 MB |
| Vaultwarden | 128 MB |
| Semaphore + PostgreSQL 17 | 512 MB |
| SWAG (nginx) | 256 MB |
| OS + overhead | 1.5 GB |
| **Total** | **~5.25 GB → 8 GB with headroom** |

**Key design decisions:**

- Semaphore uses `semaphore_postgres_path` (not `postgres_path`) to keep its PostgreSQL 17 data directory separate from the Nextcloud/Paperless PostgreSQL 15 data directory. See [roles/services.md#semaphore](roles/services.md#semaphore).
- SWAG joins all four container networks simultaneously via `swag_networks`. See [Container Network Isolation](#container-network-isolation) below.
- SELinux stays enforcing. The `standard_selinux` role handles the required booleans. See [SELinux](#selinux) below.

---

## Container Network Isolation

Each service runs in its own Podman network to prevent DNS name collisions (both Nextcloud and Semaphore have a container named `postgres`).

**AllServices VM networks:**

| Network | Subnet | Members |
|---|---|---|
| `nextcloud_container_net` | 172.16.1.8/29 | postgres, redis, nextcloud, paperless, swag |
| `navidrome_container_net` | 172.16.1.24/29 | navidrome, swag |
| `vaultwarden_container_net` | 172.16.1.16/29 | vaultwarden, swag |
| `semaphore_container_net` | (auto) | semaphore_postgres, semaphore, swag |

SWAG resolves backends via Podman DNS (`nextcloud.dns.podman`, etc.) and must be a member of every network it proxies. On single-service hosts SWAG uses the scalar `swag_network` variable. On the AllServices VM it uses the `swag_networks` list — the template in `roles/reverse_proxy/templates/swag_container.sh.j2` handles both cases.

See [inventory.md — swag_networks vs swag_network](inventory.md#swag_networks-vs-swag_network) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Firewall Design

`standard_firewalld` creates a `homelab` zone with DROP-by-default policy. The `public` zone interface binding ensures all traffic hits the `homelab` zone rules.

Allowed traffic in `homelab` zone:
- SSH from `management_network` and `ip_ansible`
- ICMP echo-request (ping)

Port 443 does not require an explicit firewalld rule. Rootful Podman's `-p 443:443/tcp` flag adds DNAT rules in the nftables PREROUTING chain, which runs before firewalld zone filtering. External traffic to port 443 is DNAT'd to the container before the zone policy applies.

See [roles/standard.md#standard_firewalld](roles/standard.md#standard_firewalld) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Certificate Management

SWAG (linuxserver.io's nginx + Certbot) handles TLS termination. It uses the Porkbun DNS-01 challenge to issue wildcard Let's Encrypt certificates for `*.example.com` subdomains.

Configuration is in `roles/reverse_proxy/templates/porkbun.ini.j2`. Per-service nginx proxy configs are generated from the `proxy_config` inventory variable.

See [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy) and [inventory.md#proxy_config](inventory.md#proxy_config-object-schema).

---

## SELinux

Rocky Linux 10 ships with SELinux in enforcing mode (targeted policy). The `standard_selinux` role ensures this and sets two required booleans:

- `virt_use_fusefs` — required for Navidrome's rclone FUSE-mounted music directory. FUSE mounts cannot use the `:Z` volume label so the boolean is the correct mitigation.
- `container_manage_cgroup` — required for Podman containers managed by systemd.

All container volume mounts use `:Z` (e.g., `-v /path:/container/path:Z`) which triggers automatic SELinux file context relabeling. No manual `sefcontext` tasks are needed.

After deploying to a new host, audit for remaining denials:
```bash
ausearch -m avc -ts recent
sealert -a /var/log/audit/audit.log
```

See [roles/standard.md#standard_selinux](roles/standard.md#standard_selinux).

---

## Role Execution Order

Standard roles run first, in this order, before any service roles:

1. `standard_ssh`
2. `standard_qemu_guest_agent`
3. `standard_update_packages`
4. `configure_timezone`
5. `standard_cron`
6. `standard_firewalld`
7. `standard_podman`
8. `standard_rclone` ← must run before `standard_selinux` (FUSE packages must exist before the boolean is set)
9. `standard_selinux` ← Rocky Linux only
10. `standard_cleanup`

Service roles follow. `nextcloud` must run before `paperless_ngx` because Paperless uses the PostgreSQL 15 and Redis containers started by the Nextcloud role.

# Architecture

For architecture patterns (container pattern, firewall pattern, role conventions, running playbooks) see [CLAUDE.md](../CLAUDE.md). This document covers the host topology, network design, SELinux policy, and the consolidated VM1.

---

## Host Topology

| VM ID | Name | OS | Services |
|---|---|---|---|
| 110 | VPN | Rocky Linux 10 | WireGuard, Porkbun DDNS |
| 111 | Pihole | Rocky Linux 10 | Pi-hole DNS, SWAG reverse proxy |
| 112 | NetworkController | Rocky Linux 10 | TP-Link Omada Controller, SWAG reverse proxy |
| 116 | UnifiController | Rocky Linux 10 | Ubiquiti Unifi Controller, SWAG reverse proxy |
| 120 | VM1 | Rocky Linux 10 | Nextcloud, Paperless NGX, Navidrome, Vaultwarden, Semaphore, PostgreSQL 17, Redis, Traefik reverse proxy, Borg backup |

Templates: VMID 400 (Debian 12 cloud-init), VMID 401 (Rocky Linux 10 cloud-init)

All VMs are provisioned via `scripts/proxmox_initial_setup.py`. See [guides/proxmox-setup.md](guides/proxmox-setup.md).

---

## Distribution Targets

| Distribution | Hosts | Package manager |
|---|---|---|
| Rocky Linux 10 | All homelab VMs | `dnf` |
| Arch Linux | Laptop | `pacman` |

Role tasks are gated with `when: ansible_facts['distribution'] == '...'` to support all distributions. See [CLAUDE.md](../CLAUDE.md) for the convention.

---

## VM1 Consolidated VM (ID 120)

VM1 (ID 120) runs all services on a single Rocky Linux 10 host to reduce resource overhead.

**Resource budget:**

| Service | Est. RAM |
|---|---|
| Nextcloud (PHP-FPM) | 1.0 GB |
| PostgreSQL 17 (Nextcloud, Paperless, Semaphore — shared) | 768 MB |
| Redis | 128 MB |
| Paperless NGX (OCR) | 1.0 GB |
| Navidrome | 256 MB |
| Vaultwarden | 128 MB |
| Semaphore | 256 MB |
| Traefik | 128 MB |
| OS + overhead | 1.5 GB |
| **Total** | **~5.2 GB → 8 GB with headroom** |

**Key design decisions:**
- Traefik joins all four container networks simultaneously via `traefik_networks`. See [Container Network Isolation](#container-network-isolation) below.
- SELinux stays enforcing. The `standard_selinux` role handles the required booleans. See [SELinux](#selinux) below.

---

## Container Network Isolation

Each service runs in its own Podman network. The shared PostgreSQL 17 container is accessed by Nextcloud, Paperless, and Semaphore across their respective networks via Podman DNS resolution.

**VM1 networks:**

| Network | Subnet | Members |
|---|---|---|
| `nextcloud_container_net` | 172.16.1.8/29 | postgres, redis, nextcloud, paperless, traefik |
| `navidrome_container_net` | 172.16.1.24/29 | navidrome, traefik |
| `vaultwarden_container_net` | 172.16.1.16/29 | vaultwarden, traefik |
| `semaphore_container_net` | (auto) | semaphore_postgres, semaphore, traefik |

Traefik resolves backends via Podman DNS (`nextcloud.dns.podman`, etc.) and must be a member of every network it proxies. On VM1 it uses the `traefik_networks` list in inventory.

See [inventory.md — traefik_networks](inventory.md#traefik_networks) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Firewall Design

`standard_firewalld` creates a `homelab` zone with DROP-by-default policy. The `public` zone interface binding ensures all traffic hits the `homelab` zone rules.

Allowed traffic in `homelab` zone:
- SSH from `management_network` and `ip_ansible`
- ICMP echo-request (ping)

Ports 80 and 443 do not require explicit firewalld rules. Rootful Podman's `-p 80:80/tcp -p 443:443/tcp` flags add DNAT rules in the nftables PREROUTING chain, which runs before firewalld zone filtering. External traffic to those ports is DNAT'd to the container before the zone policy applies.

See [roles/standard.md#standard_firewalld](roles/standard.md#standard_firewalld) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Certificate Management

Traefik v3 handles TLS termination using its built-in ACME engine. It uses the Porkbun DNS-01 challenge to issue individual Let's Encrypt certificates — one per service FQDN. Certificates are stored in `{{ traefik_path }}/acme.json` and renewed automatically by Traefik.

Setting `certResolver: porkbun` on the `websecure` entrypoint without specifying wildcard `domains` causes Traefik to request a certificate for each router's exact `Host()` FQDN. Dynamic routing config is generated from the `proxy_config` inventory variable using a single generic template (`service_proxy.yml.j2`).

See [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy) and [inventory.md#proxy_config](inventory.md#proxy_config-object-schema).

---

## SELinux

Rocky Linux 10 ships with SELinux in enforcing mode (targeted policy). The `standard_selinux` role ensures this and sets two required booleans:

- `virt_use_fusefs` — set by `standard_selinux` unconditionally (harmless; retained for potential future FUSE use).
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

Service roles follow. `nextcloud` must run before `paperless_ngx` because Paperless uses the PostgreSQL 17 and Redis containers started by the Nextcloud role.

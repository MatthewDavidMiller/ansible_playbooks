# Architecture

This document covers the maintained VM1 topology, container/runtime patterns, firewall design, and SELinux posture. For common commands see [README.md](../README.md); for playbook composition see [playbooks.md](playbooks.md).

---

## Active Topology

| VM ID | Name | OS | Services |
|---|---|---|---|
| 120 | VM1 | Rocky Linux 10 | Nextcloud, Paperless NGX, Navidrome, Vaultwarden, Semaphore, PostgreSQL 17, Redis, Traefik reverse proxy, Borg backup |

Templates: VMID 400 (Debian 12 cloud-init), VMID 401 (Rocky Linux 10 cloud-init)

All VMs are provisioned via `scripts/proxmox_initial_setup.py`. See [guides/proxmox-setup.md](guides/proxmox-setup.md).

---

## Deployment Target

The maintained deployment target is Rocky Linux 10 on VM1. Some roles still contain cross-distribution guards, but the maintained workflow documented in this repo is the VM1 path.

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

- Traefik joins all four container networks via `traefik_networks`.
- SELinux stays enforcing.
- PostgreSQL is shared across Nextcloud, Paperless, and Semaphore, but each application gets its own role and password.
- Runtime secrets are rendered to root-only env files in `secret_env_dir`.

---

## Container Network Isolation

Each service runs in its own Podman network. The shared PostgreSQL 17 container is accessed across service networks via Podman DNS resolution.

**VM1 networks:**

| Network | Subnet | Members |
|---|---|---|
| `nextcloud_container_net` | 172.16.1.8/29 | postgres, redis, nextcloud, paperless, traefik |
| `navidrome_container_net` | 172.16.1.24/29 | navidrome, traefik |
| `vaultwarden_container_net` | 172.16.1.16/29 | vaultwarden, traefik |
| `semaphore_container_net` | (auto) | postgres, semaphore, traefik |

Traefik resolves backends via Podman DNS (`nextcloud.dns.podman`, etc.) and must be a member of every network it proxies. On VM1 it uses the `traefik_networks` list in inventory.

See [inventory.md — traefik_networks](inventory.md#traefik_networks) and [roles/services.md#reverse_proxy](roles/services.md#reverse_proxy).

---

## Firewall Design

`standard_firewalld` creates a `homelab` zone with DROP-by-default policy and keeps firewalld running during the play. The `public` zone interface binding ensures all traffic hits the `homelab` zone rules.

Allowed traffic in `homelab` zone:

- SSH from `management_network` and `ip_ansible`
- ICMP echo-request (ping)

Ports 80 and 443 remain intentionally public on VM1. Rootful Podman's `-p 80:80/tcp -p 443:443/tcp` flags add DNAT rules before firewalld zone filtering, so these ports should be treated as explicit public ingress to Traefik.

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

All container volume mounts use `:Z`, which triggers automatic SELinux file context relabeling. No manual `sefcontext` tasks are needed.

After deploying to a new host, audit for remaining denials:

```bash
ausearch -m avc -ts recent
sealert -a /var/log/audit/audit.log
```

See [roles/standard.md#standard_selinux](roles/standard.md#standard_selinux).

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

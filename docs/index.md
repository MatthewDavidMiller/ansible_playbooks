# Ansible Playbooks — Documentation Index

Ansible playbooks for the maintained VM1 homelab workflow. Services run as Podman containers managed by systemd.

Start with [README.md](../README.md) for the project overview and quick start.

---

## Start Here

| Document | Description |
|---|---|
| [README.md](../README.md) | Project overview and common commands |
| [guides/getting-started.md](guides/getting-started.md) | Setup from scratch and first playbook run |
| [guides/container-image-updates.md](guides/container-image-updates.md) | Secure image review, digest updates, and container hardening validation |

## Agent Instructions

| Document | Description |
|---|---|
| [AGENT.md](../AGENT.md) | Repo-specific instructions for coding agents |
| [CLAUDE.md](../CLAUDE.md) | Repo-specific instructions for Claude Code |

## Architecture & Reference

| Document | Description |
|---|---|
| [architecture.md](architecture.md) | Host topology, distribution targets, container/network/SELinux design |
| [architecture-decisions.md](architecture-decisions.md) | Rejected approaches and their rationale (Vault, host_vars/, dedicated patching playbook, etc.) |
| [playbooks.md](playbooks.md) | All playbooks — target hosts, role order, usage notes |
| [inventory.md](inventory.md) | Full inventory variable reference |
| [roles/standard.md](roles/standard.md) | Standard infrastructure roles (`standard_ssh`, `standard_firewalld`, `standard_selinux`, etc.) |
| [roles/services.md](roles/services.md) | Service roles (`nextcloud`, `vaultwarden`, `semaphore`, `reverse_proxy`, etc.) |
| [archive.md](archive.md) | Archived playbooks, roles, and historical reference docs |

## Guides

| Document | Description |
|---|---|
| [guides/getting-started.md](guides/getting-started.md) | Setup from scratch — prerequisites, collections, first playbook run |
| [guides/container-image-updates.md](guides/container-image-updates.md) | Approved container image update and review workflow |
| [guides/adding-a-service.md](guides/adding-a-service.md) | How to add a new service using established patterns |
| [guides/proxmox-setup.md](guides/proxmox-setup.md) | VM provisioning with `scripts/proxmox_initial_setup.py` |
| [guides/dr-restore.md](guides/dr-restore.md) | Disaster recovery — initial migration to VM1 and restore from backups |
| [guides/postgres-upgrade.md](guides/postgres-upgrade.md) | PostgreSQL major version upgrade procedure for the shared postgres container |
| [`../artifacts/containers.lock.yml`](../artifacts/containers.lock.yml) | Approved container image lock for the maintained VM1 services |

## Testing & CI/CD

| Document | Description |
|---|---|
| [testing.md](testing.md) | Container security tests + CI/CD pipeline (pre-commit hook runs on every commit) |

## Standards

| Document | Description |
|---|---|
| [documentation-standards.md](documentation-standards.md) | Authoring standards for this docs directory |

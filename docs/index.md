# Ansible Playbooks — Documentation Index

Ansible playbooks for the maintained homelab VM workflow. VM1 runs Podman services managed by systemd.

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
| [AGENTS.md](../AGENTS.md) | Repo-specific workflow instructions for coding agents |
| [CLAUDE.md](../CLAUDE.md) | Claude Code specifics; imports `AGENTS.md` |

## Architecture & Reference

| Document | Description |
|---|---|
| [architecture.md](architecture.md) | Host topology, distribution targets, container/network/SELinux design |
| [security.md](security.md) | VM threat model, hardening baseline, and security change rules |
| [architecture-decisions.md](architecture-decisions.md) | Rejected approaches and their rationale (Vault, host_vars/, dedicated patching playbook, etc.) |
| [playbooks.md](playbooks.md) | All playbooks — target hosts, role order, usage notes |
| [inventory.md](inventory.md) | Full inventory variable reference |
| [variables.md](variables.md) | Required, conditional, and optional variables to define or override |
| [roles/standard.md](roles/standard.md) | Standard infrastructure roles (`standard_ssh`, `standard_firewalld`, `standard_selinux`, etc.) |
| [roles/services.md](roles/services.md) | Service roles (`nextcloud`, `vaultwarden`, `playbook_runner`, `music_server`, `reverse_proxy`, etc.) |
| [archive.md](archive.md) | How to browse the separate historical `archive` branch |

## Guides

| Document | Description |
|---|---|
| [guides/getting-started.md](guides/getting-started.md) | Setup from scratch — prerequisites, collections, first playbook run |
| [guides/container-image-updates.md](guides/container-image-updates.md) | Approved container image update and review workflow |
| [guides/container-vulnerability-policy.md](guides/container-vulnerability-policy.md) | Public-safe local VEX/ignore policy and compensating controls |
| [guides/adding-a-service.md](guides/adding-a-service.md) | How to add a new service using established patterns |
| [guides/proxmox-setup.md](guides/proxmox-setup.md) | VM provisioning with `scripts/proxmox_initial_setup.py` |
| [guides/dr-restore.md](guides/dr-restore.md) | Disaster recovery — initial migration to VM1 and restore from backups |
| [guides/postgres-upgrade.md](guides/postgres-upgrade.md) | PostgreSQL major version upgrade procedure for the shared postgres container |
| [guides/playbook-runner-migration.md](guides/playbook-runner-migration.md) | Setting up playbook-runner and removing the old Semaphore install from VM1 |
| [guides/music-server-migration.md](guides/music-server-migration.md) | Setting up music-server beside Navidrome, then retiring Navidrome |
| [`../artifacts/containers.lock.yml`](../artifacts/containers.lock.yml) | Approved container image lock for the maintained VM1 services |

## Testing & CI/CD

| Document | Description |
|---|---|
| [testing.md](testing.md) | Validation pipeline, `make` targets, and container security tests (the pre-commit hook runs the gate on every commit) |
| [`../tools/toolbox/Dockerfile`](../tools/toolbox/Dockerfile) | The pinned Alpine image every lint, test, and CI/CD gate runs inside |
| [`../tests/requirements-dev.txt`](../tests/requirements-dev.txt) | Pinned Python tooling baked into the toolbox image |

## Standards

| Document | Description |
|---|---|
| [documentation-standards.md](documentation-standards.md) | Authoring standards for this docs directory |

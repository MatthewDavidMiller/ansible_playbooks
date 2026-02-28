# Ansible Playbooks — Documentation Index

Ansible playbooks for configuring homelab Linux VMs and services. Services run as Podman containers managed by systemd.

For the top-level project overview see [README.md](../README.md).
For running playbooks and architecture patterns (authoritative reference for Claude AI) see [CLAUDE.md](../CLAUDE.md).

---

## Architecture & Reference

| Document | Description |
|---|---|
| [architecture.md](architecture.md) | Host topology, distribution targets, container/network/SELinux design |
| [playbooks.md](playbooks.md) | All playbooks — target hosts, role order, usage notes |
| [inventory.md](inventory.md) | Full inventory variable reference |
| [roles/standard.md](roles/standard.md) | Standard infrastructure roles (`standard_ssh`, `standard_firewalld`, `standard_selinux`, etc.) |
| [roles/services.md](roles/services.md) | Service roles (`nextcloud`, `vaultwarden`, `semaphore`, `reverse_proxy`, etc.) |
| [roles/laptop.md](roles/laptop.md) | Arch Linux laptop installation and configuration roles |

## Guides

| Document | Description |
|---|---|
| [guides/getting-started.md](guides/getting-started.md) | Setup from scratch — prerequisites, collections, first playbook run |
| [guides/adding-a-service.md](guides/adding-a-service.md) | How to add a new service using established patterns |
| [guides/proxmox-setup.md](guides/proxmox-setup.md) | VM provisioning with `scripts/proxmox_initial_setup.py` |

## Standards

| Document | Description |
|---|---|
| [documentation-standards.md](documentation-standards.md) | Authoring standards for this docs directory |

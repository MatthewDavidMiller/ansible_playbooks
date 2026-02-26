# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Collection of Ansible playbooks for configuring homelab Linux servers and services. Primary targets are Arch Linux VMs (most servers) and Debian 12 (backup server). Services run as Podman containers managed via systemd.

## Running Playbooks

```bash
# Run a single service playbook
ansible-playbook -i inventory.yml nextcloud.yml

# Run all homelab VMs
ansible-playbook -i inventory.yml homelab_vms.yml

# Run all updates + reboots
ansible-playbook -i inventory.yml update_homelab_vms.yml

# Check mode (dry run)
ansible-playbook -i inventory.yml nextcloud.yml --check

# Run with verbose output
ansible-playbook -i inventory.yml nextcloud.yml -v

# Lint playbooks
ansible-lint
```

## Architecture

### Playbook Structure

Top-level `.yml` files are the entry points, each targeting a specific host group:
- `homelab_vms.yml` — orchestrator that imports all service playbooks
- `update_homelab_vms.yml` — runs `homelab_vms.yml` then reboots all VMs
- Service playbooks: `ansible.yml`, `nextcloud.yml`, `vaultwarden.yml`, `vpn.yml`, `backup.yml`, `navidrome.yml`, `unificontroller.yml`, `pihole.yml`, `apcontroller.yml`
- Install playbooks: `laptop_arch_install_1.yml`, `laptop_arch_install_2.yml`, `laptop_config.yml`
- Standalone tasks in `standalone_tasks/`

### Role Conventions

All roles follow the pattern `roles/<role_name>/tasks/main.yml` with optional `templates/` subdirectory for Jinja2 (`.j2`) files.

Tasks are conditionally applied per distribution using:
```yaml
when: ansible_facts['distribution'] == 'Archlinux'
when: ansible_facts['distribution'] == 'Debian'
```

### Standard Roles (applied to most hosts)

Every service playbook typically applies these roles first before service-specific ones:
1. `standard_ssh` — SSH hardening
2. `standard_qemu_guest_agent` — QEMU guest agent for Proxmox VMs
3. `standard_update_packages` — apt/pacman full upgrade
4. `configure_timezone`
5. `standard_cron` — installs cronie/cron, sets up patching schedule
6. `standard_firewalld` — configures firewalld with a `homelab` zone (DROP default, allows SSH and ICMP from management network)
7. `standard_podman` — installs Podman + logs into Docker registry via systemd service
8. `standard_cleanup` — pacman cache, orphan removal, journal vacuum, Podman prune

### Container Pattern

Services run as Podman containers launched by systemd. Each service role typically:
1. Creates data directories owned by UID/GID 1000
2. Writes a shell script (`/usr/local/bin/<service>.sh`) from a `.j2` template — this script runs the `podman run` command
3. Writes a systemd unit (`/etc/systemd/system/<service>.service`) that calls the shell script
4. Enables the systemd service

### Reverse Proxy

The `reverse_proxy` role deploys a SWAG (nginx + Let's Encrypt) container for SSL termination. It uses Porkbun DNS challenge for wildcard certificates. The `proxy_config` inventory variable is a list of objects that drives generation of per-service nginx proxy-conf files.

### Firewall Pattern

`standard_firewalld` creates a custom `homelab` zone with DROP-by-default policy. The management network (`management_network`) and Ansible controller IP (`ip_ansible`) are whitelisted sources. Service-specific roles add additional firewalld rules to the `homelab` zone.

### Inventory

Use `example_inventory.yml` as the template for your real inventory. Key global variables under `homelab.vars`:
- `management_network`, `ip_ansible` — firewall source allowlists
- `docker_username`/`docker_password` — Docker Hub credentials for Podman login
- `porkbun_api_key`/`porkbun_api_key_secret` — DNS challenge credentials
- `patching_weekday/hour/minute/month` — cron schedule variables

Host-specific variables include service paths, database credentials, and `proxy_config` lists.

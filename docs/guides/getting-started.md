# Getting Started

This guide walks you through setting up the Ansible playbooks on a new machine from scratch. For playbook commands, see [CLAUDE.md](../../CLAUDE.md).

---

## Prerequisites

Install the following on your control machine:

- **Ansible** — `pip install ansible` or via your package manager
- **ansible-lint** — `pip install ansible-lint`
- **Python 3** — required by Ansible

---

## Install Required Collections

```bash
ansible-galaxy collection install ansible.posix community.general community.crypto
```

These collections are used across roles for firewalld, SELinux, and crypto operations.

---

## Create Your Inventory

Copy `example_inventory.yml` to a new file (do not commit real credentials):

```bash
cp example_inventory.yml inventory.yml
```

Fill in all placeholder values. Key things to configure:

- `management_network` and `ip_ansible` — your management network CIDR and Ansible controller IP; these become the firewalld allowlist
- `docker_username` / `docker_password` — Docker Hub credentials (prevents pull rate limits)
- `porkbun_api_key` / `porkbun_api_key_secret` — required for SWAG certificate issuance
- `top_domain` — your domain (e.g., `example.com`)
- Per-host `ansible_host` values — IP addresses of your VMs

For a complete variable reference see [inventory.md](../inventory.md).

---

## Set Up SSH Keys

Ansible connects to managed hosts via SSH. Ensure:

1. Your control machine's SSH public key is in `~/.ssh/authorized_keys` on each managed host
2. Your inventory's `user_name` account exists on each host with sudo access
3. SSH host keys are accepted (first connect manually or use `ssh-keyscan`)

To generate a new keypair from the Ansible server:

```bash
ansible-playbook -i inventory.yml standalone_tasks/generate_ssh_key.yml -e key_name=my_key
```

---

## Bootstrap New VMs

New VMs provisioned from the Rocky Linux 10 cloud-init template (VMID 401) need one-time bootstrapping before Ansible can connect as a non-root user.

Run `scripts/setup.py` on the VM (or equivalent manual steps) to:
- Update packages
- Install Ansible
- Create the `/ansible_configs` directory

For VM provisioning itself see [guides/proxmox-setup.md](proxmox-setup.md).

---

## Run Your First Playbook

Test connectivity:

```bash
ansible -i inventory.yml all -m ping
```

Dry run against one host:

```bash
ansible-playbook -i inventory.yml nextcloud.yml --check -v
```

Apply configuration:

```bash
ansible-playbook -i inventory.yml nextcloud.yml -v
```

---

## Run All Homelab VMs

```bash
ansible-playbook -i inventory.yml homelab_vms.yml
```

This imports all service playbooks in sequence. See [playbooks.md](../playbooks.md) for the full import order.

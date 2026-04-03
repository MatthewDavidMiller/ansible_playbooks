# Getting Started

This guide walks you through setting up the Ansible playbooks on a new machine from scratch. For the project overview and common commands, see [README.md](../../README.md).

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
- `porkbun_api_key` / `porkbun_api_key_secret` — required for DDNS and Traefik DNS-01 certificate issuance
- `secret_env_dir` — where root-only runtime env files will be rendered on managed hosts
- VM1 image variables (`traefik_image`, `postgres_image`, `nextcloud_image`, etc.) — pin the container tags you want to run
- VM1 per-service DB credentials (`postgres_admin_user`, `nextcloud_db_user`, `paperless_db_user`, `semaphore_db_user`, and their passwords)
- `top_domain` — your domain (e.g., `example.com`)
- `vm1.ansible_host` — VM1's IP address or hostname

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
ansible -i inventory.yml vm1 -m ping
```

Dry run against VM1:

```bash
ansible-playbook -i inventory.yml vm1.yml --check -v
```

Apply configuration:

```bash
ansible-playbook -i inventory.yml vm1.yml -v
```

---

## Run All Homelab VMs

```bash
ansible-playbook -i inventory.yml homelab_vms.yml
```

This imports the maintained VM1 playbook. For the preferred configure-and-reboot flow, run `update_homelab_vms.yml`. See [playbooks.md](../playbooks.md) for the active playbook chain.

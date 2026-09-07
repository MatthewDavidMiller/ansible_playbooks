# Getting Started

This guide walks you through setting up the Ansible playbooks on a new machine from scratch. For the project overview and common commands, see [README.md](../../README.md).

---

## Prerequisites

Install the following on your control machine:

- **Ansible** — via your package manager or in a virtualenv, to run the playbooks against your hosts
- **Python 3** — required by Ansible
- **Rootless Podman on the control node** — required for the validation toolbox, the local container tests, and the pinned image-review tooling fallbacks. Enable its API socket with `systemctl --user enable --now podman.socket`; see [../testing.md](../testing.md) for why the gates require rootless and refuse to run rootful.

Validation tooling is not in that list. `ansible-lint`, `yamllint`, `shellcheck`, and a pinned `ansible-core` live in the toolbox image, so a container engine is all the gates need:

```bash
make install
```

That builds the image and installs the pre-commit hook. See [../testing.md](../testing.md) for the available targets.

---

## Install Required Collections

```bash
ansible-galaxy collection install -r collections/requirements.yml -p ./collections
```

The repo's `ansible.cfg` prefers `./collections`, so the control node uses the pinned collection set from `collections/requirements.yml`.

---

## Create Your Inventory

Create a local inventory file that is not committed:

```bash
$EDITOR inventory.yml
```

Use [variables.md](../variables.md) to define the required shared and VM1
values. Key things to configure include:

- `management_network` and `ip_ansible` — your management network CIDR and Ansible controller IP; these become the firewalld allowlist
- `porkbun_api_key` / `porkbun_api_key_secret` — required for DDNS and Traefik DNS-01 certificate issuance
- `secret_env_dir` — where root-only runtime env files will be rendered on managed hosts
- VM1 per-service DB credentials (`postgres_admin_user`, `nextcloud_db_user`, `paperless_db_user`, `semaphore_db_user`, and their passwords)
- `homelab_domain` — your domain (e.g., `example.com`)
- `vm1.ansible_host` — VM1's IP address or hostname

Before the first production deploy, review and pin the current upstream image digests in `artifacts/containers.lock.yml`. The maintained workflow is documented in [container-image-updates.md](container-image-updates.md) and starts with:

```bash
python3 scripts/promote_artifacts.py --check-tools
bash scripts/review_container_updates.sh
```

For inventory conventions and naming patterns, see [inventory.md](../inventory.md).

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
- Install `ansible-core`, `openssh-clients`, and the distro-packaged collections used by the maintained playbooks
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

Apply host package updates from approved repos only when you intend to do a full installed-package refresh:

```bash
ansible-playbook -i inventory.yml standalone_tasks/update_vm1_packages.yml -v
```

Normal `vm1.yml` runs apply security-only OS updates.

---

## Run All Homelab VMs

```bash
ansible-playbook -i inventory.yml homelab_vms.yml
```

This imports the maintained VM1 playbook. For the preferred configure-and-reboot flow, run `update_homelab_vms.yml`. See [playbooks.md](../playbooks.md) for the active playbook chain.

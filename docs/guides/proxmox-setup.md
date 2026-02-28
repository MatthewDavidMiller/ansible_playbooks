# Proxmox VM Setup

This guide covers provisioning new VMs on Proxmox using `scripts/proxmox_initial_setup.py`.

---

## What the Script Does

`scripts/proxmox_initial_setup.py` automates template creation and VM cloning:

1. Downloads Debian 12 and Rocky Linux 10 cloud-init images
2. Creates cloud-init templates:
   - VMID 400 — Debian 12 (used for backup server)
   - VMID 401 — Rocky Linux 10 (used for all service VMs)
3. Clones templates to create VMs:

| VMID | Name | Template | Cores | RAM |
|---|---|---|---|---|
| 100 | Ansible | 401 (Rocky 10) | 2 | 2048 MB |
| 106 | Backup | 400 (Debian 12) | 2 | 2048 MB |
| 110 | VPN | 401 | 2 | 2048 MB |
| 111 | Pihole | 401 | 2 | 2048 MB |
| 112 | NetworkController | 401 | 2 | 2048 MB |
| 113 | Nextcloud | 401 | 2 | 2048 MB |
| 114 | Navidrome | 401 | 2 | 2048 MB |
| 115 | Vaultwarden | 401 | 2 | 2048 MB |
| 116 | UnifiController | 401 | 2 | 2048 MB |
| 120 | AllServices | 401 | 4 | 8192 MB |

Each VM gets an EFI disk (`efitype=4m, pre-enrolled-keys=0`) and UEFI BIOS.

---

## Running the Script

Run on the Proxmox host shell:

```bash
python3 scripts/proxmox_initial_setup.py
```

The script uses `qm` commands and must run as root on the Proxmox node.

---

## Post-Clone Steps

### AllServices VM (VMID 120)

The AllServices VM needs a larger root disk. Run this in the Proxmox shell after cloning:

```bash
qm resize 120 scsi0 60G
```

All other VMs use the default template disk size.

### Cloud-Init Configuration

Before first boot, configure cloud-init for each VM in the Proxmox UI:

1. Set the SSH public key (used by Ansible)
2. Set the non-root user name (must match `user_name` in inventory)
3. Set the IP address (static or DHCP)
4. Set the DNS server

### First Boot

After cloud-init configuration, start the VM:

```bash
qm start <VMID>
```

Verify SSH access from your Ansible controller before running playbooks.

---

## Bootstrap (Rocky Linux 10 VMs)

Run `scripts/setup.py` on each new Rocky Linux 10 VM to install Ansible and set up the initial directory structure:

```bash
python3 scripts/setup.py
```

This script:
- Updates all packages with `dnf`
- Installs Ansible
- Installs required Ansible collections (`community.general`, `community.crypto`, `community.docker`)
- Creates `/ansible_configs` with appropriate permissions

After bootstrapping, the VM is ready for Ansible management. See [getting-started.md](getting-started.md) for next steps.

---

## Adding a New VM

To add a new VM to the setup script, follow the pattern in `scripts/proxmox_initial_setup.py`:

```python
# Create <Name> VM
subprocess.call([r"qm", r"clone", r"401", r"<VMID>", r"--name", r"<Name>"])
subprocess.call([r"qm", r"set", r"<VMID>", r"--efidisk0",
    r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0"])
subprocess.call([r"qm", r"set", r"<VMID>", r"--cores", r"<N>"])
subprocess.call([r"qm", r"set", r"<VMID>", r"--memory", r"<MB>"])
```

Use VMID 400 (Debian 12 template) for Debian-based VMs, VMID 401 (Rocky Linux 10 template) for Rocky-based VMs.

After adding a new VM, document it in [architecture.md — Host Topology](../architecture.md#host-topology).

# Playbooks Reference

For running playbook commands see [CLAUDE.md](../CLAUDE.md). This document describes every playbook's purpose, target, and role composition.

---

## Orchestrator Playbooks

### `homelab_vms.yml`

**Imports:** `vm1.yml`

**Usage:** Run to configure all homelab VMs. Currently imports only `vm1.yml` as all services are consolidated there.

---

### `update_homelab_vms.yml`

**Imports:** `homelab_vms.yml` → `reboot_vms.yml`

**Usage:** Full update cycle — reconfigure all VMs, then reboot vm1.

---

## Service Playbooks

### `vm1.yml`

**Target:** `vm1`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `standard_cleanup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `navidrome` → `vaultwarden` → `semaphore`

**Usage:** Configures VM1 (ID 120) — a single Rocky Linux 10 host running all services consolidated. See [architecture.md — VM1 Consolidated VM](architecture.md#vm1-consolidated-vm).

**Notes:** `nextcloud` must run before `paperless_ngx` (Paperless uses Nextcloud's postgres/redis containers). `standard_rclone` must run before `standard_selinux` (fuse3 packages must exist before the boolean is set). Service backup scripts (navidrome, vaultwarden, semaphore) use `backup_local: true` to copy directly to the Nextcloud data directory.

---

### `vpn.yml`

**Target:** `vpn`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_cleanup` → `vpn`

**Usage:** Configures the WireGuard VPN server (VM 110). No SWAG — VPN is accessed directly.

---

### `unificontroller.yml`

**Target:** `unificontroller`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_cleanup` → `reverse_proxy` → `unificontroller`

**Usage:** Configures the Ubiquiti Unifi Controller (VM 116).

---

### `pihole.yml`

**Target:** `pihole`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_cleanup` → `reverse_proxy` → `dns`

**Usage:** Configures the Pi-hole DNS server (VM 111).

---

### `apcontroller.yml`

**Target:** `apcontroller`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_cleanup` → `reverse_proxy` → `omadacontroller`

**Usage:** Configures the TP-Link Omada Controller (VM 112).

---

## Laptop Playbooks

### `laptop_config.yml`

**Target:** `laptop`

**Usage:** Configures an existing Arch Linux laptop installation — desktop environment (Sway), packages, shell aliases, git, security (AppArmor, firejail), and user environment. Run after `laptop_arch_install_2.yml`.

---

### `laptop_arch_install_1.yml`

**Target:** `laptop` (over root SSH into a live environment)

**Usage:** Stage 1 of bare-metal Arch Linux install — partitioning, LUKS encryption, LVM, filesystems, base package installation via `pacstrap`. Run from the Arch ISO.

---

### `laptop_arch_install_2.yml`

**Target:** `laptop` (over root SSH, chrooted)

**Usage:** Stage 2 of Arch Linux install — hostname, fstab, bootloader (systemd-boot), users, network. Run after stage 1.

---

## Reboot Playbooks

### `reboot_vms.yml`

**Target:** `vm1`

**Usage:** Reboots VM1 using a delayed shutdown (`shutdown -r +1`) so the running Semaphore/Ansible play has time to complete before the host goes down.

---

## Standalone Tasks

Located in `standalone_tasks/`. Run individually with `-i inventory.yml`.

| File | Target | Purpose |
|---|---|---|
| `apt_update_server.yml` | `debian` | Upgrade all packages on Debian hosts |
| `generate_ssh_key.yml` | `ansible` | Generate an Ed25519 SSH keypair at `/home/{{ user_name }}/{{ key_name }}` |
| `reboot_server.yml` | `ubuntu_no_ansible` | Reboot servers with 300-second wait timeout |
| `update_openwrt.yml` | `openwrt` | Update packages on OpenWrt devices via opkg |

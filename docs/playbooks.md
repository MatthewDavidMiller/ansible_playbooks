# Playbooks Reference

For running playbook commands see [CLAUDE.md](../CLAUDE.md). This document describes every playbook's purpose, target, and role composition.

---

## Orchestrator Playbooks

### `homelab_vms.yml`

**Target:** `localhost` (then delegates to all service playbooks)

**Imports (in order):** `ansible.yml` → `unificontroller.yml` → `backup.yml` → `navidrome.yml` → `nextcloud.yml` → `vaultwarden.yml` → `vpn.yml` → `all_services.yml`

**Usage:** Run to configure all homelab VMs in a single operation. Each imported playbook targets its own host group.

---

### `update_homelab_vms.yml`

**Target:** `localhost`

**Imports:** `homelab_vms.yml` → `reboot_vms.yml` → `reboot_semaphore.yml`

**Usage:** Full update cycle — reconfigure all VMs, then reboot all non-Ansible hosts, then reboot the Ansible host separately.

---

## Service Playbooks

### `all_services.yml`

**Target:** `all_services`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `standard_cleanup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `navidrome` → `vaultwarden` → `semaphore`

**Usage:** Configures the AllServices VM (ID 120) — a single Rocky Linux 10 host running all services consolidated. See [architecture.md — AllServices Consolidated VM](architecture.md#allservices-consolidated-vm).

**Notes:** `nextcloud` must run before `paperless_ngx` (Paperless uses Nextcloud's postgres/redis containers). `standard_rclone` must run before `standard_selinux` (FUSE packages needed for the `virt_use_fusefs` boolean).

---

### `ansible.yml`

**Target:** `ansible`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `standard_podman` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_cleanup` → `ansible` → `reverse_proxy` → `semaphore`

**Usage:** Configures the dedicated Ansible/Semaphore server (VM 100).

---

### `nextcloud.yml`

**Target:** `nextcloud`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_cleanup` → `reverse_proxy` → `nextcloud` → `paperless_ngx`

**Usage:** Configures the dedicated Nextcloud + Paperless NGX VM (ID 113).

---

### `vaultwarden.yml`

**Target:** `vaultwarden`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_cleanup` → `reverse_proxy` → `vaultwarden`

**Usage:** Configures the dedicated Vaultwarden VM (ID 115).

---

### `vpn.yml`

**Target:** `vpn`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `standard_cleanup` → `vpn`

**Usage:** Configures the WireGuard VPN server (VM 110). No SWAG — VPN is accessed directly.

---

### `backup.yml`

**Target:** `backup`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `standard_cron` → `standard_firewalld` → `backup`

**Usage:** Configures the Borg backup server (VM 106, Debian 12). No Podman — backup runs natively.

---

### `navidrome.yml`

**Target:** `navidrome`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `standard_podman` → `reverse_proxy` → `standard_rclone` → `standard_cleanup` → `navidrome`

**Usage:** Configures the dedicated Navidrome music server (VM 114).

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

**Target:** `homelab`

**Usage:** Reboots all homelab VMs. Skips the `ansible` host (`when: inventory_hostname != 'ansible'`) so the Ansible controller stays up during reboots.

---

### `reboot_semaphore.yml`

**Target:** `ansible`

**Usage:** Reboots the Ansible/Semaphore server. Run after `reboot_vms.yml` completes.

---

## Standalone Tasks

Located in `standalone_tasks/`. Run individually with `-i inventory.yml`.

| File | Target | Purpose |
|---|---|---|
| `apt_update_server.yml` | `debian` | Upgrade all packages on Debian hosts |
| `generate_ssh_key.yml` | `ansible` | Generate an Ed25519 SSH keypair at `/home/{{ user_name }}/{{ key_name }}` |
| `reboot_server.yml` | `ubuntu_no_ansible` | Reboot servers with 300-second wait timeout |
| `update_openwrt.yml` | `openwrt` | Update packages on OpenWrt devices via opkg |

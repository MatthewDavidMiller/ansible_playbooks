# Playbooks Reference

This document covers the maintained playbooks only. Legacy playbooks live under [`archive/playbooks/`](../archive/playbooks/) and are indexed in [archive.md](archive.md).

---

## `vm1.yml`

**Target:** `vm1`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `dynamic_dns` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `backup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `navidrome` → `vaultwarden` → `semaphore` → `standard_cleanup`

**Usage:** Configures VM1, the single maintained Rocky Linux 10 service host. Runtime-affecting changes are staged during the play and become live after `reboot_vms.yml`.

**Notes:** `vm1.yml` resolves maintained service images from `artifacts/containers.lock.yml` and pre-pulls them through `standard_podman`. `standard_update_packages` applies security-only OS updates during normal convergence. `nextcloud` must run before `paperless_ngx` and `semaphore` because it owns the shared PostgreSQL and Redis containers. `standard_rclone` must run before `standard_selinux`.

---

## `homelab_vms.yml`

**Imports:** `vm1.yml`

**Usage:** Active orchestrator playbook for the homelab. It currently imports only `vm1.yml`.

---

## `update_homelab_vms.yml`

**Imports:** `homelab_vms.yml` → `reboot_vms.yml`

**Usage:** Preferred end-to-end workflow. Reconfigures VM1, then reboots it so staged runtime changes take effect.

---

## `reboot_vms.yml`

**Target:** `vm1`

**Usage:** Reboots VM1 using delayed shutdown so the current Ansible/Semaphore run can finish cleanly before the host goes down.

---

## `standalone_tasks/update_vm1_packages.yml`

**Target:** `vm1`

**Usage:** Manual host patching workflow. Switches `standard_update_packages` into full-update mode so installed packages can be advanced beyond security errata when you explicitly choose to do so.

# Playbooks Reference

This document covers the maintained playbooks only. Legacy playbooks are preserved on the separate branch described in [archive.md](archive.md).

---

## `vm1.yml`

**Target:** `vm1`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `dynamic_dns` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `backup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `navidrome` → `vaultwarden` → `semaphore` → `standard_cleanup` → `container_network_migration`

**Usage:** Configures VM1, the single maintained Rocky Linux 10 service host. Runtime-affecting changes are staged during the play and become live after `reboot_vms.yml`.

**Notes:** `vm1.yml` resolves maintained service images from `artifacts/containers.lock.yml` and pre-pulls them through `standard_podman`. `standard_update_packages` applies security-only OS updates during normal convergence. `nextcloud` must run before `paperless_ngx` and `semaphore` because it owns the shared PostgreSQL and Redis containers. `standard_rclone` must run before `standard_selinux`. All service roles finish before `standard_cleanup`; the final `container_network_migration` coordinator then schedules any queued disruptive migration after every configuration file and unit has been rendered.

---

## `homelab_vms.yml`

**Imports:** `vm1.yml`

**Usage:** Active orchestrator playbook for the homelab.

---

## `update_homelab_vms.yml`

**Imports:** `homelab_vms.yml` → `reboot_vms.yml`

**Usage:** Preferred end-to-end workflow. Reconfigures the maintained VMs, then reboots them so staged runtime changes take effect.

---

## `reboot_vms.yml`

**Target:** `homelab`

**Usage:** Reboots maintained homelab VMs using delayed shutdown so the current Ansible/Semaphore run can finish cleanly before hosts go down.

---

## `standalone_tasks/update_vm1_packages.yml`

**Target:** `vm1`

**Usage:** Manual host patching workflow. Switches `standard_update_packages` into full-update mode so installed packages can be advanced beyond security errata when you explicitly choose to do so.

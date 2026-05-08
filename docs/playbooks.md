# Playbooks Reference

This document covers the maintained playbooks only. Legacy playbooks live under [`archive/playbooks/`](../archive/playbooks/) and are indexed in [archive.md](archive.md).

---

## `vm1.yml`

**Target:** `vm1`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `dynamic_dns` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `backup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `navidrome` → `vaultwarden` → `standard_cleanup` → `semaphore`

**Usage:** Configures VM1, the single maintained Rocky Linux 10 service host. Runtime-affecting changes are staged during the play and become live after `reboot_vms.yml`.

**Notes:** `vm1.yml` resolves maintained service images from `artifacts/containers.lock.yml` and pre-pulls them through `standard_podman`. `standard_update_packages` applies security-only OS updates during normal convergence. `nextcloud` must run before `paperless_ngx` and `semaphore` because it owns the shared PostgreSQL and Redis containers. `standard_rclone` must run before `standard_selinux`. `semaphore` runs last because VM1 playbooks are normally launched from the Semaphore container; any queued disruptive container-network migration is scheduled there after configuration files and units have been rendered.

---

## `vm2.yml`

**Target:** `vm2`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `standard_firewalld` → `dev_vm` → `standard_selinux` → `standard_cleanup`

**Usage:** Configures VM2 as a Rocky Linux 10 SSH/tmux development VM for Codex and Claude Code.

**Notes:** `vm2.yml` enables EPEL for the dev workstation package set, allows SSH TCP forwarding and raises `MaxSessions` for VS Code Remote SSH, installs agent CLIs through user-local npm under `user_name`, exposes the `devmux` helper for persistent tmux sessions, shows interactive SSH users how to run `devmux` and detach with `Ctrl-b`, then `d`, and maps `vm2_selinux_extra_booleans` into `standard_selinux_extra_booleans`. By default, VM2 enables `domain_can_mmap_files` for standard dev tooling.

---

## `homelab_vms.yml`

**Imports:** `vm1.yml` → `vm2.yml`

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

---

## `standalone_tasks/update_vm2_packages.yml`

**Target:** `vm2`

**Usage:** Manual VM2 patching workflow. Enables EPEL and switches `standard_update_packages` into full-update mode for the dev VM package set.

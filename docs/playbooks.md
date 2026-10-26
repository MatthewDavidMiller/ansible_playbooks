# Playbooks Reference

This document covers the maintained playbooks only. Legacy playbooks are preserved on the separate branch described in [archive.md](archive.md).

---

## `vm1.yml`

**Target:** `vm1`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `dynamic_dns` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `backup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `navidrome` → `vaultwarden` → `playbook_runner` → `standard_cleanup` → `container_network_migration`

**Usage:** Configures VM1, the single maintained Rocky Linux 10 service host. Runtime-affecting changes are staged during the play and become live after `reboot_vms.yml`.

**Notes:** `vm1.yml` resolves maintained service images from `artifacts/containers.lock.yml` and pre-pulls them through `standard_podman`. `standard_update_packages` applies every available Rocky Linux package update during normal convergence. `nextcloud` must run before `paperless_ngx` because it owns the shared PostgreSQL and Redis containers. `standard_rclone` must run before `standard_selinux`. All service roles finish before `standard_cleanup`; the final `container_network_migration` coordinator then schedules any queued disruptive migration after every configuration file and unit has been rendered.

---

## `homelab_vms.yml`

**Imports:** `vm1.yml`

**Usage:** Active orchestrator playbook for the homelab.

---

## `update_homelab_vms.yml`

**Imports:** `homelab_vms.yml` → `reboot_vms.yml`

**Usage:** Preferred end-to-end workflow and the weekly OS patch run. Reconfigures and fully patches the maintained VMs, then reboots them so staged runtime changes and new kernel and library packages take effect. Schedule it once a week in playbook-runner.

---

## `reboot_vms.yml`

**Target:** `homelab`

**Usage:** Reboots maintained homelab VMs using delayed shutdown so the current Ansible/playbook-runner run can finish cleanly before hosts go down.

---

## `retire_semaphore.yml`

**Target:** `vm1`

**Usage:** One-shot cleanup of the Semaphore install that `vm1.yml` no longer manages. Run it once, after `vm1.yml` has converged and VM1 has rebooted. It stops and removes the Semaphore service, container, image, launch and backup scripts, backup cron entry, config, state, secrets file, and log, removes its two Podman networks and its Traefik route file, and drops its PostgreSQL database and role. Every task is safe to repeat. It is not part of `update_homelab_vms.yml`, because it deletes a database. See [guides/playbook-runner-migration.md](guides/playbook-runner-migration.md#4-retire-semaphore).

**Inventory:** keep `semaphore_database_name`, `semaphore_db_user`, and `postgres_admin_user` until it has run; without the first two the database and role are left in place and the play says so. `semaphore_egress_network` and `secret_env_dir` are optional and default to their old values. The final Semaphore dumps in the Nextcloud tree are not touched.

**Failure:** removing a network fails while a container still uses it. That means Traefik has not restarted since `vm1.yml` dropped the route; reboot VM1 and run it again.


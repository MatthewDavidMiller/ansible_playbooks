# Playbooks Reference

This document covers the maintained playbooks only. Legacy playbooks are preserved on the separate branch described in [archive.md](archive.md).

---

## `vm1.yml`

**Target:** `vm1`

**Roles (in order):** `standard_ssh` → `standard_qemu_guest_agent` → `standard_update_packages` → `configure_timezone` → `standard_cron` → `dynamic_dns` → `standard_firewalld` → `standard_podman` → `standard_rclone` → `standard_selinux` → `backup` → `ansible` → `reverse_proxy` → `nextcloud` → `paperless_ngx` → `vaultwarden` → `playbook_runner` → `music_server` → `standard_cleanup` → `container_network_migration`

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

**Usage:** Schedules a reboot of the maintained homelab VMs one minute out, so the current playbook-runner run can finish and record its result before VM1 goes down. A run that succeeds means the reboot was scheduled, not that the host came back: run `show_logs.yml` afterwards to see that it did.

---

## `show_logs.yml`

**Target:** `vm1`

**Usage:** Shows VM1's health and service logs in the run log, so playbook-runner covers what would otherwise need SSH. It changes nothing, and is safe to run or schedule at any time.

**Choosing what to show:** the runner has no argument field, so a template uses tags. No tags shows the overview and then every service. `overview` shows only services, disk, memory, and failed units. `network` adds whether VM1 and Traefik can resolve Let's Encrypt, through each of Traefik's nameservers, with the firewall zones and Podman's network versions; use it when certificates fail with a lookup timeout. A service tag (`traefik`, `postgres`, `redis`, `nextcloud`, `paperless`, `vaultwarden`, `playbook_runner`, `music_server`, `homedrive`) shows the overview and that service. Make one template per service you check often.

**For each service:** the unit's state, the lines that look like errors from the last 24 hours, the unit's journal, and the end of the container's log. Container lines come from the journal, so they are still there after a failed container has been removed. A service that is not deployed shows `LoadState=not-found`. `show_logs_lines` (60) and `show_logs_since` (24h) can be set in the inventory.

**Privacy:** the run log holds these lines, including client addresses and paths from Traefik's access log. Only the runner's administrator can read it, and it is sealed at rest.

---

## `retire_navidrome.yml`

**Target:** `vm1`

**Usage:** One-shot cleanup of the Navidrome install that `vm1.yml` no longer manages, now that music-server serves the library. Run it once, after `vm1.yml` has converged and VM1 has rebooted. It stops and removes the Navidrome service, container, image, launch and backup scripts, backup cron entry, and logs, removes its Podman network and its Traefik route file, and turns off the `virt_use_fusefs` SELinux boolean that only Navidrome's old rclone mount needed. Every task is safe to repeat. It is not part of `update_homelab_vms.yml`. See [guides/music-server-migration.md](guides/music-server-migration.md#5-retire-navidrome).

**Data:** Navidrome's data directory is kept. To delete it too, run with `-e retire_navidrome_remove_data=true` while `navidrome_path` is still in the inventory; the play refuses a path under Nextcloud or a bare parent such as `/opt`. The music (the Nextcloud `Music` folder) and the final database dumps in the Nextcloud tree are never touched. `-e retire_navidrome_disable_fusefs=false` leaves the SELinux boolean as it is. Afterwards, `scripts/remove_navidrome_inventory.py` removes the Navidrome settings from the inventory.

**Failure:** removing the network fails while a container still uses it. That means Traefik has not restarted since `vm1.yml` dropped the route; reboot VM1 and run it again.

---

## `retire_semaphore.yml`

**Target:** `vm1`

**Usage:** One-shot cleanup of the Semaphore install that `vm1.yml` no longer manages. Run it once, after `vm1.yml` has converged and VM1 has rebooted. It stops and removes the Semaphore service, container, image, launch and backup scripts, backup cron entry, config, state, secrets file, and log, removes its two Podman networks and its Traefik route file, and drops its PostgreSQL database and role. Every task is safe to repeat. It is not part of `update_homelab_vms.yml`, because it deletes a database. See [guides/playbook-runner-migration.md](guides/playbook-runner-migration.md#4-retire-semaphore).

**Inventory:** keep `semaphore_database_name`, `semaphore_db_user`, and `postgres_admin_user` until it has run; without the first two the database and role are left in place and the play says so. `semaphore_egress_network` and `secret_env_dir` are optional and default to their old values. The final Semaphore dumps in the Nextcloud tree are not touched.

**Failure:** removing a network fails while a container still uses it. That means Traefik has not restarted since `vm1.yml` dropped the route; reboot VM1 and run it again.

---

## `homedrive_import.yml`

**Target:** `vm1`

**Usage:** One-shot bulk load of the Nextcloud files tree (`<nextcloud_path>/data/<nextcloud_homelab_user>/files`) into a homedrive drive, followed by the checks the migration needs. It needs homedrive 0.1.4 or later. Run it after `vm1.yml` has deployed homedrive. It is not part of `update_homelab_vms.yml`. Re-running is safe. See [guides/homedrive.md](guides/homedrive.md#importing-the-previous-file-service).

**A run with no tags** reads only what the drive lacks, so it takes minutes, not hours. `verify-tree --quick` lists every source path the drive lacks, by size and without reading files, and the play stops before writing anything if more than `homedrive_import_max_missing` (100) are missing. That means the wrong user or source, or a sync client that has not finished uploading. `import-tree --only-missing` then adds the missing files, without old versions, and leaves every path the drive has unread. A second quick check must find nothing missing.

**The `full` tag** (a template of its own, with a long timeout) runs the slow checks that must pass before the source is retired: `verify-tree` compares every source file byte for byte, `fsck --deep` reads every version back, and `gc --dry-run` shows what collection would free. The play fails unless `verify-tree` and `fsck` are both clean. The source's hashes are kept in `homedrive_import_cache_dir` (`/var/lib/homedrive_import`), so a later run, or one that was cut off, reads only files that changed since. `-e homedrive_import_fresh=true` reads everything afresh.

**Inventory:** `homedrive_import_user` defaults to `nextcloud_homelab_user` and must be one of `homedrive_users`. `homedrive_import_src`, `homedrive_import_dest` (the drive's root by default), `homedrive_import_max_missing`, `homedrive_import_cache_dir`, and `homedrive_import_timeout_s` (24 hours per step) can be overridden; the cache may not be inside, or contain, the source or the store. The full output, file names included, goes to `/var/log/homedrive_import.log`; the run log shows summaries and at most 50 file lines per step.

**Isolation:** the import runs in a one-off container from the running server's image with no network, the source and the store both mounted read-only, the cache directory its only writable mount, and SELinux separation off for that container only, so neither tree is relabeled. It reads the Nextcloud files through their group, and writes to the drive only through the server's admin socket.

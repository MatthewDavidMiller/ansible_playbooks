# Standard Roles Reference

These roles are applied to most hosts before any service-specific roles. See [architecture.md — Role Execution Order](../architecture.md#role-execution-order) for the required ordering.

---

### `standard_ssh`

Hardens the SSH daemon by disabling password authentication, root login, empty passwords, challenge-response auth, GSSAPI auth, and PAM; enables public key authentication.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `standard_qemu_guest_agent`

Installs the QEMU guest agent so Proxmox can communicate with the VM (snapshot coordination, IP reporting, clean shutdown).

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `standard_update_packages`

Upgrades all installed packages to their latest versions. On Rocky Linux 10, also installs and enables the EPEL repository before upgrading.

**Distributions:** Debian 12 (`apt`), Rocky Linux 10 (`dnf`), Arch Linux (`pacman`)

**Required variables:** None

**Templates:** None

---

### `configure_timezone`

Sets the system timezone to `America/New_York`.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `standard_cron`

Installs the cron daemon. On Rocky Linux 10 enables `crond.service`, on Arch Linux enables `cronie.service`, on Debian 12 enables `cron.service`. Also removes any scheduled automatic update job from the crontab.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `standard_firewalld`

Installs firewalld and configures a restrictive `homelab` zone:

- `public` zone target set to DROP
- `homelab` zone created with DROP target
- Management network (`management_network`) and Ansible controller IP (`ip_ansible`) added as allowed sources
- SSH and ICMP echo-request enabled in `homelab` zone
- SSH, cockpit, dhcpv6-client, mdns disabled in `public` zone
- Network interface bound to `public` zone (traffic enters homelab zone via source matching)
- firewalld enabled and started

Port 443 is **not** opened here — the `reverse_proxy` role opens it on hosts running SWAG.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `management_network` | string | CIDR of management network | `192.168.1.0/24` |
| `ip_ansible` | string | Ansible controller IP (CIDR) | `192.168.1.1/32` |
| `default_interface` | string | Primary network interface | `eth0` |

**Templates:** None

---

### `standard_podman`

Installs Podman and its DNS dependencies. On Arch Linux also installs `cni-plugins`, `netavark`, and `aardvark-dns`. Creates and enables a `login_to_docker.service` systemd unit that logs Podman into Docker Hub on boot (avoids pull rate limits).

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `docker_username` | string | Docker Hub username | `myuser` |
| `docker_password` | string | Docker Hub password | `secret` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `login_to_docker.j2` | `/etc/systemd/system/login_to_docker.service` | Systemd unit for Docker Hub login on boot |

---

### `standard_rclone`

Installs rclone and fuse3. Creates the rclone config file at `/root/.config/rclone/rclone.conf` from a template (used by Navidrome for mounting music files and by Nextcloud/Vaultwarden for backups).

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** rclone remote credentials (defined in template — varies by provider)

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `rclone_config.j2` | `/root/.config/rclone/rclone.conf` | rclone configuration file |

---

### `standard_selinux`

Ensures SELinux is enforcing (policy: targeted) on Rocky Linux 10 and sets two booleans required for Podman-based services.

**Distributions:** Rocky Linux 10 only (all tasks gated with `when: ansible_facts['distribution'] == 'Rocky'`)

**Required variables:** None

**Templates:** None

**Notable tasks:**

- Installs `policycoreutils-python-utils` and `setroubleshoot-server` (provides `semanage`, `audit2allow`, `sealert`)
- Sets `virt_use_fusefs=on` (persistent) — required for Navidrome's rclone FUSE mount; FUSE mounts cannot use `:Z` volume labels
- Sets `container_manage_cgroup=on` (persistent) — required for Podman containers managed by systemd

**Notes:**
- All container volume mounts use `:Z` which handles SELinux file context relabeling automatically — no `sefcontext` tasks are needed
- After first deployment run `ausearch -m avc -ts recent` to catch any remaining denials
- Must run after `standard_rclone` so fuse3 packages exist before the `virt_use_fusefs` boolean is set

---

### `standard_cleanup`

Cleans up package caches, old logs, and stale container artifacts:

- Removes orphaned packages (dnf/pacman)
- Clears package manager caches
- Deletes log files older than 30 days from `/var/log`
- Vacuums systemd journal to 500 MB
- Prunes stopped Podman containers, unused images, volumes, and networks

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `standard_reboot`

Reboots the host and waits for it to come back up. Used by `reboot_vms.yml` and `reboot_semaphore.yml`.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `standard_patching`

Sets up a cron job for automated package patching on a configurable schedule.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `patching_weekday` | integer | Day of week (0=Sun) | `1` |
| `patching_hour` | integer | Hour | `12` |
| `patching_minute` | integer | Minute | `30` |
| `patching_month` | string | Month | `"1"` |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `update_system.j2` | `/etc/cron.d/update_system` | Cron job for dnf/apt updates |
| `update_system_arch.j2` | `/etc/cron.d/update_system` | Cron job for pacman updates |

---

### `standard_python`

Installs Python 3.

**Distributions:** Debian 12, Rocky Linux 10, Arch Linux

**Required variables:** None

**Templates:** None

---

### `configure_timezone`

Sets system timezone. See [above](#configure_timezone).

---

### `standard_openwrt`

Applies baseline configuration to OpenWrt hosts. Used for network devices, not standard VMs.

---

### `standard_pi_config`

Applies Raspberry Pi-specific configuration overrides.

# Standard Roles Reference

These are the maintained infrastructure roles used by `vm1.yml`. Historical standard roles live under the archive.

---

### `standard_ssh`

Deploys the managed SSH hardening drop-in under `/etc/ssh/sshd_config.d/`.

**Key behavior:** disables password auth and root login, keeps project SSH defaults centralized, and validates the config before reload.

---

### `standard_qemu_guest_agent`

Installs and enables the QEMU guest agent so Proxmox can coordinate clean shutdowns, report IPs, and handle snapshots more reliably.

---

### `standard_update_packages`

Updates installed packages to the latest available versions. On Rocky Linux 10 it also enables EPEL before upgrading.

---

### `configure_timezone`

Sets the system timezone to `America/New_York`.

---

### `standard_cron`

Installs and enables the platform cron service, and removes any legacy OS-level patching cron jobs so Semaphore remains the scheduling source of truth.

---

### `standard_firewalld`

Builds the restrictive `homelab` firewalld model used by VM1.

**Required variables:** `management_network`, `ip_ansible`, `default_interface`

**Key behavior:** creates a DROP-by-default `homelab` zone, whitelists the management network and Ansible controller, allows SSH and ping, and keeps the public interface bound to `public`.

---

### `standard_podman`

Installs Podman and registry-login support.

**Required variables:** `docker_username`, `docker_password`, `secret_env_dir`

**Templates:** `login_to_docker.j2`, `docker_login.env.j2`

**Key behavior:** writes a root-only Docker credential env file and a boot-time login service so image pulls can avoid anonymous rate limits.

---

### `standard_rclone`

Installs rclone and writes the root rclone config used by backups and any file-mount workflow.

**Templates:** `rclone_config.j2`

---

### `standard_selinux`

Keeps SELinux enforcing on Rocky Linux 10 and sets the booleans required by the VM1 Podman workflow.

**Key behavior:** enables `container_manage_cgroup`, sets `virt_use_fusefs`, installs troubleshooting tools, and relies on `:Z` mounts for container relabeling.

---

### `standard_cleanup`

Runs the post-deploy cleanup pass.

**Key behavior:** clears caches, prunes stale logs, vacuums the journal, and prunes stopped or unused Podman artifacts after service deployment completes.

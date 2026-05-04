# Standard And Dev Roles Reference

These are the maintained infrastructure and dev-host roles used by the active VM playbooks. Historical standard roles live under the archive.

---

### `standard_ssh`

Deploys the managed SSH hardening drop-in under `/etc/ssh/sshd_config.d/`.

**Key behavior:** disables password auth and root login, keeps project SSH defaults centralized, and validates the config before reload.

---

### `standard_qemu_guest_agent`

Installs and enables the QEMU guest agent so Proxmox can coordinate clean shutdowns, report IPs, and handle snapshots more reliably.

---

### `standard_update_packages`

Applies security-only OS package updates during normal convergence and keeps broader package refreshes behind a standalone patching playbook.

**Key behavior:** normal `vm1.yml` convergence runs `dnf` security updates for installed packages only; `standalone_tasks/update_vm1_packages.yml` switches the role into full-update mode on demand.

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

Installs Podman and enforces the approved-image policy before any service starts.

**Required variables:** `approved_container_images`, `secret_env_dir`

**Key behavior:** validates that every maintained image ref is an immutable digest reference, pre-pulls approved images, and keeps service restarts from fetching tags from upstream.

---

### `standard_rclone`

Installs rclone and writes the root rclone config used by backups and any file-mount workflow.

**Templates:** `rclone_config.j2`

---

### `standard_selinux`

Keeps SELinux enforcing on Rocky Linux 10 and sets the booleans required by the VM1 Podman workflow.

**Optional variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `standard_selinux_extra_booleans` | list | Host-specific SELinux booleans to set persistently | `[{name: domain_can_mmap_files, state: true}]` |
| `standard_selinux_extra_fcontexts` | list | Host-specific SELinux file context rules to apply and restore | `[{target: "/srv/dev(/.*)?", setype: container_file_t, restore_path: "/srv/dev"}]` |

**Key behavior:** enables `container_manage_cgroup`, sets `virt_use_fusefs`, installs troubleshooting tools, applies explicit host-specific SELinux exceptions, and relies on `:Z` mounts for container relabeling.

---

### `standard_cleanup`

Runs the post-deploy cleanup pass.

**Key behavior:** clears caches, prunes stale logs, vacuums the journal, and prunes stopped or unused Podman artifacts after service deployment completes.

---

### `dev_vm`

Configures VM2 as an SSH/tmux development host for Codex and Claude Code.

**Distributions:** Rocky Linux 10

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `user_name` | string | Existing non-root SSH user that owns the agent CLIs | `example_user` |

**Optional variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `dev_vm_user` | string | Dev user override; defaults to `user_name` | `example_user` |
| `dev_vm_npm_prefix` | path | User-local npm global prefix | `/home/example_user/.npm-global` |
| `dev_vm_tmux_session` | string | Default tmux session name for `devmux` | `dev` |
| `dev_vm_packages` | list | Rocky package baseline for the dev VM | `[tmux, git, nodejs]` |
| `dev_vm_npm_global_packages` | list | npm packages installed for the dev user | `["@openai/codex", "@anthropic-ai/claude-code"]` |

**Key behavior:** installs heavy workstation packages, keeps npm global packages under the dev user's home directory, exposes that bin path through `/etc/profile.d/dev-vm-npm.sh`, and installs a `devmux` helper that attaches to or creates a persistent tmux session. Interactive SSH logins for the dev user show a short `devmux` usage hint, including `Ctrl-b`, then `d`, to detach from tmux. `vm2.yml` pairs this role with a VM2-only SELinux `domain_can_mmap_files` boolean for standard dev tooling.

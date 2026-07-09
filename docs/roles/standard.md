# Standard And Dev Roles Reference

These are the maintained infrastructure and dev-host roles used by the active VM playbooks. Historical standard roles live under the archive.

---

### `standard_ssh`

Deploys the managed SSH hardening drop-in under `/etc/ssh/sshd_config.d/`.

**Key behavior:** disables password auth and root login, keeps project SSH defaults centralized, and validates the config before reload.

**Optional variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `standard_ssh_allow_users` | list | Optional account allowlist for SSH logins | `[example_user]` |
| `standard_ssh_allow_tcp_forwarding` | bool | Enable SSH TCP forwarding for hosts that need editor remoting | `true` |
| `standard_ssh_max_sessions` | integer | SSH session channel limit | `10` |

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

Configures VM2 as an SSH/tmux development host for Codex, Claude Code, and Grok Build.

**Distributions:** Rocky Linux 10

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `user_name` | string | Existing non-root SSH user that owns the dev agent tooling (npm CLIs + Grok Build) | `example_user` |

**Optional variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `dev_vm_user` | string | Dev user override; defaults to `user_name` | `example_user` |
| `dev_vm_npm_prefix` | path | User-local npm global prefix | `/home/example_user/.npm-global` |
| `dev_vm_tmux_session` | string | Default tmux session name for `devmux` | `dev` |
| `dev_vm_workspace_path` | path | Parent workspace directory created empty for the dev user (no auto clone) | `/home/example_user/matt_dev` |
| `dev_vm_packages` | list | Rocky package baseline (tmux, git, nodejs, podman, go, rust, ripgrep, fd-find, bubblewrap, tree, ShellCheck, yamllint, gh, ansible-core, …) | see role defaults |
| `dev_vm_docker_packages` | list | Docker Engine packages from Docker's official RHEL repository | `[docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin]` |
| `dev_vm_docker_prune` | boolean | When true, run `docker system prune -f` on converge | `false` |
| `dev_vm_npm_global_packages` | list | npm packages for the dev user; pin with `name@version` when desired | `["@openai/codex", "@anthropic-ai/claude-code"]` |
| `dev_vm_npm_global_state` | string | npm module state: `present` (stable) or `latest` (refresh CLIs) | `present` |
| `dev_vm_grok_installer_url` | string | URL of the official Grok Build CLI installer script (mutable latest) | `https://x.ai/cli/install.sh` |
| `dev_vm_grok_update` | boolean | When true, re-download and re-run the Grok installer each converge | `false` |
| `dev_vm_python_user_packages` | list | pip `--user` CLI packages | `["ansible-lint", "pre-commit"]` |
| `dev_vm_git_user_name` | string | Optional global `git user.name` for the dev user; empty skips | `Example User` |
| `dev_vm_git_user_email` | string | Optional global `git user.email` for the dev user; empty skips | `user@example.com` |
| `dev_vm_ansible_project_path` | path | Checkout path used to find pinned collection requirements | `/home/example_user/matt_dev/ansible_playbooks` |
| `dev_vm_install_project_collections` | boolean | Install repo-pinned Ansible collections when the checkout exists | `true` |

**Key behavior:** installs the workstation package baseline (search tools, build toolchain, `gh`, ShellCheck, yamllint, Podman), installs and enables Docker Engine from Docker's official RHEL repository for local container validation, and adds the dev user to the `docker` group (effectively root-equivalent; intentional on a single-user dev VM). npm and Python CLIs install under the dev user's home; Grok Build installs via the official xAI installer into `~/.grok/bin`. A single `/etc/profile.d/dev-vm-path.sh` plus `~/.config/dev-vm/path.sh` (sourced from interactive `~/.bashrc`) expose npm, Grok, and pip user bins. Optional git identity is written only when name/email vars are non-empty. Repo-pinned Ansible collections install when the checkout exists; otherwise the role logs a clear skip warning. Manages `~/.tmux.conf` mouse scrolling and the `devmux` helper for persistent agent sessions (no auto-attach). Provider auth (Codex/Claude/Grok login) is interactive and not provisioned by Ansible.

**First login (interactive):**

1. SSH as `user_name`, then run `devmux`.
2. Complete provider auth as needed (`codex login`, Claude Code login, Grok auth).
3. Confirm CLIs resolve: `command -v codex claude grok ansible-lint gh`.

**Grok upgrades:** leave `dev_vm_grok_update: false` for install-once behavior; set `true` on the next converge to refresh, or run `grok update` inside `devmux`. `vm2.yml` pairs this role with a VM2-only SELinux `domain_can_mmap_files` boolean for standard dev tooling.

# Standard Roles Reference

These are the maintained infrastructure roles used by the active VM playbook. Historical standard roles are preserved on the branch described in [archive.md](../archive.md).

---

### `standard_ssh`

Deploys the managed SSH hardening drop-in under `/etc/ssh/sshd_config.d/`.

**Key behavior:** disables password auth and root login, keeps project SSH defaults centralized, and validates the config before reload. The drop-in pins the SFTP subsystem to the Rocky path `/usr/libexec/openssh/sftp-server`; `sshd -t` does not check that the binary exists, so a wrong path silently breaks SFTP and SSHFS.

**Optional variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `standard_ssh_allow_users` | list | Optional account allowlist for SSH logins | `[example_user]` |
| `standard_ssh_tcp_forwarding_mode` | string | OpenSSH forwarding mode (`no`, `local`, `remote`, or `yes`) | `local` |
| `standard_ssh_allow_agent_forwarding` | bool | Enable agent forwarding; disabled by the role | `true` |
| `standard_ssh_streamlocal_forwarding_mode` | string | Unix-socket forwarding mode | `no` |
| `standard_ssh_max_sessions` | integer | SSH session channel limit | `10` |

---

### `standard_qemu_guest_agent`

Installs and enables the QEMU guest agent so Proxmox can coordinate clean shutdowns, report IPs, and handle snapshots more reliably.

---

### `standard_update_packages`

Applies security-only OS package updates during normal convergence and keeps broader package refreshes behind a standalone patching playbook.

**Key behavior:** normal `vm1.yml` convergence runs `dnf` security updates for installed packages only; `standalone_tasks/update_vm1_packages.yml` switches the role into full-update mode on demand. When `standard_update_enable_epel` is true, the role installs `epel-release` and enables CRB (CodeReady Builder) so EPEL packages can resolve CRB-provided dependencies such as `python3-pathspec`.

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

**Key behavior:** creates a DROP-by-default `homelab` zone, semantically validates and reconciles the management/controller CIDRs, allows SSH and ping, and keeps the public interface bound to `public`.

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

**Key behavior:** clears package caches and vacuums the journal. Destructive container/image pruning is opt-in; volumes and networks are never pruned automatically.

---

### `container_network`

Reconciles a single Podman network to the state its calling role declares.
Service roles include it once per network they own instead of repeating the
inspect/create/replace sequence, so the drift rules live in one place.

**Optional variables:**

| Variable | Type | Description | Default |
|---|---|---|---|
| `container_network_name` | string | Network to reconcile | `""` |
| `container_network_subnet` | string | Deterministic IPv4 CIDR, or empty to let Podman choose | `""` |
| `container_network_internal` | bool | Exact desired internal mode; drift in either direction triggers replacement | `true` |
| `container_network_reconcile_existing` | bool | Repair drift on an existing network; when false the network is still created if missing | `true` |
| `container_network_defer` | bool | Queue replacement instead of performing it inline | `apply_runtime_changes_on_reboot` |

**Key behavior:** validates the requested name, subnet, and boolean controls, inspects the network
once, and decides replacement through the `homelab_network_needs_replacement`
filter. A missing network is always created. An existing network whose internal
mode or subnet does not match is force-removed and recreated during non-staged
runs, or appended to `container_network_migrations` during staged runs so
`container_network_migration` can replace it after the play finishes. Deferred
requests retain the desired internal mode, so egress networks remain external.

Set `container_network_reconcile_existing: false` when another role owns the
network's lifecycle — `reverse_proxy` uses this for
`reverse_proxy_deferred_route_networks` so it never tears down the network
carrying the Semaphore container that is running the playbook.

**Usage:**

```yaml
- name: Reconcile Navidrome proxy network
  ansible.builtin.include_role:
    name: container_network
  vars:
    container_network_name: navidrome_container_net
    container_network_subnet: "{{ route_proxy_network_subnets.navidrome_container_net }}"
```

---

### `container_network_migration`

Coordinates queued Podman network replacements after every VM1 service role and
the cleanup pass have completed.

**Optional variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| `container_network_migration_delay` | string | Positive systemd time span before the migration starts | `2min` |

**Key behavior:** validates the queued network definitions and service restart
order, renders one root-only migration script, and schedules it with a transient
systemd unit. The script always attempts to restart services through an exit
trap and fails visibly if a stop, network replacement, or restart fails.

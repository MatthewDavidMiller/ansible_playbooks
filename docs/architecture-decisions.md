# Architecture Decisions

This document records explicit design decisions — approaches considered but ultimately rejected — and the reasoning behind them. Understanding these decisions prevents reconsidering already-evaluated options.

---

## Rejected: Ansible Vault for Secrets Management

**Decision:** Do not use Ansible Vault to encrypt credentials in the git repository.

**Rationale:**
- Real inventory with credentials is managed externally in Semaphore (not this git repository).
- The checked-in `example_inventory.yml` is a template / reference, not a live inventory.
- Vault would add complexity (managing encryption keys, distributing to contributors) without benefit: there are no live secrets in the repo to encrypt.
- Contributors copy `example_inventory.yml` to their real inventory, fill in actual credentials, and manage that file securely outside git.

**How to apply:**
- When documenting variables that will contain secrets (passwords, API keys), note them as such in the variable table (e.g., `postgres_database_user_password: string | required | Secret: PostgreSQL superuser password`).
- Do not commit real values for these variables to git. The `example_inventory.yml` file uses placeholder values like `secret`, `mypassword`, `pk1_...`.
- Treat the real inventory file (wherever contributors keep it) as a .gitignored local configuration, not a tracked artifact.

---

## Rejected: `host_vars/` and `group_vars/` Directory Structure

**Decision:** Do not split inventory into `host_vars/`, `group_vars/`, and `inventory.yml` files.

**Rationale:**
- Semaphore manages inventory injection at runtime. Variables are resolved and merged in the Semaphore UI, not by Ansible's `host_vars`/`group_vars` loading mechanism.
- The inline `example_inventory.yml` format (all variables in one YAML file) is the correct pattern for this workflow: it serves as a complete, self-contained reference that Semaphore ingests as a single unit.
- Splitting across multiple files adds fragmentation without corresponding benefit — contributors must understand and maintain multiple locations, and the single-file format is easier to reason about and document.

**How to apply:**
- Keep the inline inventory structure. All variables for a host go into its entry in `example_inventory.yml`.
- Document the complete variable reference in `docs/inventory.md` (grouped by host for readability).
- When Semaphore ingests `example_inventory.yml`, it does so as-is; no dynamic variable merging from separate `host_vars/` files occurs.

---

## Rejected: Dedicated Patching Playbook

**Decision:** Do not create a separate `patch_homelab_vms.yml` playbook. Use the existing Semaphore schedule instead.

**Rationale:**
- The `homelab_vms.yml` playbook is already scheduled weekly in Semaphore (applies all configuration roles + standard patching).
- Creating a dedicated `patch_homelab_vms.yml` playbook would duplicate:
  - The logic for determining which hosts to patch (same host selection as `homelab_vms.yml`)
  - The standard roles (ssh, firewall, podman, etc.) that should run even on patch days
  - The orchestration / restart policy decisions
- Semaphore's scheduling feature already provides the "periodic patching" mechanism. Using the calendar UI in Semaphore is clearer than maintaining two playbooks in the codebase.

**How to apply:**
- Patching is triggered by the Semaphore schedule (weekly run of `homelab_vms.yml`), not by an OS-level cron job.
- The `standard_cron` role sets `state: absent` for any historical patching cron jobs, ensuring no conflicting system-level scheduling.
- When updating patching frequency, adjust the Semaphore schedule in the Semaphore UI, not in the Ansible code.

---

## Decision: Cron Job Removal via `standard_cron`

**Decision:** The `standard_cron` role explicitly removes any patching cron jobs by setting their `state: absent`.

**Rationale:**
- In previous iterations, patching was driven by OS-level cron jobs. This has been replaced by Semaphore scheduling.
- Leaving old cron jobs in place would cause duplicate runs (OS cron + Semaphore schedule) and unexpected behavior.
- Explicitly removing them via Ansible ensures:
  - A clean migration path: old systems have cron jobs removed when re-provisioned
  - No surprises: cron-based patching doesn't run in parallel with Semaphore
  - Clear intent: the Ansible code documents that Semaphore is the source of truth for scheduling

**How to apply:**
- The `standard_cron` role removes patching cron entries on every run.
- Contributors running playbooks see `ok: [host] → cron...state=absent` tasks, confirming the cleanup is intentional.
- If OS-level cron-based patching is ever needed again, this decision can be reversed by changing the cron task state to `present`.

---

## Decision: Container Security Hardening (`--cap-drop=ALL`)

**Decision:** All service containers run with `--cap-drop=ALL` and `--security-opt=no-new-privileges:true`. Capabilities are re-added only where functionally required.

**Exceptions and required caps:**
- **Traefik:** adds `--cap-add=NET_BIND_SERVICE` (binds ports 80/443 as a non-root process)
- **Pi-hole:** adds `--cap-add=NET_BIND_SERVICE` (binds port 53/tcp and 53/udp)
- **Vaultwarden:** adds `--cap-add=NET_BIND_SERVICE` (required by the image's privileged-port listener)
- **Redis:** adds `CHOWN`, `FOWNER`, and `DAC_OVERRIDE` for startup-time filesystem ownership handling
- **Paperless NGX:** adds `CHOWN`, `SETUID`, `SETGID`, `FOWNER`, and `DAC_OVERRIDE` to support `USERMAP_UID/GID` and entrypoint privilege dropping
- **Navidrome:** adds `DAC_READ_SEARCH` so the non-root process can traverse the mounted music library
- **WireGuard:** uses `--privileged=true` instead (see dedicated decision below)
- **Nextcloud:** omits `--cap-drop=ALL` entirely — the entrypoint runs `rsync --chown` to copy the webroot on every start, which requires `CHOWN` capability; dropping all capabilities breaks startup

**Rationale:**
- Capability dropping limits the blast radius of a container escape. A compromised container without `NET_RAW`, `SYS_ADMIN`, `DAC_OVERRIDE`, etc. cannot pivot to the host as effectively.
- `no-new-privileges` prevents setuid binaries inside the container from acquiring capabilities after startup.
- These flags are validated by the manual container security test suite (`scripts/test_container_security.sh`) before deployment or after hardening changes.

**How to apply:**
- New service containers default to `--cap-drop=ALL --security-opt=no-new-privileges:true`.
- Before adding `--cap-add=<CAP>`, verify it is strictly required by testing the container without it (see `TEST-04` for Traefik as a reference pattern).
- If a container image uses `gosu`, `su-exec`, or `rsync --chown` in its entrypoint, test with `--cap-drop=ALL` first and check logs for `Operation not permitted` errors.

---

## Decision: WireGuard Uses `--privileged=true` (Exception to Cap-Drop Pattern)

**Decision:** The WireGuard container runs with `--privileged=true` rather than the standard `--cap-drop=ALL` + selective `--cap-add` pattern.

**Rationale:**
- WireGuard requires loading the `wireguard` kernel module (`SYS_MODULE`), configuring network interfaces (`NET_ADMIN`), raw socket access (`NET_RAW`), and writing sysctl values — a combination that requires a superset of named capabilities that is impractical to enumerate precisely.
- The linuxserver WireGuard image also uses `iptables`/`nftables` for NAT and routing, which require additional caps beyond `NET_ADMIN`.
- `--privileged=true` is the standard approach for WireGuard containers and is accepted practice for VPN tunnelling containers that must interact with kernel networking subsystems.

**How to apply:**
- The WireGuard template (`roles/vpn/templates/wireguard.sh.j2`) uses only `--privileged=true` — do not add `--cap-drop=ALL` or `--cap-add` flags alongside `--privileged`, as they are no-ops and create misleading documentation.
- Do not apply this exception to any other service role without equivalent justification.

---

## Decision: SSH Hardening Values

**Decision:** The `standard_ssh` role applies specific hardening values: `MaxAuthTries 3`, `LoginGraceTime 30`, `ClientAliveInterval 300`, `ClientAliveCountMax 2`, and `UsePAM no`.

**Rationale:**
- **MaxAuthTries 3:** Reduces the window for brute-force attempts while still allowing for minor key-agent mistakes. All hosts require key-based auth (PasswordAuthentication is disabled), so 3 attempts is sufficient.
- **LoginGraceTime 30:** Closes unauthenticated connections quickly. A 2-minute window (default) leaves the SSH daemon holding open connections that are never completed.
- **ClientAliveInterval 300 / ClientAliveCountMax 2:** Detects dead SSH sessions (e.g., crashed clients, idle tunnels) and terminates them after 10 minutes of no response. Prevents accumulation of orphaned connections.
- **UsePAM no:** PAM is not used for authentication on these hosts — all auth is via public key. Disabling PAM prevents accidental activation of PAM modules that could interfere with authentication flow.

**How to apply:**
- These values apply to all hosts via `standard_ssh`. Do not tune per-host unless a specific service requires it (e.g., a bastion host with higher MaxAuthTries).

---

## Decision: Container Launch Scripts Set `mode: "0700"`

**Decision:** All container launch scripts (e.g., `/usr/local/bin/postgres_container.sh`) are deployed with `mode: "0700"` (owner-only read/write/execute).

**Rationale:**
- Scripts contain plaintext credentials passed as environment variables (e.g., `--env POSTGRES_PASSWORD=...`). Restricting read access to root/owner prevents other users on the host from reading credentials via the script file.
- Scripts are only ever executed by systemd (running as root) or the Ansible controller (connecting as root). Group or world execute permission is not required.
- This aligns with the principle of least privilege: files containing or exposing secrets should be accessible only to the process that needs them.

**How to apply:**
- All new container launch scripts should use `mode: "0700"`.
- Templates that do not contain credentials (e.g., pure configuration files) may use `mode: "0644"`.

---

## Decision: Single Shared PostgreSQL 17 Container

**Decision:** Consolidate all databases (Nextcloud, Paperless, Semaphore) into one PostgreSQL 17 container, accessed across multiple isolated Podman networks.

**Rationale:**
- **Resource efficiency:** One container instance saves ~256 MB RAM compared to separate postgres instances. On a resource-constrained VM1 (8 GB total), this matters.
- **Simplified administration:** One `postgres_container` to manage, monitor, and upgrade instead of multiple. The `db_wrapper.sh` script creates all three databases and the shared superuser role; no per-service setup needed.
- **Network isolation without container isolation:** Services remain on isolated Podman networks (preventing DNS collisions), but backend databases are consolidated. This balances isolation and resource usage.
- **Backup simplicity:** One `pg_dumpall` captures all three databases atomically. Restore is straightforward: start postgres, restore one dump, done.

**Replaces:** The prior design of two separate containers:
- PostgreSQL 15 for Nextcloud + Paperless (on `nextcloud_container_net`)
- PostgreSQL 17 for Semaphore only (on `semaphore_container_net`)

**How to apply:**
- All services connect to the shared PostgreSQL 17 instance via Podman DNS (`postgres.dns.podman`).
- The `nextcloud` role creates and configures `postgres_container` as the shared instance; Semaphore does not manage a separate postgres container.
- Variable naming: `postgres_path` points to the one PostgreSQL 17 data directory. `semaphore_postgres_path` no longer exists.
- All three services use the same `postgres_database_user` and `postgres_database_user_password` for superuser access; databases are isolated by name (`nextcloud`, `paperless`, `semaphore`).

---

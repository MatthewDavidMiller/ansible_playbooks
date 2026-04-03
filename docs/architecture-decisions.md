# Architecture Decisions

This document records explicit design decisions and rejected alternatives for the maintained VM1 workflow.

---

## Rejected: Ansible Vault for Secrets Management

**Decision:** Do not use Ansible Vault to encrypt credentials in the git repository.

**Rationale:**

- Real inventory with credentials is managed externally in Semaphore, not in this repo.
- `example_inventory.yml` is a template and contains no live secrets.
- Vault would add coordination overhead without protecting an actual checked-in secret source.

---

## Rejected: `host_vars/` and `group_vars/` Directory Structure

**Decision:** Keep the inline inventory pattern rather than splitting variables across `host_vars/` and `group_vars/`.

**Rationale:**

- Semaphore manages inventory injection as one unit.
- A single inventory template is easier to document and easier to reason about.

---

## Rejected: Dedicated Patching Playbook

**Decision:** Do not create a separate patching playbook.

**Rationale:**

- The maintained flow is `update_homelab_vms.yml`.
- Creating a separate patch-only playbook would duplicate host selection and standard role execution.
- Semaphore scheduling is the source of truth for recurring runs.

---

## Decision: Cron Job Removal via `standard_cron`

**Decision:** The `standard_cron` role explicitly removes legacy patching cron jobs.

**Rationale:**

- Older cron-driven patch workflows should not coexist with Semaphore scheduling.
- The removal is part of the migration to a single scheduler model.

---

## Decision: Container Security Hardening (`--cap-drop=ALL`)

**Decision:** Maintained service containers run with `--cap-drop=ALL` and `--security-opt=no-new-privileges:true`, then add back only the capabilities they actually need.

**Exceptions and required caps:**

- **Traefik:** `NET_BIND_SERVICE`
- **Vaultwarden:** `NET_BIND_SERVICE`
- **Redis:** only the filesystem-related caps needed by its startup path
- **Nextcloud:** does not use `cap-drop=ALL` because its image entrypoint requires a broader default capability set

---

## Decision: SSH Hardening Values

**Decision:** `standard_ssh` applies the project's hardening defaults via a validated drop-in under `/etc/ssh/sshd_config.d/`.

**Rationale:**

- Keep host access key-only.
- Reduce brute-force and orphaned-session exposure.
- Centralize SSH tuning in one managed file.

---

## Decision: Root-Only Runtime Env Files Are Shell-Sourced

**Decision:** Sensitive runtime values are rendered to root-only env files under `secret_env_dir` and sourced by shell before `podman run`.

**Rationale:**

- Keeps secrets out of systemd `ExecStart=` lines.
- Avoids parser drift between systemd, shell, and Podman.
- Matches the validation covered by `scripts/test_shell_secret_env.sh`.

---

## Decision: Unencrypted Backups Are Acceptable For This Homelab

**Decision:** Keep VM1 backups unencrypted.

**Rationale:**

- The operational priority is low-friction recovery.
- The accepted tradeoff is documented.
- Hardening effort is focused on safer temp-file handling and reduced credential exposure.

---

## Decision: Single Shared PostgreSQL 17 Container

**Decision:** Consolidate Nextcloud, Paperless, and Semaphore into one PostgreSQL 17 container while giving each app its own role and password.

**Rationale:**

- Saves memory and operational overhead.
- Simplifies backup and restore.
- Preserves service isolation through separate Podman networks and per-service credentials.

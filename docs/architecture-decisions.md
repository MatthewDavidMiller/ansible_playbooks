# Architecture Decisions

This document records explicit design decisions and rejected alternatives for the maintained VM1 workflow.

---

## Rejected: Ansible Vault for Secrets Management

**Decision:** Do not use Ansible Vault to encrypt credentials in the git repository.

**Rationale:**

- Real inventory with credentials is managed externally in playbook-runner, not in this repo.
- Real inventory is injected by playbook-runner and is not stored in this repository.
- Vault would add coordination overhead without protecting an actual checked-in secret source.

---

## Rejected: `host_vars/` and `group_vars/` Directory Structure

**Decision:** Keep the inline inventory pattern rather than splitting variables across `host_vars/` and `group_vars/`.

**Rationale:**

- playbook-runner manages inventory injection as one unit.
- A single externally managed inventory is easier to document and reason about.

---

## Rejected: Dedicated Patching Playbook

**Decision:** Do not create a separate patching playbook.

**Rationale:**

- The maintained flow is `update_homelab_vms.yml`.
- Creating a separate patch-only playbook would duplicate host selection and standard role execution.
- playbook-runner scheduling is the source of truth for recurring runs. OS patching is a weekly playbook-runner schedule of `update_homelab_vms.yml`, which applies every available package update during convergence and then reboots.
- OS packages are not pinned. They come from the signed Rocky Linux repositories, unlike container images, which are digest-locked in `artifacts/containers.lock.yml`.

---

## Decision: Cron Job Removal via `standard_cron`

**Decision:** The `standard_cron` role explicitly removes legacy patching cron jobs.

**Rationale:**

- Older cron-driven patch workflows should not coexist with playbook-runner scheduling.
- The removal is part of the migration to a single scheduler model.

---

## Decision: Container Security Hardening (`--cap-drop=ALL`)

**Decision:** Maintained service containers run with `--cap-drop=ALL` and `--security-opt=no-new-privileges:true`, then add back only the capabilities they actually need.

**Exceptions and required caps:**

- **Traefik:** `NET_BIND_SERVICE`
- **Vaultwarden:** `NET_BIND_SERVICE`

---

## Decision: SSH Hardening Values

**Decision:** `standard_ssh` applies the project's hardening defaults via a validated drop-in under `/etc/ssh/sshd_config.d/`.

**Rationale:**

- Keep host access key-only.
- Reduce brute-force and orphaned-session exposure.
- Keep PAM session/account controls available while password and challenge-response authentication remain disabled.
- Centralize SSH tuning in one managed file.

---

## Decision: Traefik Dashboard Defense in Depth

**Decision:** The Traefik dashboard requires both management-source IP allowlisting and BasicAuth.

**Rationale:**

- The dashboard is an administrative surface exposed through public HTTPS entrypoints.
- Source allowlists reduce exposure, while BasicAuth prevents allowlist mistakes from becoming unauthenticated access.

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

## Decision: Single Shared PostgreSQL 17 Container (retired)

**Decision:** Consolidate Nextcloud and Paperless into one PostgreSQL 17 container while giving each app its own role and password.

**Status:** Retired with the Nextcloud stack; see [Nextcloud, Paperless, PostgreSQL and Redis Retire](#decision-nextcloud-paperless-postgresql-and-redis-retire).

**Rationale:**

- Saves memory and operational overhead.
- Simplifies backup and restore.
- Preserves service isolation through separate Podman networks and per-service credentials.

---

## Decision: First-Party Images Skip the 24-Hour Age Gate

**Decision:** An image this project builds and releases itself is exempt from the review tool's 24-hour minimum image age. The lock entry opts in with `first_party: true`, which the tool accepts only for images under `ghcr.io/matthewdavidmiller/`.

**Rationale:**

- The age gate protects against a compromised or broken *upstream* release by giving the wider community a day to notice it. A first-party image has no upstream; waiting a day after our own release only delays a fix we chose to ship.
- The release is gated before it is pushed: `make release` in the image's repository runs its full test suite and its runtime tests under VM1's container flags.
- The exemption is explicit per entry and confined to our own namespace, so a third-party image cannot inherit it, and every other control (digest pin, Trivy scan, runtime tests) still applies.

---

## Decision: playbook-runner Replaces Semaphore

**Decision:** The Ansible web UI and scheduler on VM1 is playbook-runner, a first-party Rust program, and the `semaphore` role was removed. Semaphore, its PostgreSQL database and role, its backend-network membership, and its backup job no longer exist.

**Rationale:**

- This project used a small part of Semaphore: an external inventory, vault passwords and SSH keys, manual runs, and one weekly schedule. A purpose-built tool does that with far less code to trust.
- playbook-runner needs no database, so the shared PostgreSQL container serves only Nextcloud and Paperless and Semaphore's backend-network access is gone.
- It has no third-party Rust crates, encrypts every secret and inventory at rest with a master key held outside the data volume, and carries its Ansible collections in the image so a run never downloads anything.
- The image is first-party, so it follows the exemption above.

## Decision: music-server Replaces Navidrome

**Decision:** Music streaming on VM1 moves from Navidrome to music-server, a first-party Rust Subsonic server. It ran beside Navidrome on its own route until play:Sub had been checked against it; the `navidrome` role was then removed, and a one-shot playbook (since deleted) cleaned the old install off VM1.

**Rationale:**

- The project used a small part of Navidrome: play:Sub over the Subsonic API, playlists, and transcoding for mobile data. A purpose-built server does that with far less code to trust.
- It has no third-party Rust crates and no database. Per-user data is sealed under a master key held outside the data volume.
- Accounts are declared in the inventory (a Vault list rendered into a Podman secret), not created by hand in a web UI.
- ffmpeg, from the official Alpine image, is the one third-party program in the image. It runs only as a supervised subprocess.
- The image is first-party, so it follows the first-party image exemption.
- No history is migrated from `navidrome.db`; that would need a SQLite parser for a one-time import.

---

## Decision: Nextcloud, Paperless, PostgreSQL and Redis Retire

**Decision:** The previous file service (Nextcloud), Paperless NGX, and the PostgreSQL and Redis containers that served only those two are removed from `vm1.yml`. homedrive holds the files. A one-shot playbook removed what the roles had left on VM1, and a helper script moved the inventory off their variables; both were deleted after they had run and are in the git history.

**Rationale:**

- homedrive is first-party, verified end to end, and its import of the previous service was proved byte for byte before anything was removed.
- PostgreSQL and Redis served nothing else once Semaphore (and its database) went, so they retire with the two applications instead of becoming a role of their own.
- Starting the Nextcloud container relabels every file in its data tree (`:Z`), which changes each file's change time. While it ran, that invalidated the final check's hash cache and touched a tree no longer written to. The stack was held stopped (`nextcloud_stack_deploy`, default off) from the end of the migration until the roles were removed.
- The three daily service backups go only to homedrive. Their Nextcloud branches, the occ scan helper, and the Borg backup of the Nextcloud files went with the service.
- No Paperless export was made into homedrive: its documents are in the Borg archives of the nightly export, which are kept. Neither those archives nor the older `nextcloud_backup-*` archives are pruned by anything.

**Consequences:**

- The data disk is mounted by the `data_disk` role under `data_disk` and `data_disk_mount_path` (renamed from `nextcloud_disk` and `nextcloud_disk_mount_path`); the account the backups and the Music export use is `homedrive_main_user` (renamed from `nextcloud_homelab_user`).
- The backup role only mounts the backup disk and makes sure its Borg repository exists.
- The retirement playbook keeps all data unless a typed confirmation and a per-data flag are given, and never removes the Borg repository inside `nextcloud_path`.

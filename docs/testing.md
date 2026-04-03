# Testing

## CI/CD Pipeline

Checks run automatically on every `git commit` via the local pre-commit hook at `hooks/pre-commit`.

**Install the hook:**

```bash
git config core.hooksPath hooks
```

**What runs:**

1. `ansible-lint`
2. `scripts/test_supply_chain_policy.sh`
3. `ansible-playbook --syntax-check` for the maintained playbooks

`scripts/test_container_security.sh` remains a manual validation step because it pulls container images and can take several minutes.

---

## Quick Start

```bash
cd /home/matthew/matt_dev/ansible_playbooks
XDG_CACHE_HOME=/tmp/.cache ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-lint
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i example_inventory.yml vm1.yml
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i example_inventory.yml homelab_vms.yml
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i example_inventory.yml update_homelab_vms.yml
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i example_inventory.yml reboot_vms.yml
bash scripts/test_shell_secret_env.sh
bash scripts/test_supply_chain_policy.sh
python3 scripts/promote_artifacts.py --check-tools
python3 scripts/promote_artifacts.py --service traefik
bash scripts/test_container_security.sh 2>&1 | tee /tmp/container_test_results.txt
grep -E "^(PASS|FAIL|WARN|INFO)" /tmp/container_test_results.txt
```

> `:Z` SELinux volume relabel flags are intentionally omitted from the local container tests.

---

## Container Security Testing

The script validates the current VM1 hardening profile:

1. PostgreSQL starts with `--cap-drop=ALL`, `--shm-size=256m`, and the expected ownership.
2. PostgreSQL role isolation works: per-service roles can use their own databases and should not have cross-database access by default.
3. Redis starts with the minimal filesystem capabilities it still needs.
4. Nextcloud starts with `no-new-privileges` and without `cap-drop=ALL`, matching the image entrypoint requirement.
5. Traefik still requires `NET_BIND_SERVICE` under a real kernel.
6. Paperless NGX starts with its reduced capability set and without privilege errors.
7. Vaultwarden starts with `NET_BIND_SERVICE` and `SIGNUPS_ALLOWED=false`.
8. Semaphore starts with `cap-drop=ALL` and strict SSH host-key checking args.
9. Navidrome starts as explicit non-root UID/GID `33:33` with `cap-drop=ALL`.

By default the script now reads the approved image refs from `artifacts/containers.lock.yml`, converts them to digest-pinned `repo@sha256:...` refs, and tests those exact images. It still accepts image override env vars when you need to test a candidate image before writing it into the lock file:

```bash
TRAEFIK_IMAGE=public.ecr.aws/docker/library/traefik@sha256:171c9c3565b29f6c133f1c1b43c5d4e5853415198e9e1078c001f8702ff66aec \
POSTGRES_IMAGE=public.ecr.aws/docker/library/postgres@sha256:b994732fcf33f73776c65d3a5bf1f80c00120ba5007e8ab90307b1a743c1fc16 \
REDIS_IMAGE=public.ecr.aws/docker/library/redis@sha256:009cc37796fbdbe1b631b4cc0582bed167e5e403ed8bcd06f77eb6cb5aeb6f93 \
NEXTCLOUD_IMAGE=public.ecr.aws/docker/library/nextcloud@sha256:2176a451aa8fbd9f003a3d745978377e9a5213850e0181f4bcb24be63885175b \
PAPERLESS_IMAGE=ghcr.io/paperless-ngx/paperless-ngx@sha256:4b05bcd28e6923768000b5d247cbf2c66fd49bdc3f3b05955bd4f6790a638b01 \
NAVIDROME_IMAGE=docker.io/deluan/navidrome@sha256:b14a6acb5cd5ee73f3a13d63d8d68ede82dedb796aa522fbada94769d990cf0b \
VAULTWARDEN_IMAGE=ghcr.io/dani-garcia/vaultwarden@sha256:43498a94b22f9563f2a94b53760ab3e710eefc0d0cac2efda4b12b9eb8690664 \
SEMAPHORE_IMAGE=public.ecr.aws/semaphore/server@sha256:17678757e65621aaf27bffbfe8caa00fb85857d60124b49876a5326e3f3dfac9 \
bash scripts/test_container_security.sh
```

## Image Review Tooling

`scripts/promote_artifacts.py` performs the immutable-image review steps:

1. Resolve each `upstream_ref` to a digest with `skopeo`.
2. Verify signatures with `cosign` when `signature_required: true` and the lock entry includes pinned signer metadata.
3. Scan for `HIGH` and `CRITICAL` findings with `trivy`.
4. Optionally write the approved digest back to `artifacts/containers.lock.yml`.

The script prefers native `skopeo`, `cosign`, and `trivy` binaries. If one is missing, it falls back to a pinned official container image for that tool via `podman` or `docker`.

Check the current tool path selection:

```bash
python3 scripts/promote_artifacts.py --check-tools
```

Full review for one or more services:

```bash
bash scripts/review_container_updates.sh --service traefik
bash scripts/review_container_updates.sh --service postgres --service redis
```

For the full workflow and install references, see [guides/container-image-updates.md](guides/container-image-updates.md).

---

## Shell-Sourced Env Regression Testing

`scripts/test_shell_secret_env.sh` renders the affected templates locally and checks the parser-specific invariants for the secret env migration:

- Special-character values containing `;`, backslashes, single quotes, and double quotes survive `bash -lc 'set -a; . file; env'` unchanged.
- Service launch scripts no longer use `--env-file`.
- Service launch scripts source the correct file under `secret_env_dir` before `podman run`.
- Each sourced variable expected by a container is passed with `--env VAR_NAME`.
- Service launch scripts use `podman run --pull=never` and no longer call standalone `podman pull`.
- Local backup scripts for Navidrome, Vaultwarden, and Semaphore render ownership-preserving `install` commands for the Nextcloud data tree when `backup_local: true`.

Run it directly:

```bash
bash scripts/test_shell_secret_env.sh
```

---

## Expected Outcomes

- `ansible-lint` and `--syntax-check` complete without errors.
- `scripts/test_shell_secret_env.sh` reports `PASS` for shell quoting and generated launch artifact checks.
- `scripts/test_supply_chain_policy.sh` reports `PASS` for immutable image refs, approved collection installs, and pinned provisioning inputs.
- `python3 scripts/promote_artifacts.py --check-tools` reports either native binaries or the pinned container fallback for `skopeo`, `cosign`, and `trivy`.
- VM1 container tests report `PASS` for PostgreSQL, Redis, Nextcloud, Traefik, Paperless, Vaultwarden, Semaphore, and Navidrome.

---

## Notes

- Because VM1 now uses shell-sourced root-only env files under `secret_env_dir`, run `scripts/test_shell_secret_env.sh` after touching env templates or launch scripts so parser regressions are caught before deployment.
- Run `python3 scripts/promote_artifacts.py --check-tools` after provisioning a new control node so missing native binaries or missing container-engine fallback are caught early.
- Run `scripts/test_supply_chain_policy.sh` after changing image refs, bootstrap tooling, or dependency manifests.
- Use `bash scripts/review_container_updates.sh --service <name>` when updating `artifacts/containers.lock.yml` so digest resolution, signature verification, scanning, and runtime hardening checks happen in one sequence.
- Semaphore host verification depends on real `semaphore_known_hosts` content in inventory; the container security script validates the runtime SSH args shape, not your real host keys.
- VM1 backups remain intentionally unencrypted for this homelab. The hardening focus is on safer temp-file handling and reduced credential exposure, not backup-at-rest encryption.

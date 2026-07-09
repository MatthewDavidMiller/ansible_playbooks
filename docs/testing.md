# Testing

## CI/CD Pipeline

Checks run automatically on every `git commit` via the local pre-commit hook at `hooks/pre-commit`.

**Install the hook:**

```bash
git config core.hooksPath hooks
```

**What runs:**

1. `scripts/test_supply_chain_policy.sh`
2. `scripts/test_dev_vm_packages.sh` (policy + Rocky 10 / EPEL dnf depsolve for `dev_vm`)
3. `ansible-lint`
4. `ansible-playbook --syntax-check` for the maintained playbooks (`vm1.yml`, `vm2.yml`, `homelab_vms.yml`, `update_homelab_vms.yml`, `reboot_vms.yml`)

`scripts/test_container_security.sh` remains a manual validation step because it pulls container images and can take several minutes.

Offline or no-container commits can skip the network depsolve only:

```bash
DEV_VM_PACKAGE_DEPSOLVE=0 git commit ...
```

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
bash scripts/test_dev_vm_packages.sh
python3 scripts/promote_artifacts.py --check-tools
python3 scripts/promote_artifacts.py --service traefik
bash scripts/test_container_security.sh 2>&1 | tee /tmp/container_test_results.txt
grep -E "^(PASS|FAIL|WARN|INFO)" /tmp/container_test_results.txt
bash scripts/test_container_security.sh semaphore
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

For faster debugging, pass one or more targets instead of running the full suite:

```bash
bash scripts/test_container_security.sh static
bash scripts/test_container_security.sh semaphore
bash scripts/test_container_security.sh postgres redis
```

```bash
TRAEFIK_IMAGE=public.ecr.aws/docker/library/traefik@sha256:d6858791f9e74df44ca4014166647c41cdc2abd3bf2a71b832ca4e1c6a91b257 \
POSTGRES_IMAGE=public.ecr.aws/docker/library/postgres@sha256:2203e6282d9e7de7c24d7da234e2a744fb325df366a3fd8ed940e8abbee39527 \
REDIS_IMAGE=public.ecr.aws/docker/library/redis@sha256:0a972391db0b24ec336e35d1bc98b237237e26f82bf5120cf2f6b1688d1df973 \
NEXTCLOUD_IMAGE=public.ecr.aws/docker/library/nextcloud@sha256:e15ff2ff02d04bf272940bb63f2157599bc9440d45b688cc60f09b72be7ae717 \
PAPERLESS_IMAGE=ghcr.io/paperless-ngx/paperless-ngx@sha256:6c86cad803970ea782683a8e80e7403444c5bf3cf70de63b4d3c8e87500db92f \
NAVIDROME_IMAGE=docker.io/deluan/navidrome@sha256:c4b5cb36a790b3eb63ca6a68bbe2fe149c2d7fa2e586f7a480e61db630e6664b \
VAULTWARDEN_IMAGE=ghcr.io/dani-garcia/vaultwarden@sha256:d626d04934cd1192ad8ced1adb975099fca78cec33ab467d2d3c923cde7f3b0c \
SEMAPHORE_IMAGE=public.ecr.aws/semaphore/server@sha256:f6651f30d5bf962afe13831b579c3e0f02a13a45735f852b4de3225d98859c8e \
bash scripts/test_container_security.sh
```

## Image Review Tooling

`scripts/promote_artifacts.py` performs the immutable-image review steps:

1. Resolve each `upstream_ref` to a digest with `skopeo`.
2. Verify signatures with `cosign` when `signature_required: true` and the lock entry includes pinned signer metadata.
3. Scan for unfixed `MEDIUM`, `HIGH`, and `CRITICAL` findings with `trivy`, enforcing explicit lock-file exceptions when no newer upstream image is available.
4. Optionally write the approved digest back to `artifacts/containers.lock.yml`.

Trivy output is written to `logs/container-vulnerability-findings.log`; `logs/` is git ignored.
If present, local files at `logs/.trivyignore` and `logs/trivy-vex.json` are passed to Trivy for private accepted-risk review. Real ignore/VEX content must stay out of the public repo.

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

## dev_vm Package Resolution Testing

`scripts/test_dev_vm_packages.sh` guards the VM2 workstation package baseline against the class of failure that breaks `dnf` depsolve on Rocky 10 + EPEL when CRB is missing (for example EPEL `yamllint` needing `python3.12dist(pathspec)` from CRB).

Checks:

1. **Policy:** pure-Python CLIs (`yamllint`, `ansible-lint`, `pre-commit`) must live in `dev_vm_python_user_packages` (pip `--user`), not `dev_vm_packages` (dnf).
2. **Policy:** dnf and pip lists must not overlap; required baseline dnf packages remain present.
3. **Regression:** with CRB disabled, EPEL `yamllint` must fail depsolve (original failure mode still exists upstream).
4. **Regression:** with CRB enabled (matching `standard_update_packages`), EPEL `yamllint` must resolve.
5. **Depsolve:** in a clean `rockylinux:10` container with EPEL + CRB, `dnf --assumeno install` must resolve `dev_vm_packages` and Docker CE packages from the same baseurl the role configures.

Run it directly:

```bash
bash scripts/test_dev_vm_packages.sh
DEV_VM_PACKAGE_DEPSOLVE=0 bash scripts/test_dev_vm_packages.sh   # policy only
```

Requires `podman` or `docker` for the depsolve step, plus network access to Rocky, EPEL, and Docker CE repositories.

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
- `scripts/test_supply_chain_policy.sh` also enforces core SSH, firewall, proxy, backup, and secret-rendering guardrails.
- `scripts/test_dev_vm_packages.sh` reports `PASS` for pip-vs-dnf package policy, the EPEL-without-CRB yamllint regression fixture, and Rocky 10 + EPEL + CRB dependency resolution of `dev_vm_packages` / `dev_vm_docker_packages`.
- `python3 scripts/promote_artifacts.py --check-tools` reports either native binaries or the pinned container fallback for `skopeo`, `cosign`, and `trivy`.
- VM1 container tests report `PASS` for PostgreSQL, Redis, Nextcloud, Traefik, Paperless, Vaultwarden, Semaphore, and Navidrome.

---

## Notes

- Because VM1 now uses shell-sourced root-only env files under `secret_env_dir`, run `scripts/test_shell_secret_env.sh` after touching env templates or launch scripts so parser regressions are caught before deployment.
- Run `python3 scripts/promote_artifacts.py --check-tools` after provisioning a new control node so missing native binaries or missing container-engine fallback are caught early.
- Run `scripts/test_supply_chain_policy.sh` after changing image refs, bootstrap tooling, or dependency manifests.
- Run `scripts/test_dev_vm_packages.sh` after changing `roles/dev_vm/defaults/main.yml` package lists, VM2 EPEL/CRB settings, or Docker CE repository configuration. The depsolve step uses a Rocky 10 container with EPEL + CRB to mirror `standard_update_packages` on VM2.
- Run `scripts/test_supply_chain_policy.sh` and `bash scripts/test_container_security.sh static` after changing container-network tasks. These checks cover route-owned proxy networks and the deferred migration path used when staged VM1 runs would otherwise interrupt Semaphore.
- Use `bash scripts/review_container_updates.sh --service <name>` when updating `artifacts/containers.lock.yml` so digest resolution, signature verification, scanning, and runtime hardening checks happen in one sequence.
- Semaphore host verification depends on real `semaphore_known_hosts` content in inventory; the container security script validates the runtime SSH args shape, not your real host keys.
- VM1 backups remain intentionally unencrypted for this homelab. The hardening focus is on safer temp-file handling and reduced credential exposure, not backup-at-rest encryption.

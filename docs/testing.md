# Testing

## CI/CD Pipeline

Checks run automatically on every `git commit` via the local pre-commit hook at `hooks/pre-commit`.

**Install the hook:**

```bash
git config core.hooksPath hooks
```

**What runs:**

1. Supply-chain and static container policy checks
2. Python unit tests and bytecode compilation
3. ShellCheck and yamllint
4. Secret-template rendering regression tests
5. `dev_vm` policy plus Rocky 10/EPEL dependency resolution using a digest-pinned test image
6. `ansible-lint` and syntax checks for every maintained playbook

The static portion of `scripts/test_container_security.sh` runs in the hook. Runtime container tests remain manual because they pull images and can take several minutes.
Runtime tests prefer Docker when both engines are installed, fall back to Podman automatically, and honor an explicit `DOCKER=/path/to/engine` override.

The Python suite includes mocked success and failure paths for artifact promotion, Proxmox provisioning, dynamic DNS, shared validation filters, and VM bootstrap behavior. It also executes the Nextcloud permission-normalization command against a temporary file tree to guard its single-pass and idempotent behavior.

The suite also guards failure recovery in deferred container-network migrations,
malformed Porkbun record responses, fail-closed Proxmox VM discovery, and atomic
artifact-lock replacement.

Container network reconciliation has dedicated guards in
`tests/test_ansible_regressions.py`. Every service role must reconcile the
networks it owns through the shared `container_network` role, with the expected
internal flag per network; no role outside `container_network` may run a
`podman network` command or parse inspect output itself. The shared role must
queue replacements during staged runs, force-remove before recreating during
immediate runs, and leave `reverse_proxy_deferred_route_networks` to the role
that owns them. The replacement decision itself is covered directly in
`tests/test_homelab_validation.py`, including the legacy `Internal` key
spelling, subnet drift, and unreadable inspect output.

Route proxy addressing has dedicated guards in `tests/test_ansible_regressions.py`. Every container on a route proxy network must request a static address that Podman can assign, Traefik's `route_proxy_traefik_ips` address must differ from the service address on the same network, and `route_proxy_container_ips` must match the address the service launch script requests. The checks read the launch scripts and role defaults, so a new proxied service is covered once it pins an address.

Local Nextcloud backups have dedicated guards in `tests/test_ansible_regressions.py`. Every template that writes into the Nextcloud user files tree must call the managed `nextcloud_scan_path.sh` helper, must report helper failures instead of discarding them with `|| true`, and must install dumps using `nextcloud_user_files_file_mode` so the mode survives the `nextcloud` role's normalization. The helper itself is checked for serialized scans, retries, an explicit `occ` path and working directory, the `nextcloud_uid:nextcloud_gid` runtime user, and detection of semantic failures that `occ files:scan` reports with a zero exit status. Because every caller is a cron job, the helper is also checked for a pinned `PATH`, `HOME`, and locale, absolute paths for every binary it calls, a `timeout` around `occ`, and the `occ info:file` confirmation that the scanned path really reached the file cache. A separate check holds the `nextcloud` role to the `container_file_t` rule for its volume and to a `restorecon` of the data tree that does not force the range, since `-F` would strip the MCS categories podman's `:Z` applied. The backup-template checks discover callers by content, so a new service backup script is covered without editing the tests.

Offline or no-container commits can skip the network depsolve only:

```bash
DEV_VM_PACKAGE_DEPSOLVE=0 git commit ...
```

---

## Quick Start

```bash
cd /home/matthew/matt_dev/ansible_playbooks
XDG_CACHE_HOME=/tmp/.cache ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-lint
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i vm1,vm2,homelab, vm1.yml
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i vm1,vm2,homelab, homelab_vms.yml
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i vm1,vm2,homelab, update_homelab_vms.yml
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote ansible-playbook --syntax-check -i vm1,vm2,homelab, reboot_vms.yml
bash scripts/test_shell_secret_env.sh
bash scripts/test_supply_chain_policy.sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/promote_artifacts.py --validate-policy
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

1. Inspect each `upstream_ref` once with `skopeo` to resolve its digest and creation timestamp.
2. Verify signatures with `cosign` when `signature_required: true` and the lock entry includes pinned signer metadata.
3. Require a changed image's recorded creation time to be at least 24 hours old.
4. Scan for fix-available `MEDIUM`, `HIGH`, and `CRITICAL` findings with `trivy`. Scanner/tool errors fail closed.
5. Require a reviewed, maximum-30-day public exception for non-Critical findings. Critical findings require an exact local service/digest/CVE acceptance unless every candidate Critical finding is already present in the currently approved digest; that no-regression case promotes the eligible newer image.
6. Optionally write the approved digest back to `artifacts/containers.lock.yml`.

Lock-file and Critical-acceptance digests must be complete lowercase `sha256:` values; malformed metadata fails before registry or scanner work begins.

Trivy output is written to `logs/container-vulnerability-findings.log`; `logs/` is git ignored.
Critical findings cannot be hidden by a broad Trivy ignore or VEX file. Use `logs/vulnerability-acceptance.yml` for exact Critical acceptances; real acceptance data must stay out of the public repo. `artifacts/vulnerability-acceptance.example.yml` is the schema reference.

The script prefers native `skopeo`, `cosign`, and `trivy` binaries. If one is missing, it falls back to a pinned, capability-dropped, read-only container via Podman or Docker.

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
2. **Policy:** dnf and pip lists must not overlap; required baseline dnf packages remain present, including the `rpi-omt-client` and `playlist_generator` system dependencies.
3. **Policy:** Hadolint matches `rpi-omt-client`'s version pin and is installed with a configured SHA-256 checksum.
4. **Regression:** with CRB disabled, EPEL `yamllint` must fail depsolve (original failure mode still exists upstream).
5. **Regression:** with CRB enabled (matching `standard_update_packages`), EPEL `yamllint` must resolve.
6. **Depsolve:** in the digest-pinned Rocky Linux 10 test image with EPEL + CRB, `dnf --assumeno install` must resolve the rootless-Podman `dev_vm_packages` baseline.

Run it directly:

```bash
bash scripts/test_dev_vm_packages.sh
DEV_VM_PACKAGE_DEPSOLVE=0 bash scripts/test_dev_vm_packages.sh   # policy only
```

Requires a working Podman or Docker engine for the depsolve step, plus network access to Rocky and EPEL repositories. VM2 itself provisions only rootless Podman.

---

## Shell-Sourced Env Regression Testing

`scripts/test_shell_secret_env.sh` renders the affected templates locally and checks the parser-specific invariants for the secret env migration:

- Special-character values containing `;`, backslashes, single quotes, and double quotes survive `bash -lc 'set -a; . file; env'` unchanged.
- Service launch scripts no longer use `--env-file`.
- Service launch scripts source the correct file under `secret_env_dir` before `podman run`.
- Each sourced variable expected by a container is passed with `--env VAR_NAME`.
- Service launch scripts use `podman run --pull=never` and no longer call standalone `podman pull`.
- Local backup scripts for Navidrome, Vaultwarden, and Semaphore render ownership-preserving `install` commands for the Nextcloud data tree when `backup_local: true`.
- The shared targeted Nextcloud scan helper renders the expected UID/GID, absolute `occ` path, serialization, retry, and semantic-error checks, and every local service backup calls it.

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
- `scripts/test_dev_vm_packages.sh` reports `PASS` for pinned-validator package policy, the EPEL-without-CRB regression fixture, and Rocky 10 + EPEL + CRB resolution of the rootless-Podman package baseline.
- `python3 scripts/promote_artifacts.py --check-tools` reports either native binaries or the pinned container fallback for `skopeo`, `cosign`, and `trivy`.
- VM1 container tests report `PASS` for PostgreSQL, Redis, Nextcloud, Traefik, Paperless, Vaultwarden, Semaphore, and Navidrome.

---

## Notes

- Because VM1 now uses shell-sourced root-only env files under `secret_env_dir`, run `scripts/test_shell_secret_env.sh` after touching env templates or launch scripts so parser regressions are caught before deployment.
- Run `python3 scripts/promote_artifacts.py --check-tools` after provisioning a new control node so missing native binaries or missing container-engine fallback are caught early.
- Run `scripts/test_supply_chain_policy.sh` after changing image refs, bootstrap tooling, or dependency manifests.
- Run `scripts/test_dev_vm_packages.sh` after changing `roles/dev_vm/defaults/main.yml` package lists or VM2 EPEL/CRB settings. The depsolve step uses the immutable Rocky test image with EPEL + CRB to mirror `standard_update_packages` on VM2.
- Run `scripts/test_supply_chain_policy.sh` and `bash scripts/test_container_security.sh static` after changing container-network tasks. These checks cover route-owned proxy networks and the deferred migration path used when staged VM1 runs would otherwise interrupt Semaphore.
- Use `bash scripts/review_container_updates.sh --service <name>` when updating `artifacts/containers.lock.yml` so digest resolution, signature verification, scanning, and runtime hardening checks happen in one sequence.
- Semaphore host verification depends on real `semaphore_known_hosts` content in inventory; the container security script validates the runtime SSH args shape, not your real host keys.
- VM1 backups remain intentionally unencrypted for this homelab. The hardening focus is on safer temp-file handling and reduced credential exposure, not backup-at-rest encryption.

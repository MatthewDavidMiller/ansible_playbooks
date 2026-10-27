# Testing

## Local Validation Pipeline

Every check in this repository runs inside a pinned Alpine toolbox image built from [`tools/toolbox/Dockerfile`](../tools/toolbox/Dockerfile). Rootless Podman is the only thing a workstation needs: `ansible-core`, `ansible-lint`, `yamllint`, `shellcheck`, Python, and the collections pinned in `collections/requirements.yml` all live in the image, so every commit is validated against the same tool versions no matter which machine runs the gate.

**Set up once:**

```bash
make install
```

That builds the toolbox image and points `core.hooksPath` at `hooks/`, so the gate runs on every `git commit`. Skip a run with `git commit --no-verify`.

**Targets:**

| Command | What it runs |
|---|---|
| `make lint` | Bash syntax, ShellCheck, yamllint, Python compilation, `ansible-lint`, and `--syntax-check` for every maintained playbook |
| `make test` | Everything in `make lint`, plus supply-chain policy, artifact promotion policy, Python unit tests, secret-template rendering, and the static container policy checks |
| `make test-full` | Everything in `make test`, then the runtime container tests (see [below](#the-one-gate-that-runs-outside-the-toolbox)) |
| `make shell` | Interactive shell inside the toolbox |
| `make clean` | Remove toolbox images, validator caches, and `__pycache__` directories |

`make test` is what the pre-commit hook runs. Runtime container tests stay out of it because they pull the locked service images and start real containers; run `make test-full` after changing container flags, launch templates, or image pins.

### How the toolbox runs

`scripts/toolbox.sh` builds the image on first use and execs straight through when it is already inside one, so the hook → `test-local.sh` → `lint.sh` chain runs in a single container rather than nesting three.

- The base image is the digest-pinned Alpine entry in [`artifacts/test_images.lock.yml`](../artifacts/test_images.lock.yml), the same lock the runtime container tests read. Bumping the toolbox base is therefore an ordinary reviewed lock-file change, not a second pin to keep in sync.
- The image tag is a content hash of the Dockerfile, `tests/requirements-dev.txt`, `collections/requirements.yml`, and that base digest. Changing any pin names a different image, rebuilds on the next gate run, and drops the image it replaces.
- The repository is bind-mounted at its own absolute path, and so is `/tmp`. Containers started from inside the toolbox run on the host engine and are handed bind-mount paths, which the host resolves in its own filesystem — any other mount point would silently mount the wrong directory.
- The container runs as the invoking user, so a gate leaves no root-owned files in the working tree.
- The host's Podman API socket is mounted and `CONTAINER_HOST` points at it, so the image-review tool fallbacks can start their pinned containers. The client in the image is `podman-remote`, installed as `podman`, which speaks Podman's own API rather than the Docker-compatible one. Enable the socket with `systemctl --user enable --now podman.socket`.
- `PODMAN` names a different binary if `podman` is not the one to use. It is word-split, so it takes a prefix.

### Why rootless, and why only Podman

Rootless Podman is a requirement, not a preference. `scripts/toolbox.sh` asks the engine (`podman info --format '{{.Host.Security.Rootless}}'`) and refuses to run rootful rather than adapting to it, because a rootful gate writes root-owned files into your working tree.

Under rootless Podman the container's root is you, and every other uid inside comes out of your subuid range. So the toolbox runs with both `--userns=keep-id`, which maps your host uid to itself inside the namespace, and `--user "$(id -u):$(id -g)"`, which is what that mapping makes mean you. Get this pair wrong and nothing announces it: the gate runs as something like uid `100999` and dies partway through on a permission error inside a tree you own.

Supporting Docker as well meant detecting which engine and which mode was in use and mapping uids differently for each combination — and one of those detections is why `podman-docker`, which puts a `docker` command on `PATH` that is Podman, produced exactly the silent failure above. One engine, one mapping, checked rather than guessed. `tests/test_ansible_regressions.py` fails the build if a Docker path or a different uid mapping reappears in the pipeline scripts.

### The one gate that runs outside the toolbox

The runtime container suite is the exception. Everything else only needs somewhere to run; this one needs a local Podman rather than a client talking to one over the socket.

Its fixtures are host directories owned by the subuids its containers run as, so creating and reclaiming them means entering your user namespace with `podman unshare chown`. The remote client refuses that outright — `cannot use command "podman unshare" with the remote podman client` — because a user namespace is local to the machine holding the files.

`scripts/run-runtime-container-tests.sh` therefore runs the suite on the host, and `make test-full` calls it, so this needs no flag. It is the only place in this repository that wants anything on the host beyond Podman itself — `python3` with PyYAML, to read the pinned digests out of the lock files — and it says so and stops rather than failing obscurely if that is missing.

The Python suite includes mocked success and failure paths for artifact promotion, Proxmox provisioning, dynamic DNS, shared validation filters, and VM bootstrap behavior. It also executes the Nextcloud permission-normalization command against a temporary file tree to guard its single-pass and idempotent behavior, and to confirm it reports a count of the files it fixed rather than a line for each one.

The suite also guards failure recovery in deferred container-network migrations,
malformed Porkbun record responses, fail-closed Proxmox VM discovery, and atomic
artifact-lock replacement.

Container network reconciliation has dedicated guards in
`tests/test_ansible_regressions.py`. Every service role must reconcile the
networks it owns through the shared `container_network` role, with the expected
internal flag per network; no role outside `container_network` may run a
`podman network` command or parse inspect output itself. The shared role must
queue replacements during staged runs, preserve each queued network's internal
mode, force-remove before recreating during immediate runs, and leave
`reverse_proxy_deferred_route_networks` to the role that owns them. The
replacement decision itself is covered directly in
`tests/test_homelab_validation.py`, including exact internal/external mode,
the legacy `Internal` key spelling, subnet drift, and unreadable inspect output.

`tests/test_backup_proxmox_config.py` guards the standalone Proxmox backup's
fail-fast destination validation, private temporary files, exit-trap cleanup,
and archive-only remote retention filter.

Route proxy addressing has dedicated guards in `tests/test_ansible_regressions.py`. Every container on a route proxy network must request a static address that Podman can assign, Traefik's `route_proxy_traefik_ips` address must differ from the service address on the same network, and `route_proxy_container_ips` must match the address the service launch script requests. The checks read the launch scripts and role defaults, so a new proxied service is covered once it pins an address.

Local Nextcloud backups have dedicated guards in `tests/test_ansible_regressions.py`. Every template that writes into the Nextcloud user files tree must call the managed `nextcloud_scan_path.sh` helper, must report helper failures instead of discarding them with `|| true`, and must install dumps using `nextcloud_user_files_file_mode` so the mode survives the `nextcloud` role's normalization. The helper itself is checked for serialized scans, retries, an explicit `occ` path and working directory, the `nextcloud_uid:nextcloud_gid` runtime user, and detection of semantic failures that `occ files:scan` reports with a zero exit status. Because every caller is a cron job, the helper is also checked for a pinned `PATH`, `HOME`, and locale, absolute paths for every binary it calls, a `timeout` around `occ`, and the `occ info:file` confirmation that the scanned path really reached the file cache. A separate check holds the `nextcloud` role to the `container_file_t` rule for its volume and to a `restorecon` of the data tree that does not force the range, since `-F` would strip the MCS categories podman's `:Z` applied, and that counts its `-v` output through `wc -l` instead of returning a line per relabeled file. The backup-template checks discover callers by content, so a new service backup script is covered without editing the tests.

---

## Quick Start

The whole gate:

```bash
make test
```

Individual checks run in the toolbox too — `scripts/toolbox.sh` takes any command and runs it inside the image:

```bash
./scripts/toolbox.sh ansible-lint
./scripts/toolbox.sh ansible-playbook --syntax-check -i vm1,homelab, vm1.yml
./scripts/toolbox.sh bash scripts/test_supply_chain_policy.sh
./scripts/toolbox.sh bash scripts/test_shell_secret_env.sh
./scripts/toolbox.sh python3 -m unittest discover -s tests -p 'test_*.py'
./scripts/toolbox.sh python3 scripts/promote_artifacts.py --validate-policy
./scripts/toolbox.sh python3 scripts/promote_artifacts.py --check-tools
./scripts/toolbox.sh bash scripts/test_container_security.sh static
```

Or open a shell and run several in a row:

```bash
make shell
```

`XDG_CACHE_HOME`, `ANSIBLE_LOCAL_TEMP`, and `ANSIBLE_REMOTE_TEMP` are set in the image, so no environment prefixes are needed to keep validator caches out of the working tree.

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
8. Navidrome starts as explicit non-root UID/GID `33:33` with `cap-drop=ALL`.

By default the script now reads the approved image refs from `artifacts/containers.lock.yml`, converts them to digest-pinned `repo@sha256:...` refs, and tests those exact images. It still accepts image override env vars when you need to test a candidate image before writing it into the lock file:

The full suite is `make test-full`. For faster debugging, pass one or more targets to the wrapper instead:

```bash
./scripts/run-runtime-container-tests.sh vaultwarden
./scripts/run-runtime-container-tests.sh postgres redis
```

The `static` target needs no engine and is already part of `make test`.

The runtime suite runs on the host, so image override variables are set in the shell that invokes it:

```bash
TRAEFIK_IMAGE=public.ecr.aws/docker/library/traefik@sha256:d6858791f9e74df44ca4014166647c41cdc2abd3bf2a71b832ca4e1c6a91b257 \
POSTGRES_IMAGE=public.ecr.aws/docker/library/postgres@sha256:2203e6282d9e7de7c24d7da234e2a744fb325df366a3fd8ed940e8abbee39527 \
REDIS_IMAGE=public.ecr.aws/docker/library/redis@sha256:0a972391db0b24ec336e35d1bc98b237237e26f82bf5120cf2f6b1688d1df973 \
NEXTCLOUD_IMAGE=public.ecr.aws/docker/library/nextcloud@sha256:e15ff2ff02d04bf272940bb63f2157599bc9440d45b688cc60f09b72be7ae717 \
PAPERLESS_IMAGE=ghcr.io/paperless-ngx/paperless-ngx@sha256:6c86cad803970ea782683a8e80e7403444c5bf3cf70de63b4d3c8e87500db92f \
NAVIDROME_IMAGE=docker.io/deluan/navidrome@sha256:c4b5cb36a790b3eb63ca6a68bbe2fe149c2d7fa2e586f7a480e61db630e6664b \
VAULTWARDEN_IMAGE=ghcr.io/dani-garcia/vaultwarden@sha256:d626d04934cd1192ad8ced1adb975099fca78cec33ab467d2d3c923cde7f3b0c \
bash scripts/test_container_security.sh
```

`scripts/remove_semaphore_inventory.py` has its own tests (`tests/test_remove_semaphore_inventory.py`) that run on made-up inventories: previews print no values, the result parses to the original minus the Semaphore settings, comments and `!vault` blocks survive, and it refuses when a leftover reference or an unsupported layout would make the edit unsafe.

## Image Review Tooling

`scripts/promote_artifacts.py` performs the immutable-image review steps:

1. Inspect each `upstream_ref` once with `skopeo` to resolve its digest and creation timestamp.
2. Verify signatures with `cosign` when `signature_required: true` and the lock entry includes pinned signer metadata.
3. Select the newest release of the major line already pinned, holding newer majors back, and require a changed third-party image's recorded creation time to be at least 24 hours old (first-party images are exempt).
4. Scan for fix-available `MEDIUM`, `HIGH`, and `CRITICAL` findings with `trivy`. Scanner/tool errors fail closed.
5. Report non-Critical findings without blocking. A Critical the candidate introduces requires an exact local service/digest/CVE acceptance; Criticals already present in the currently approved digest are a no-regression update and promote.
6. Optionally write the approved digest back to `artifacts/containers.lock.yml`.

Lock-file and Critical-acceptance digests must be complete lowercase `sha256:` values; malformed metadata fails before registry or scanner work begins.

Trivy output is written to `logs/container-vulnerability-findings.log`; `logs/` is git ignored.
Critical findings cannot be hidden by a broad Trivy ignore or VEX file. Use `logs/vulnerability-acceptance.yml` for exact Critical acceptances; real acceptance data must stay out of the public repo. `artifacts/vulnerability-acceptance.example.yml` is the schema reference.

The script prefers native `skopeo`, `cosign`, and `trivy` binaries. If one is missing, it falls back to a pinned, capability-dropped, read-only container run with Podman.

The toolbox image carries none of those three binaries, so a review run inside it always takes the pinned-container fallback, which `podman-remote` starts on the host engine through the mounted API socket. Check the current tool path selection:

```bash
./scripts/toolbox.sh python3 scripts/promote_artifacts.py --check-tools
```

Full review for one or more services:

```bash
./scripts/toolbox.sh bash scripts/review_container_updates.sh --service traefik
./scripts/toolbox.sh bash scripts/review_container_updates.sh --service postgres --service redis
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
- Local backup scripts for Navidrome, Vaultwarden, playbook-runner, and music-server render ownership-preserving `install` commands for the Nextcloud data tree when `backup_local: true`.
- The shared targeted Nextcloud scan helper renders the expected UID/GID, absolute `occ` path, serialization, retry, and semantic-error checks, and every local service backup calls it.

It runs as part of `make test`. To run it alone:

```bash
./scripts/toolbox.sh bash scripts/test_shell_secret_env.sh
```

---

## Expected Outcomes

- `ansible-lint` and `--syntax-check` complete without errors.
- `scripts/test_shell_secret_env.sh` reports `PASS` for shell quoting and generated launch artifact checks.
- `scripts/test_supply_chain_policy.sh` reports `PASS` for immutable image refs, approved collection installs, and pinned provisioning inputs.
- `scripts/test_supply_chain_policy.sh` also enforces core SSH, firewall, proxy, backup, and secret-rendering guardrails.
- `scripts/promote_artifacts.py --check-tools` reports either native binaries or the pinned container fallback for `skopeo`, `cosign`, and `trivy`.
- VM1 container tests report `PASS` for PostgreSQL, Redis, Nextcloud, Traefik, Paperless, Vaultwarden, and Navidrome.
- `make lint` and `make test` end with an explicit pass line; any missing linter fails the run instead of being skipped.

---

## Notes

- `make test` covers `scripts/test_shell_secret_env.sh`, `scripts/test_supply_chain_policy.sh`, and the static container policy checks, so the notes below matter mainly when you want one of them on its own between commits.
- Because VM1 uses shell-sourced root-only env files under `secret_env_dir`, run `scripts/test_shell_secret_env.sh` after touching env templates or launch scripts so parser regressions are caught before deployment.
- Run `scripts/promote_artifacts.py --check-tools` after provisioning a new control node so missing native binaries or missing container-engine fallback are caught early.
- Run `scripts/test_supply_chain_policy.sh` after changing image refs, bootstrap tooling, or dependency manifests.
- Run `scripts/test_supply_chain_policy.sh` and `scripts/test_container_security.sh static` after changing container-network tasks. These checks cover route-owned proxy networks and the deferred migration path used when staged VM1 runs would otherwise interrupt playbook-runner.
- Bumping a Python pin in `tests/requirements-dev.txt`, a collection in `collections/requirements.yml`, or the Alpine digest in `artifacts/test_images.lock.yml` rebuilds the toolbox on the next gate run. No separate rebuild step is needed; `make install` forces one.
- Use `bash scripts/review_container_updates.sh --service <name>` when updating `artifacts/containers.lock.yml` so digest resolution, signature verification, scanning, and runtime hardening checks happen in one sequence.
- playbook-runner host verification depends on real `playbook_runner_known_hosts` content in inventory; the static checks validate the launch script, not your real host keys.
- VM1 backups remain intentionally unencrypted for this homelab. The hardening focus is on safer temp-file handling and reduced credential exposure, not backup-at-rest encryption.

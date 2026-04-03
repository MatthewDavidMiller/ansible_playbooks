# Testing

## CI/CD Pipeline

Checks run automatically on every `git commit` via the local pre-commit hook at `hooks/pre-commit`.

**Install the hook:**

```bash
git config core.hooksPath hooks
```

**What runs:**

1. `ansible-lint`
2. `ansible-playbook --syntax-check` for the maintained playbooks

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

The script also defines image override env vars so local testing can pin the same image references used in inventory:

```bash
POSTGRES_IMAGE=docker.io/postgres:17 \
REDIS_IMAGE=docker.io/redis:7 \
NEXTCLOUD_IMAGE=docker.io/nextcloud:31-apache \
PAPERLESS_IMAGE=ghcr.io/paperless-ngx/paperless-ngx:2.14.7 \
NAVIDROME_IMAGE=docker.io/deluan/navidrome:0.54.5 \
VAULTWARDEN_IMAGE=docker.io/vaultwarden/server:1.33.2 \
SEMAPHORE_IMAGE=docker.io/semaphoreui/semaphore:v2.13.6 \
bash scripts/test_container_security.sh
```

---

## Shell-Sourced Env Regression Testing

`scripts/test_shell_secret_env.sh` renders the affected templates locally and checks the parser-specific invariants for the secret env migration:

- Special-character values containing `;`, backslashes, single quotes, and double quotes survive `bash -lc 'set -a; . file; env'` unchanged.
- `login_to_docker.service` no longer uses `EnvironmentFile=`.
- Service launch scripts no longer use `--env-file`.
- Service launch scripts source the correct file under `secret_env_dir` before `podman run`.
- Each sourced variable expected by a container is passed with `--env VAR_NAME`.
- Service launch scripts use `podman run --pull=newer` and no longer call standalone `podman pull`.
- Local backup scripts for Navidrome, Vaultwarden, and Semaphore render ownership-preserving `install` commands for the Nextcloud data tree when `backup_local: true`.

Run it directly:

```bash
bash scripts/test_shell_secret_env.sh
```

---

## Expected Outcomes

- `ansible-lint` and `--syntax-check` complete without errors.
- `scripts/test_shell_secret_env.sh` reports `PASS` for shell quoting and generated launch artifact checks.
- VM1 container tests report `PASS` for PostgreSQL, Redis, Nextcloud, Traefik, Paperless, Vaultwarden, Semaphore, and Navidrome.

---

## Notes

- Because VM1 now uses shell-sourced root-only env files under `secret_env_dir`, run `scripts/test_shell_secret_env.sh` after touching env templates or launch scripts so parser regressions are caught before deployment.
- Semaphore host verification depends on real `semaphore_known_hosts` content in inventory; the container security script validates the runtime SSH args shape, not your real host keys.
- VM1 backups remain intentionally unencrypted for this homelab. The hardening focus is on safer temp-file handling and reduced credential exposure, not backup-at-rest encryption.

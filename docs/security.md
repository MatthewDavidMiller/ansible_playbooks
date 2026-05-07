# Security Posture

This repo targets pragmatic homelab hardening for the maintained VM1 deployment. VM1 is a single Rocky Linux 10 host running rootful Podman services behind Traefik, with SELinux enforcing and firewalld limiting direct host ingress.

## Threat Model

Primary risks:

- Public HTTP(S) service compromise through an exposed application.
- Credential leakage from inventory, rendered env files, logs, or backup scripts.
- Accidental supply-chain drift from mutable container tags or unreviewed image pulls.
- Lateral movement from Traefik or an application container into the database/cache network or outbound internet.
- Backup damage or data exposure from permissive filesystem modes.

Out of scope for the current low-disruption design:

- Splitting services across multiple hosts.
- Replacing root-only rendered env files with an external secret manager.
- Encrypting the existing local backup repository by default.

## Baseline Controls

- SSH disables password auth, root login, X11 forwarding, and TCP forwarding by default. `standard_ssh_allow_users` can add an explicit login allowlist after inventory users are standardized.
- Firewalld keeps a drop-by-default model and rejects `0.0.0.0/0` for management and Ansible source CIDRs.
- SELinux remains enforcing on maintained VMs. VM2 enables `domain_can_mmap_files` for standard dev tooling; additional host-specific SELinux exceptions should be explicit variables, not ad hoc permissive mode.
- Traefik is the only intended public ingress on ports `80` and `443`. Dashboard/admin routes require management-source allowlisting and BasicAuth.
- Container images are resolved from `artifacts/containers.lock.yml`, deployed as immutable digest refs, pre-pulled by `standard_podman`, and launched with `--pull=never`.
- Containers use explicit network placement, internal app/backend networks for deny-by-default egress, memory/PID limits, `no-new-privileges`, reduced capabilities, and read-only root filesystems where compatible.
- Runtime secrets are rendered under `secret_env_dir` as root-owned `0600` env files. Secret-writing tasks use `no_log: true`.
- Backups use root-owned scripts and restrictive file modes. Temporary backup handling should use private permissions and cleanup traps.

## Change Rules

- Do not add a public host port unless it is intentional ingress through Traefik.
- Do not put Traefik on the backend database/cache network.
- Do not add container egress by placing apps on non-internal networks unless the operational need is documented.
- Do not use mutable image references in maintained deployment paths.
- Do not remove `no_log` from secret rendering tasks.
- Do not create service paths without explicit owner, group, and mode.
- Document any container that cannot use `--read-only` or `--cap-drop=ALL` with the reason and a test.

## Verification

Before merging security-sensitive changes, run:

```bash
bash scripts/test_supply_chain_policy.sh
bash scripts/test_shell_secret_env.sh
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote XDG_CACHE_HOME=/tmp/.cache ansible-lint
ANSIBLE_LOCAL_TEMP=/tmp/.ansible-local ANSIBLE_REMOTE_TEMP=/tmp/.ansible-remote XDG_CACHE_HOME=/tmp/.cache ansible-playbook --syntax-check -i example_inventory.yml vm1.yml
```

For container runtime changes, also run:

```bash
bash scripts/test_container_security.sh static
```

After deploying to VM1, check firewalld zones, service status, container inspect output, and recent SELinux AVC denials.

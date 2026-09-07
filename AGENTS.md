# Agent Instructions

Workflow instructions for coding agents working in this repository. Project
facts live in [`docs/`](docs/index.md) — read them there rather than expecting
them here.

This repo configures VM1, a single Rocky Linux 10 host running rootful Podman
services under systemd behind Traefik. Historical playbooks live on the
unmaintained `archive` branch.

---

## Before You Change Anything

Read the document that owns the area you are touching:

| Area | Read first |
|---|---|
| Any change | [README.md](README.md), [docs/index.md](docs/index.md) |
| Roles, networks, SELinux, execution order | [docs/architecture.md](docs/architecture.md) |
| Anything security-relevant | [docs/security.md](docs/security.md) |
| A new service | [docs/guides/adding-a-service.md](docs/guides/adding-a-service.md) |
| Inventory variables | [docs/variables.md](docs/variables.md), [docs/inventory.md](docs/inventory.md) |
| Container image pins | [docs/guides/container-image-updates.md](docs/guides/container-image-updates.md) |
| Tests and gates | [docs/testing.md](docs/testing.md) |
| Writing docs | [docs/documentation-standards.md](docs/documentation-standards.md) |
| Why an approach was rejected | [docs/architecture-decisions.md](docs/architecture-decisions.md) |

Check [docs/architecture-decisions.md](docs/architecture-decisions.md) before
proposing a structural change; several obvious-looking ideas were already
considered and rejected there for reasons that still hold.

## Validation

Every gate runs inside the pinned Alpine toolbox image, so rootless Podman is
the only host prerequisite — the pipeline supports no other engine and refuses
to run rootful. Never install linters on the host or run them directly: an
agent-run `ansible-lint` from a host install is not the version the gate uses.

```bash
make install     # once per clone: build the toolbox, install the pre-commit hook
make lint        # shellcheck, yamllint, ansible-lint, playbook syntax
make test        # the full pre-commit gate (no images pulled)
make test-full   # adds the runtime container tests (pulls locked images)
```

Run `make test` before reporting a change complete. Run `make test-full` after
changing container flags, launch templates, or image pins. Run a single check
with `./scripts/toolbox.sh <command>`; see [docs/testing.md](docs/testing.md).

Never pass `--no-verify` to `git commit`.

## Non-Negotiables

These are enforced by `scripts/test_supply_chain_policy.sh`,
`scripts/test_shell_secret_env.sh`, and `tests/`. Do not work around a failing
guard by weakening it — the guard is the requirement.

- **Secrets never enter the repo.** Real inventory lives outside the tree or in
  Ansible Vault. Do not read or write `inventory.yml`, `homelab_inventory.yml`,
  `vars.yml`, `env/`, `host_vars/`, or `group_vars/`; do not paste values from
  them into code, docs, commit messages, or your replies.
- **Images are immutable digest refs** resolved from
  `artifacts/containers.lock.yml`. Edit that lock only through
  `scripts/review_container_updates.sh` / `scripts/promote_artifacts.py`, never
  by hand.
- **Keep `no_log: true`** on secret-rendering tasks.
- **Follow the security change rules** in
  [docs/security.md](docs/security.md#change-rules) — no new public host ports,
  no Traefik on the backend network, no undocumented container egress.
- **Documentation ships in the same change as the code.** A change to role
  variables, playbook structure, or inventory conventions is incomplete until
  the owning doc is updated.

## Role Conventions

Match the existing roles; `roles/vaultwarden/` is a compact reference.

- Open `tasks/main.yml` with an `ansible.builtin.assert` that validates inputs
  through the `homelab_*` filters in `filter_plugins/homelab_validation.py`
  before the role changes the host.
- Declare every variable in `defaults/main.yml` with a comment, even when the
  real value comes from inventory.
- Reconcile Podman networks by including the shared `container_network` role
  once per network. Never run `podman network` or parse inspect output in a
  service role; `tests/test_ansible_regressions.py` fails the build if you do.
- Render secrets to root-only `0600` files under `secret_env_dir` and source
  them from launch scripts. No `--env-file`; use `--env VAR_NAME`.
- Launch containers with `podman run --pull=never`; `standard_podman` pre-pulls
  approved digests.
- Set explicit `owner`, `group`, and `mode` on every file, directory, and
  template task.
- Guard immediate service starts with
  `when: not (apply_runtime_changes_on_reboot | default(false) | bool)`; VM1
  stages runtime changes for the next reboot.
- Containers on a route proxy network need static IPs on both sides —
  `container_static_ips` for the service, `route_proxy_traefik_ips` for Traefik.

## Tests

New behavior needs a guard. Python tests live in `tests/` and run under
`unittest`; most architectural rules are asserted by reading role files and
rendered templates in `tests/test_ansible_regressions.py`, so write guards that
discover their subjects by content rather than by a hardcoded file list.

## Commits

Only commit when asked. Commit messages in this repo are a short imperative
subject followed by a body that explains what was wrong, what changed, and why
that approach — wrapped at 72 columns, no emoji. `git log` is the reference.

Do not commit `logs/`, `collections/ansible_collections/`, `__pycache__/`, or
any inventory file.

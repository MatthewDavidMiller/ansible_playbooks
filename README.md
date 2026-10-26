# Ansible Playbooks

Ansible repo for the maintained homelab VM workflow: VM1 runs Rocky Linux 10 Podman services under systemd. Historical playbooks and roles are preserved on the separate `archive` branch and are not maintained.

## Documentation

- [docs/index.md](docs/index.md) — full documentation index
- [docs/architecture.md](docs/architecture.md) — active VM1 topology and runtime design
- [docs/security.md](docs/security.md) — threat model, hardening baseline, and security change rules
- [docs/guides/getting-started.md](docs/guides/getting-started.md) — setup from scratch
- [docs/variables.md](docs/variables.md) — required, conditional, and optional inventory variables
- [docs/guides/container-image-updates.md](docs/guides/container-image-updates.md) — secure image review and digest-pinning workflow
- [docs/archive.md](docs/archive.md) — how to browse the historical `archive` branch

## Quick Start

```bash
# Run VM1 (stages runtime changes; reboot later to apply)
ansible-playbook -i inventory.yml vm1.yml

# Active orchestrator for the homelab
ansible-playbook -i inventory.yml homelab_vms.yml

# Preferred full cycle: configure maintained VMs, then reboot them
ansible-playbook -i inventory.yml update_homelab_vms.yml

# Dry run
ansible-playbook -i inventory.yml vm1.yml --check
```

## Validation

Every check runs inside a pinned Alpine toolbox image, so rootless Podman is the only prerequisite — `ansible-lint`, `yamllint`, `shellcheck`, `ansible-core`, and the pinned collections all live in the image.

```bash
# Build the toolbox and install the pre-commit hook (once)
make install

# Lint only
make lint

# The full gate the pre-commit hook runs
make test

# Add the runtime container tests
make test-full

# Review and pin container image updates securely
./scripts/toolbox.sh python3 scripts/promote_artifacts.py --check-tools
./scripts/toolbox.sh bash scripts/review_container_updates.sh --service traefik
```

See [docs/testing.md](docs/testing.md) for what each target runs and how the toolbox is built.

Every `vm1.yml` run applies all available Rocky Linux package updates; OS packages are not pinned. A weekly playbook-runner schedule of `update_homelab_vms.yml` patches VM1 and then reboots it.

## License

Copyright (c) Matthew David Miller. All rights reserved.

[Licensed under the MIT License.](LICENSE)

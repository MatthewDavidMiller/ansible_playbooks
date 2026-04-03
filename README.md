# Ansible Playbooks

Ansible repo for the maintained homelab VM1 workflow: one Rocky Linux 10 VM running Podman services under systemd. Historical playbooks and roles are kept under `archive/` for reference and are not maintained.

## Documentation

- [docs/index.md](docs/index.md) — full documentation index
- [docs/architecture.md](docs/architecture.md) — active VM1 topology and runtime design
- [docs/guides/getting-started.md](docs/guides/getting-started.md) — setup from scratch
- [docs/guides/container-image-updates.md](docs/guides/container-image-updates.md) — secure image review and digest-pinning workflow
- [docs/archive.md](docs/archive.md) — archived playbooks, roles, and historical notes
- [example_inventory.yml](example_inventory.yml) — active inventory template for VM1

## Quick Start

```bash
# Run VM1 (stages runtime changes; reboot later to apply)
ansible-playbook -i inventory.yml vm1.yml

# Apply host package updates from approved repos
ansible-playbook -i inventory.yml standalone_tasks/update_vm1_packages.yml

# Active orchestrator for the homelab
ansible-playbook -i inventory.yml homelab_vms.yml

# Preferred full cycle: configure VM1, then reboot it
ansible-playbook -i inventory.yml update_homelab_vms.yml

# Dry run
ansible-playbook -i inventory.yml vm1.yml --check

# Lint
ansible-lint

# Review and pin container image updates securely
python3 scripts/promote_artifacts.py --check-tools
bash scripts/review_container_updates.sh --service traefik
```

Normal `vm1.yml` runs apply security-only OS updates. Use `standalone_tasks/update_vm1_packages.yml` when you intentionally want the broader installed package set refreshed.

## License

Copyright (c) Matthew David Miller. All rights reserved.

[Licensed under the MIT License.](LICENSE)

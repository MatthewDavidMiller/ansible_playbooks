# CLAUDE.md

Repository guidance for Claude Code when working in this project.

## Project

This repo manages a homelab with Ansible. Most hosts are Rocky Linux 10 VMs running Podman containers under systemd; the laptop playbooks target Arch Linux.

Start with [README.md](README.md), then use [docs/index.md](docs/index.md) for the full documentation map.

## Working Rules

- Prefer updating existing playbooks, roles, and docs instead of adding parallel patterns.
- Keep architecture, inventory, and playbook facts in `docs/`, not in this file.
- Update documentation in the same change when behavior, variables, or role ordering changes.
- Do not add a `Co-Authored-By` trailer to commits in this repository.

## Checks

- Run `ansible-lint` after Ansible changes.
- Run `ansible-playbook -i inventory.yml <playbook>.yml --syntax-check` for changed playbooks when relevant.
- Keep verification scoped to the files you changed.

## Where To Look

- [docs/playbooks.md](docs/playbooks.md): playbook purpose, targets, and role order
- [docs/architecture.md](docs/architecture.md): host topology, container and firewall design, execution-order rationale
- [docs/inventory.md](docs/inventory.md): inventory variables and naming conventions
- [docs/roles/standard.md](docs/roles/standard.md): shared infrastructure roles
- [docs/roles/services.md](docs/roles/services.md): service role behavior and templates
- [docs/guides/getting-started.md](docs/guides/getting-started.md): setup and first-run commands
- [docs/documentation-standards.md](docs/documentation-standards.md): doc ownership and cross-reference rules

# CLAUDE.md

Repository guidance for Claude Code when working in this project.

## Project

This repo manages the maintained homelab VM workflow with Ansible. Historical playbooks and roles are preserved on the separate `archive` branch for reference only.

Start with [README.md](README.md), then use [docs/index.md](docs/index.md) for the full documentation map.

## Working Rules

- Prefer updating existing playbooks, roles, and docs instead of adding parallel patterns.
- Keep architecture, inventory, and playbook facts in `docs/`, not in this file.
- Update documentation in the same change when behavior, variables, or role ordering changes.
- Do not add a `Co-Authored-By` trailer to commits in this repository.
- Never wait or sleep for an artificial time gate (for example, waiting until a newer container image becomes 24 hours old). Choose the latest option that is eligible right now, finish the task, and note any newer ineligible candidates for a later run.

## Checks

- Every gate runs inside the toolbox image, so Docker or Podman is the only host prerequisite. Build it once with `make install`.
- Run `make lint` after Ansible changes: it covers `ansible-lint`, `yamllint`, ShellCheck, Python compilation, and `--syntax-check` for every maintained playbook.
- Run `make test` before committing. The pre-commit hook runs the same gate.
- Run `make test-full` when container flags, launch templates, or image pins change; it adds the runtime container tests.
- Run a single check with `./scripts/toolbox.sh <command>`, and keep verification scoped to the files you changed.

## Where To Look

- [docs/playbooks.md](docs/playbooks.md): playbook purpose, targets, and role order
- [docs/architecture.md](docs/architecture.md): host topology, container and firewall design, execution-order rationale
- [docs/inventory.md](docs/inventory.md): inventory variables and naming conventions
- [docs/roles/standard.md](docs/roles/standard.md): shared infrastructure roles
- [docs/roles/services.md](docs/roles/services.md): service role behavior and templates
- [docs/guides/getting-started.md](docs/guides/getting-started.md): setup and first-run commands
- [docs/testing.md](docs/testing.md): the toolbox image, `make` targets, and what each gate covers
- [docs/archive.md](docs/archive.md): browsing the historical `archive` branch
- [docs/documentation-standards.md](docs/documentation-standards.md): doc ownership and cross-reference rules

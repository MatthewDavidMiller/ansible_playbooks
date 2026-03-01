# Ansible Playbooks

Collection of Ansible playbooks for configuring homelab Linux servers and services. Targets Rocky Linux 10 VMs running Podman containers managed via systemd. Laptop configuration playbooks target Arch Linux.

## Documentation

- [docs/index.md](docs/index.md) — full documentation index
- [docs/architecture.md](docs/architecture.md) — host topology, network design, SELinux policy
- [docs/guides/getting-started.md](docs/guides/getting-started.md) — setup from scratch
- [example_inventory.yml](example_inventory.yml) — inventory template with all required variables

## Quick Start

```bash
# Run VM1 (all consolidated services)
ansible-playbook -i inventory.yml vm1.yml

# Run all homelab VMs
ansible-playbook -i inventory.yml homelab_vms.yml

# Run updates + reboot
ansible-playbook -i inventory.yml update_homelab_vms.yml

# Dry run
ansible-playbook -i inventory.yml vm1.yml --check

# Lint
ansible-lint
```

## License

Copyright (c) Matthew David Miller. All rights reserved.

[Licensed under the MIT License.](LICENSE)

# playbook-runner setup and Semaphore retirement

> **Historical:** this guide was written while the previous file service (Nextcloud) and its PostgreSQL still ran on VM1. Where it names `nextcloud_*`, `postgres_*` or a `Nextcloud:` backup location, that service has since been retired and the backups go to homedrive. See [dr-restore.md](dr-restore.md) for the current layout.

[playbook-runner](https://github.com/MatthewDavidMiller/playbook-runner) is
the first-party Ansible web UI and scheduler on VM1. It holds the external
inventory, vault passwords and SSH keys, runs playbooks on demand, and runs
the weekly `update_homelab_vms.yml` schedule. It needs no database.

It replaced Semaphore, which this repository no longer deploys. Sections 1
to 3 set the runner up; section 4 removes what Semaphore left on VM1.

---

## 1. Release and lock the image

Done for the first release. Each later release follows the same steps. In the
playbook-runner repository:

```bash
gh auth token | podman login ghcr.io -u MatthewDavidMiller --password-stdin
make release
```

The `ghcr.io/matthewdavidmiller/playbook-runner` package is public, because
VM1 pulls images anonymously (the supply-chain policy refuses registry
credentials in inventory). The image holds no secrets; the repository stays
private. Then pin the new digest here:

```bash
bash scripts/review_container_updates.sh --service playbook_runner
```

The lock entry carries `first_party: true`, so the review skips the 24-hour
age gate that applies to third-party images; see
[container-image-updates.md](container-image-updates.md#first-party-images).

## 2. Inventory

`vm1.yml` enables the role. Add to the externally managed inventory:

```yaml
playbook_runner_path: /srv/playbook-runner      # any safe absolute path
playbook_runner_master_key: !vault |            # playbook-runner gen-key
  ...
playbook_runner_admin_password: !vault |        # optional
  ...
playbook_runner_backup_location: Nextcloud:playbook_runner_backup
playbook_runner_known_hosts: "host ssh-ed25519 AAAA..."   # pinned SSH host keys
```

Store the master key in Vaultwarden as well. Without it the runner's stored
secrets cannot be recovered.

The network addresses, DNS aliases, and Traefik route come from the
repository's plan, [`network/vm1.yml`](../../network/vm1.yml), and `vm1.yml`
adds `playbook_runner` to `container_service_names` itself, so the inventory
needs none of them. The route is
`playbook-runner.<homelab_internal_domain>`, restricted to
`management_network`.

## 3. Deploy and configure

Run `update_homelab_vms.yml` as usual. After the reboot, open
the runner's site and sign in (with `playbook_runner_admin_password`, or
with the setup token from `podman logs playbook_runner`). Then recreate in
the interface:

1. **Secrets:** the vault password(s), and the SSH key used for VM1.
2. **Repositories:** this repository's git URL, with a read-only deploy key.
3. **Known hosts:** confirm the git server and VM1 are listed.
4. **Inventories:** the inventory variables file.
5. **Templates:** `vm1.yml` (for ad-hoc runs), `update_homelab_vms.yml`,
   `reboot_vms.yml`, and `show_logs.yml`, plus one `show_logs.yml` template
   per service you check often, with its tag (see
   [playbooks.md](../playbooks.md#show_logsyml)). Sync the repository first
   so the new playbooks are offered.
6. **Schedules:** the weekly `update_homelab_vms.yml` run, for example
   `0 4 * * sun` in `America/New_York`. The run finishes and is marked
   succeeded before the reboot, which it schedules a minute out. That
   success does not show that VM1 came back, so schedule `show_logs.yml`
   for a few minutes later, or run it, and read the result. A run still
   going when VM1 stops is marked `interrupted`.

Run `vm1.yml` in check mode from the runner before relying on it.

## 4. Retire Semaphore

Done. `vm1.yml` no longer deploys Semaphore, and the one-shot cleanup that
removed what earlier runs had put on VM1 (the service, container, image,
scripts, cron entry, networks, Traefik route, and its database and role), and
the helper that removed its settings from the inventory, have been deleted
from the repository now that they have run. They are in the git history if
you need to read them. Anything still named for Semaphore in an inventory is
unused and can be removed by hand, along with the old dumps and the Semaphore
DNS record. The certificate in Traefik's `acme.json` expires on its own.

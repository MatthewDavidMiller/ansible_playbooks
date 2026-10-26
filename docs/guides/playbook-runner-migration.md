# playbook-runner setup and Semaphore retirement

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

The route dictionaries in inventory replace the role defaults, so add the
runner's entries to each (values from [variables.md](../variables.md)):
`route_proxy_network_subnets`, `route_proxy_container_ips`,
`route_proxy_traefik_ips`, `container_static_ips`, and `container_dns`.
Then add a route and the service order:

```yaml
proxy_config:
  - name: playbook_runner_proxy
    proxy_fqdn: runner.example.com
    proxy_upstream_protocol: http
    container_destination: "{{ container_dns.aliases.playbook_runner_proxy }}.{{ container_dns.domain }}"
    proxy_upstream_port: "8080"
    proxy_network: playbook_runner_container_net
    proxy_management_only: true
container_service_names: "... vaultwarden playbook_runner"
```

## 3. Deploy and configure

Run `update_homelab_vms.yml` as usual. After the reboot, open
the runner's site and sign in (with `playbook_runner_admin_password`, or
with the setup token from `podman logs playbook_runner`). Then recreate in
the interface:

1. **Secrets:** the vault password(s), and the SSH key used for VM1.
2. **Repositories:** this repository's git URL, with a read-only deploy key.
3. **Known hosts:** confirm the git server and VM1 are listed.
4. **Inventories:** the inventory variables file.
5. **Templates:** `vm1.yml` (for ad-hoc runs) and `update_homelab_vms.yml`.
6. **Schedules:** the weekly `update_homelab_vms.yml` run, for example
   `0 4 * * sun` in `America/New_York`. The run is marked `interrupted`
   when the reboot stops the runner partway through; check that VM1 came
   back patched.

Run `vm1.yml` in check mode from the runner before relying on it.

## 4. Retire Semaphore

`vm1.yml` no longer deploys Semaphore, so nothing in it removes what an earlier
run created. [`retire_semaphore.yml`](../playbooks.md#retire_semaphoreyml)
does, once.

**1. Update the inventory.** Run the helper on your inventory file. It
previews by default, prints variable names and line numbers but never values,
and only changes the file with `--write`:

```bash
python3 scripts/remove_semaphore_inventory.py /path/to/inventory.yml          # preview
python3 scripts/remove_semaphore_inventory.py /path/to/inventory.yml --write  # apply
```

It edits the text in place, so comments, ordering, and `!vault` blocks are
untouched, and it keeps a private `0600` copy of the original next to the file
(delete that copy once you have checked the result; it holds the same secrets).
Before writing, it parses the file before and after and refuses unless the
only difference is the Semaphore settings, and it refuses if anything left in
the file still refers to a variable it would remove, such as a
`"{{ semaphore_known_hosts }}"` template. It needs `python3` with PyYAML. A
file it cannot check (flow-style mappings, quoted keys) is left alone with an
explanation; edit that one by hand.

It removes:

- the `semaphore_*` variables: password, admin, encryption key, known hosts,
  backup location, egress network, and image;
- the `semaphore_container_net` entries from `route_proxy_network_subnets`,
  `route_proxy_container_ips`, `route_proxy_traefik_ips`, and
  `reverse_proxy_deferred_route_networks`;
- the `semaphore_backend`, `semaphore_proxy`, and `semaphore_egress` entries
  from `container_static_ips` and `container_dns.aliases`;
- the Semaphore route from `proxy_config`, and `semaphore` from
  `container_service_names`.

By default it **keeps** `semaphore_database_name` and `semaphore_db_user`,
which step 3 needs to drop the database. `postgres_admin_user` is never
touched. If you may want Semaphore's data later, note the value of
`semaphore_backup_location` first, since the helper removes it, and confirm a
recent dump exists in that folder under
`<nextcloud_path>/data/<nextcloud_homelab_user>/files/`.

**2. Run `vm1.yml`, then reboot VM1.** The PostgreSQL and Traefik launch
scripts lose their Semaphore settings, and the reboot applies them, so Traefik
no longer holds the Semaphore network.

**3. Run `retire_semaphore.yml`** (in playbook-runner, add it as a template
and run it once, or run `ansible-playbook -i inventory.yml retire_semaphore.yml`
from a workstation). It removes the service, container, image, scripts,
backup cron entry, config, state, secrets file, log, both networks, the
Traefik route file, and the database and role. Run it in check mode first to
see what it would change.

**4. Finish up.** Run the helper again with `--all` to remove the last two
variables, delete the cleanup template from playbook-runner, delete the old dumps when you no
longer need them (then run `occ files:scan` for that user), and delete the
Semaphore DNS record. The certificate in Traefik's `acme.json` expires on its
own.

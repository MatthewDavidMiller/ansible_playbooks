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

Semaphore's role is gone from `vm1.yml`, so Ansible no longer manages or
removes anything it created. Remove it by hand, in this order.

**1. Clean the inventory** before the next run, or validation fails on the
leftover entries. Delete:

- the `semaphore_*` variables (database, admin, encryption key, known hosts,
  backup location, egress network) and `semaphore_image` if set;
- the `semaphore_container_net` entries from `route_proxy_network_subnets`,
  `route_proxy_container_ips`, and `route_proxy_traefik_ips`;
- the `semaphore_backend`, `semaphore_proxy`, and `semaphore_egress` entries
  from `container_static_ips` and `container_dns.aliases`;
- the Semaphore route from `proxy_config`, and `semaphore` from
  `container_service_names`.

**2. Run `vm1.yml` and reboot.** The PostgreSQL and Traefik launch scripts
lose their Semaphore settings, and the reboot applies them. Do the rest after
the reboot, so Traefik no longer holds the Semaphore network.

**3. Remove Semaphore from VM1** as root:

```bash
# Service, launch scripts, and the daily backup cron entry
systemctl disable --now semaphore.service
rm -f /etc/systemd/system/semaphore.service /usr/local/bin/semaphore.sh \
      /usr/local/bin/backup_semaphore.sh
systemctl daemon-reload
crontab -l | grep -v 'Backup Semaphore\|backup_semaphore.sh' | crontab -

# Container, image, config, state, and secrets
podman rm -f semaphore 2>/dev/null
podman images --format '{{.ID}} {{.Repository}}' | awk '/semaphore/ {print $1}' | xargs -r podman rmi -f
rm -rf /etc/semaphore /var/lib/semaphore <secret_env_dir>/semaphore.env \
      /var/log/semaphore_backup.log

# Networks (fails while a container still uses them)
podman network rm semaphore_container_net <semaphore_egress_network>

# The Traefik route file; list the directory to find it by route name
ls <traefik_path>/config/
rm <traefik_path>/config/<semaphore_route_name>.yml
```

**4. Drop the database and role** from the shared PostgreSQL container:

```bash
podman exec postgres psql -h localhost -U <postgres_admin_user> -d postgres \
    -c "DROP DATABASE IF EXISTS <semaphore_database_name>;" \
    -c "DROP ROLE IF EXISTS <semaphore_db_user>;"
```

**5. Keep or delete the backups.** The last Semaphore dumps stay in
`<nextcloud_path>/data/<nextcloud_homelab_user>/files/<semaphore_backup_location>/`.
Keep them until you are sure nothing in Semaphore is needed, then delete the
directory and run `occ files:scan` for that user.

**6. Outside VM1:** delete the Semaphore DNS record, and remove its
entries from any monitoring or bookmarks. The certificate in Traefik's
`acme.json` expires on its own and needs no action.

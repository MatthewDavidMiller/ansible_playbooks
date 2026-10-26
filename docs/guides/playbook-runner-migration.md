# Migrating from Semaphore to playbook-runner

[playbook-runner](https://github.com/MatthewDavidMiller/playbook-runner) is
the first-party replacement for Semaphore. It covers what this repository
uses Semaphore for: the external inventory, vault passwords and SSH keys,
manual playbook runs, and the weekly `update_homelab_vms.yml` schedule. It
needs no database, so retiring Semaphore also retires its PostgreSQL
database, role, and backup.

The two run side by side until playbook-runner has completed a full weekly
cycle; only then is Semaphore removed.

---

## 1. Release and lock the image

Done for 0.1.0. Each later release follows the same steps. In the
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
playbook_runner_known_hosts: "{{ semaphore_known_hosts }}"
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
container_service_names: "... semaphore playbook_runner"
```

## 3. Deploy and configure

Run `update_homelab_vms.yml` from Semaphore as usual. After the reboot, open
the runner's site and sign in (with `playbook_runner_admin_password`, or
with the setup token from `podman logs playbook_runner`). Then recreate in
the interface:

1. **Secrets:** the vault password(s), and the SSH key Semaphore uses for VM1.
2. **Repositories:** this repository's git URL, with a read-only deploy key.
3. **Known hosts:** confirm the git server and VM1 are listed.
4. **Inventories:** the same inventory Semaphore holds.
5. **Templates:** `vm1.yml` (for ad-hoc runs) and `update_homelab_vms.yml`.
6. **Schedules:** disabled at first.

Run `vm1.yml` in check mode from the runner and compare the result with a
Semaphore check run.

## 4. Switch the schedule

Disable the weekly schedule in Semaphore and enable the matching schedule in
the runner (`0 4 * * sun`, or whatever Semaphore used, in
`America/New_York`). Let one full weekly cycle complete. The run is marked
`interrupted` when the reboot stops the runner partway through, exactly as
Semaphore's run was; check that VM1 came back patched.

## 5. Retire Semaphore

Once a weekly cycle has completed from the runner, remove the `semaphore`
role, its lock entry, its database and user, its networks and route, and its
inventory variables in one change, and update this guide's references.

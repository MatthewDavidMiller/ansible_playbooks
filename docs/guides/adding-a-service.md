# Adding a Service

This guide covers the maintained pattern: add the service to VM1, not to a new dedicated-VM playbook. Historical multi-VM examples live under [archive.md](../archive.md).

---

## 1. Create the Role

Create `roles/<service_name>/tasks/main.yml` and any needed templates/files under `roles/<service_name>/`.

Use the existing active service roles as reference:

- `roles/reverse_proxy/`
- `roles/nextcloud/`
- `roles/paperless_ngx/`
- `roles/navidrome/`
- `roles/vaultwarden/`
- `roles/semaphore/`

---

## 2. Follow the Active Runtime Pattern

- Use Podman + systemd, matching the existing VM1 services.
- Render sensitive values to `{{ secret_env_dir }}/<service>.env` as root-only shell-sourced files.
- Use `podman run --pull=newer`.
- Use `:Z` on container-mounted host paths.
- Put the service on its own Podman network when it needs isolation.
- If the service is proxied by Traefik, add an entry to `proxy_config` instead of creating a per-service reverse-proxy template.

---

## 3. Wire It Into VM1

- Add the role to `vm1.yml` in the correct order.
- Add required variables to the `vm1` host entry in `inventory.yml`.
- If Traefik must reach the service, add the service network to `traefik_networks`.
- If the service depends on PostgreSQL or Redis, place it after `nextcloud`.
- If the role changes live runtime behavior that VM1 stages until reboot, guard immediate-start behavior with `apply_runtime_changes_on_reboot`.

---

## 4. Document It

- Add the role to [roles/services.md](../roles/services.md) or [roles/standard.md](../roles/standard.md).
- Update [playbooks.md](../playbooks.md) if the role order changes.
- Update [inventory.md](../inventory.md) with any new variables.
- Update [testing.md](../testing.md) if the service changes the validation surface.

---

## 5. Verify It

```bash
ansible-lint
ansible-playbook --syntax-check -i example_inventory.yml vm1.yml
bash scripts/test_shell_secret_env.sh
```

Run `bash scripts/test_container_security.sh` when the service changes container hardening or launch semantics.

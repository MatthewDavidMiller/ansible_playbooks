# podman_service

Reusable role that encapsulates the standard four-step container deployment
pattern used by all service roles in this project:

1. Create data directories
2. Write `/usr/local/bin/<name>.sh` — the `podman run` script
3. Write `/etc/systemd/system/<name>.service` — the systemd unit
4. Enable and start the systemd service

The generated script uses `podman run --pull=newer` by default so cached
images are reused unless the remote registry digest changes.

Callers keep their own service-specific `.j2` templates for the run script
when the generic template is not sufficient (e.g. when the script needs
complex conditional logic). In the common case the generic templates cover
everything through variables.

---

## Required variables

| Variable | Type | Description |
|---|---|---|
| `podman_service_name` | string | Container name; also the stem for the script and unit filenames |
| `podman_service_image` | string | Fully-qualified image reference, e.g. `docker.io/vaultwarden/server:latest` |

---

## Optional variables (see `defaults/main.yml` for defaults)

| Variable | Type | Default | Description |
|---|---|---|---|
| `podman_service_pull_policy` | string | `newer` | Podman `--pull` policy; `newer` keeps the cached image unless the remote digest changed |
| `podman_service_dirs` | list of objects | `[]` | Directories to create. Each entry: `path`, `owner`, `group`, `mode` |
| `podman_service_networks` | list of strings | `[]` | `--network` values |
| `podman_service_ports` | list of strings | `[]` | `-p host:container[/proto]` mappings |
| `podman_service_volumes` | list of strings | `[]` | `-v src:dest[:opts]` mappings. Include `:Z` on Rocky Linux 10 |
| `podman_service_env` | dict | `{}` | Environment variables; values are shell-quoted automatically |
| `podman_service_extra_args` | list of strings | `[]` | Extra flags appended before the image reference, e.g. `--memory=256m` |
| `podman_service_labels` | list of strings | `[]` | `--label` flags for Traefik routing, rendered verbatim |
| `podman_service_after` | list of strings | `[]` | Additional `After=` dependencies in the systemd unit |
| `podman_service_type` | string | `forking` | systemd `Type=`. Use `forking` for `-d` containers, `simple` for foreground |
| `podman_service_timeout_start` | int | `300` | `TimeoutStartSec` in the systemd unit |
| `podman_service_timeout_stop` | int | `70` | `TimeoutStopSec` in the systemd unit |
| `podman_service_script_owner` | string | `{{ user_name }}` | Owner of the run script |

---

## Handlers expected in the calling playbook

The tasks in this role fire two notify handlers. The calling role or playbook
must define them:

```yaml
handlers:
  - name: Reload systemd
    ansible.builtin.systemd:
      daemon_reload: true

  - name: Restart <service_name>
    ansible.builtin.systemd:
      name: "<service_name>.service"
      state: restarted
```

Because `notify` values are evaluated at template-render time using the
`podman_service_name` variable, the handler name must match exactly:
`"Restart {{ podman_service_name }}"`.

---

## Usage example

Below is a minimal example showing how an existing service role would delegate
to `podman_service` via `ansible.builtin.include_role`.

```yaml
# roles/myservice/tasks/main.yml
---
- name: Create myservice container network
  ansible.builtin.shell:
    cmd: podman network create --subnet 172.16.1.32/29 myservice_net
  ignore_errors: true
  changed_when: false

- name: Deploy myservice container
  ansible.builtin.include_role:
    name: podman_service
  vars:
    podman_service_name: myservice
    podman_service_image: docker.io/example/myservice:latest
    podman_service_pull_policy: newer
    podman_service_dirs:
      - path: "{{ myservice_path }}/data"
        owner: "1000"
        group: "1000"
        mode: "0750"
      - path: "{{ myservice_path }}/config"
        owner: "1000"
        group: "1000"
        mode: "0750"
    podman_service_networks:
      - myservice_net
    podman_service_ports:
      - "8080:8080"
    podman_service_volumes:
      - "{{ myservice_path }}/data:/app/data:Z"
      - "{{ myservice_path }}/config:/app/config:Z,ro"
    podman_service_env:
      TZ: America/New_York
      APP_DB_HOST: postgres.dns.podman
      APP_DB_PASS: "{{ myservice_db_password }}"
    podman_service_extra_args:
      - "--memory=512m"
      - "--memory-swap=512m"
    podman_service_after:
      - postgres_container.service
```

### Traefik labels example

For VM1 services behind Traefik, pass labels via `podman_service_labels`:

```yaml
podman_service_labels:
  - "--label traefik.enable=true"
  - "--label traefik.http.routers.myservice.rule=Host(`{{ myservice_fqdn }}`)"
  - "--label traefik.http.routers.myservice.entrypoints=websecure"
  - "--label traefik.http.routers.myservice.tls.certResolver=porkbun"
  - "--label traefik.http.services.myservice.loadbalancer.server.port=8080"
```

---

## SELinux note (Rocky Linux 10)

All volume mounts for services running on Rocky Linux 10 must include the `:Z`
flag so that SELinux relabels the host directory with the container context.
Read-only mounts use `:ro,z` (lowercase `z` allows sharing across containers).
Never disable or set SELinux to permissive — the `:Z` flag is the correct fix.

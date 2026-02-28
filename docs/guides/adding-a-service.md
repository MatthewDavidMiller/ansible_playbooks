# Adding a New Service

This guide walks you through adding a new service to the homelab using the established Podman + systemd pattern. See [roles/services.md](../roles/services.md) for existing service roles as examples.

---

## 1. Create the Role Directory

```bash
mkdir -p roles/<service_name>/tasks
mkdir -p roles/<service_name>/templates
```

---

## 2. Write `roles/<service_name>/tasks/main.yml`

Follow this task structure:

**a. Create the container network:**
```yaml
- name: Create <service> container network
  ansible.builtin.shell:
    cmd: podman network create <service>_container_net
  ignore_errors: true
  when: ansible_facts['distribution'] == 'Debian' or ansible_facts['distribution'] == 'Archlinux' or ansible_facts['distribution'] == 'Rocky'
```

**b. Create data directories:**
```yaml
- name: Create <service> data directory
  ansible.builtin.file:
    path: "{{ service_path }}"
    state: directory
    owner: 1000
    group: 1000
    mode: "0770"
  when: ansible_facts['distribution'] == 'Debian' or ansible_facts['distribution'] == 'Archlinux' or ansible_facts['distribution'] == 'Rocky'
```

Use UID/GID 1000 unless the container image requires a different user. Check the image documentation.

**c. Write the launch script:**
```yaml
- name: <service> script
  ansible.builtin.template:
    src: <service>.sh.j2
    dest: /usr/local/bin/<service>.sh
    owner: 1000
    group: root
    mode: "0770"
  when: ansible_facts['distribution'] == 'Debian' or ansible_facts['distribution'] == 'Archlinux' or ansible_facts['distribution'] == 'Rocky'
```

**d. Write the systemd unit:**
```yaml
- name: <service> service
  ansible.builtin.template:
    src: <service>.service.j2
    dest: /etc/systemd/system/<service>.service
  when: ansible_facts['distribution'] == 'Debian' or ansible_facts['distribution'] == 'Archlinux' or ansible_facts['distribution'] == 'Rocky'

- name: Enable <service>
  ansible.builtin.systemd:
    name: <service>.service
    enabled: yes
  when: ansible_facts['distribution'] == 'Debian' or ansible_facts['distribution'] == 'Archlinux' or ansible_facts['distribution'] == 'Rocky'
```

---

## 3. Write the Shell Script Template

Create `roles/<service_name>/templates/<service>.sh.j2`:

```bash
/usr/bin/podman pull docker.io/example/image:latest
/usr/bin/podman run \
--name <service> \
--network <service>_container_net \
-e SOME_ENV={{ some_variable }} \
-e TZ=America/New_York \
--volume {{ service_path }}:/data:Z \
-d docker.io/example/image:latest
```

Key conventions:
- Always use `:Z` on volume mounts — this triggers SELinux file context relabeling on Rocky Linux 10
- Use Podman DNS names (`<container>.dns.podman`) when containers need to talk to each other
- Pull the image before running to get the latest version

---

## 4. Write the Systemd Unit Template

Create `roles/<service_name>/templates/<service>.service.j2`:

```ini
[Unit]
Description=<Service> Container
After=network.target login_to_docker.service
Requires=login_to_docker.service

[Service]
Restart=always
ExecStartPre=-/usr/bin/podman stop <service>
ExecStartPre=-/usr/bin/podman rm <service>
ExecStart=/usr/local/bin/<service>.sh

[Install]
WantedBy=multi-user.target
```

If the service depends on other containers (e.g., a database), add them to `After=` and `Requires=`.

---

## 5. Open Required Firewall Ports (if needed)

If the service needs a port open beyond what `standard_firewalld` provides, add a firewalld task to your role (not to `standard_firewalld`):

```yaml
- name: Open port XXXX for <service>
  ansible.posix.firewalld:
    zone: homelab
    port: XXXX/tcp
    permanent: yes
    state: enabled
  when: ansible_facts['distribution'] == 'Debian' or ansible_facts['distribution'] == 'Archlinux' or ansible_facts['distribution'] == 'Rocky'
```

Port 443 does not need to be added — the `reverse_proxy` role opens it.

---

## 6. Add a SWAG Proxy Config Template (if HTTPS access is needed)

Create `roles/reverse_proxy/templates/<service>_proxy.conf.j2` with the nginx subdomain proxy configuration for your service. Use an existing template (e.g., `vaultwarden_proxy.conf.j2`) as a reference.

Then add an entry to `proxy_config` in the host's inventory:

```yaml
proxy_config:
  - name: <service>_proxy
    proxy_fqdn: "<service>.example.com"
    proxy_upstream_port: "8080"
    proxy_upstream_protocol: "http"
    container_destination: "<service>.dns.podman"
```

See [inventory.md — proxy_config object schema](../inventory.md#proxy_config-object-schema).

---

## 7. Create the Playbook

Create `<service_name>.yml`:

```yaml
---
- hosts: <service_name>
  roles:
    - standard_ssh
    - standard_qemu_guest_agent
    - standard_update_packages
    - configure_timezone
    - standard_cron
    - standard_firewalld
    - standard_podman
    - standard_cleanup
    - reverse_proxy      # if HTTPS access is needed
    - <service_name>
```

Add `standard_rclone` if the service needs rclone (backups or file mounts). Add `standard_selinux` if deploying to Rocky Linux 10 with FUSE mounts.

---

## 8. Add to `homelab_vms.yml`

```yaml
- name: Run <service_name> config playbook
  import_playbook: <service_name>.yml
```

---

## 9. Add to Inventory

Add a host entry under `homelab.hosts` in your inventory with all required variables. Follow the naming conventions in [inventory.md — Variable naming conventions](../inventory.md#variable-naming-conventions).

---

## Consolidated VM vs. Dedicated VM

If you are adding the service to the AllServices VM (ID 120) rather than a dedicated VM:

- Add the role to `all_services.yml` in the appropriate order
- Add all required variables to the `all_services` host entry in inventory
- If the service uses a Podman network, add that network to `swag_networks` in the `all_services` inventory entry
- If the service has a PostgreSQL instance, use a unique path variable (not `postgres_path`) to avoid collisions with other PostgreSQL instances

---

## Verify

```bash
# Lint
ansible-lint <service_name>.yml

# Dry run
ansible-playbook -i inventory.yml <service_name>.yml --check -v

# Apply
ansible-playbook -i inventory.yml <service_name>.yml -v
```

On Rocky Linux 10, after the first live run check for SELinux denials:

```bash
ausearch -m avc -ts recent
```

See [architecture.md — SELinux](../architecture.md#selinux) for how to interpret and resolve denials.

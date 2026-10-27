#!/bin/bash

set -euo pipefail

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

repo_root=$(cd "$(dirname "$0")/.." && pwd)
tmpdir=$(mktemp -d)
render_dir="$tmpdir/render"

cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

mkdir -p "$render_dir"

command -v ansible-playbook >/dev/null 2>&1 || fail "ansible-playbook is required"

porkbun_api_key=$(cat <<'EOF'
pk1_; "quoted" \ slash & dollars $HOME
EOF
)
porkbun_secret_key=$(cat <<'EOF'
sk1_; "quoted" \ slash & dollars $HOME and 'single'
EOF
)
postgres_admin_password=$(cat <<'EOF'
pg;admin "quoted" \ slash & dollars $HOME and 'single'
EOF
)
nextcloud_db_password=$(cat <<'EOF'
nc;db "quoted" \ slash & dollars $HOME and 'single'
EOF
)
paperless_db_password=$(cat <<'EOF'
pl;db "quoted" \ slash & dollars $HOME and 'single'
EOF
)
paperless_secret_key=$(cat <<'EOF'
pl;secret "quoted" \ slash & dollars $HOME and 'single'
EOF
)
nextcloud_admin_password=$(cat <<'EOF'
nc;admin "quoted" \ slash & dollars $HOME and 'single'
EOF
)
nextcloud_trusted_domains=$(cat <<'EOF'
cloud.example.com cloud-alt.example.com
EOF
)

cat > "$tmpdir/vars.yml" <<EOF
secret_env_dir: /etc/homelab/secrets
homelab_domain: 'example.com'
homelab_subdomain: 'dyn-sub'
porkbun_api_key: 'pk1_; "quoted" \ slash & dollars \$HOME'
porkbun_api_key_secret: 'sk1_; "quoted" \ slash & dollars \$HOME and ''single'''
postgres_admin_user: 'postgres-admin'
postgres_admin_password: 'pg;admin "quoted" \ slash & dollars \$HOME and ''single'''
postgres_legacy_bootstrap_user: ''
postgres_legacy_bootstrap_password: ''
nextcloud_database_name: 'nextcloud-db'
nextcloud_db_user: 'nextcloud-user'
nextcloud_db_password: 'nc;db "quoted" \ slash & dollars \$HOME and ''single'''
paperless_database_name: 'paperless-db'
paperless_db_user: 'paperless-user'
paperless_db_password: 'pl;db "quoted" \ slash & dollars \$HOME and ''single'''
paperless_secret_key: 'pl;secret "quoted" \ slash & dollars \$HOME and ''single'''
nextcloud_admin_user: 'nextcloud-admin'
nextcloud_admin_password: 'nc;admin "quoted" \ slash & dollars \$HOME and ''single'''
nextcloud_trusted_domains: 'cloud.example.com cloud-alt.example.com'
nextcloud_dns_name: 'cloud.example.com'
nextcloud_homelab_user: 'admin'
nextcloud_uid: '33'
nextcloud_gid: '33'
paperless_dns_name: 'paperless.example.com'
traefik_image: 'docker.io/traefik@sha256:1111111111111111111111111111111111111111111111111111111111111111'
traefik_egress_network: 'traefik_egress_net'
traefik_dashboard_basic_auth_users:
  - 'admin:\$apr1\$example\$T2v8QdKqzJ8D7c4s1bYhZ/'
traefik_dashboard_fqdn: 'traefik.example.com'
management_network: '192.168.1.0/24'
ip_ansible: '192.168.1.10/32'
traefik_path: '/srv/traefik'
container_dns:
  domain: 'test.dns.podman'
  aliases:
    postgres_backend: 'test-postgres-backend'
    redis_backend: 'test-redis-backend'
    nextcloud_backend: 'test-nextcloud-backend'
    nextcloud_proxy: 'test-nextcloud-proxy'
    paperless_backend: 'test-paperless-backend'
    paperless_proxy: 'test-paperless-proxy'
    playbook_runner_proxy: 'test-playbook-runner-proxy'
    playbook_runner_egress: 'test-playbook-runner-egress'
    music_server_proxy: 'test-music-server-proxy'
    traefik_proxy: 'test-traefik-proxy'
    traefik_egress: 'test-traefik-egress'
route_proxy_network_subnets:
  nextcloud_proxy_net: '172.16.1.32/29'
  paperless_proxy_net: '172.16.1.40/29'
  vaultwarden_container_net: '172.16.1.16/29'
container_static_ips:
  postgres_backend: '172.16.1.2'
  redis_backend: '172.16.1.3'
  nextcloud_backend: '172.16.1.4'
  nextcloud_proxy: '172.16.1.34'
  paperless_backend: '172.16.1.5'
  paperless_proxy: '172.16.1.42'
  playbook_runner_proxy: '172.16.1.58'
  music_server_proxy: '172.16.1.50'
route_proxy_container_ips:
  nextcloud_proxy_net: '172.16.1.34'
route_proxy_traefik_ips:
  nextcloud_proxy_net: '172.16.1.35'
  paperless_proxy_net: '172.16.1.43'
  playbook_runner_container_net: '172.16.1.59'
  music_server_container_net: '172.16.1.51'
proxy_config:
  - name: 'nextcloud_proxy'
    proxy_fqdn: 'cloud.example.com'
    proxy_upstream_port: '80'
    proxy_upstream_protocol: 'http'
    container_destination: '{{ container_dns.aliases.nextcloud_proxy }}.{{ container_dns.domain }}'
    proxy_network: 'nextcloud_proxy_net'
container_service_names: 'postgres_container redis_container nextcloud_container paperless_ngx vaultwarden'
container_network_migrations:
  - name: 'nextcloud_proxy_net'
    subnet: '172.16.1.32/29'
    internal: true
  - name: 'traefik_egress_net'
    subnet: ''
    internal: false
postgres_image: 'docker.io/postgres@sha256:2222222222222222222222222222222222222222222222222222222222222222'
postgres_path: '/srv/postgres'
nextcloud_image: 'docker.io/nextcloud@sha256:4444444444444444444444444444444444444444444444444444444444444444'
nextcloud_path: '/srv/nextcloud'
redis_image: 'docker.io/redis@sha256:3333333333333333333333333333333333333333333333333333333333333333'
paperless_image: 'ghcr.io/paperless-ngx/paperless-ngx@sha256:5555555555555555555555555555555555555555555555555555555555555555'
paperless_data_path: '/srv/paperless/data'
paperless_media_path: '/srv/paperless/media'
paperless_export_path: '/srv/paperless/export'
paperless_consume_path: '/srv/paperless/consume'
backup_local: true
vaultwarden_path: '/srv/vaultwarden'
vaultwarden_image: 'docker.io/vaultwarden/server@sha256:7777777777777777777777777777777777777777777777777777777777777777'
vaultwarden_backup_location: 'Nextcloud:vaultwarden_backup'
playbook_runner_path: '/srv/playbook-runner'
playbook_runner_image: 'ghcr.io/matthewdavidmiller/playbook-runner@sha256:9999999999999999999999999999999999999999999999999999999999999999'
playbook_runner_admin_password: 'run;admin "quoted" \\ slash & dollars \$HOME'
playbook_runner_timezone: 'America/New_York'
playbook_runner_keep_runs: 500
playbook_runner_uid: '10001'
playbook_runner_gid: '10001'
playbook_runner_egress_network: 'playbook_runner_egress_net'
playbook_runner_backup_location: 'Nextcloud:playbook_runner_backup'
music_server_path: '/srv/music-server'
music_server_music_path: '/srv/nextcloud/data/admin/files/Music'
music_server_image: 'ghcr.io/matthewdavidmiller/music-server@sha256:8888888888888888888888888888888888888888888888888888888888888888'
music_server_users:
  - name: 'alice'
    password: 'music;pw "quoted" \\ slash & dollars \$HOME'
    admin: true
music_server_scan_interval_minutes: 60
music_server_max_transcodes: 2
music_server_memory: '512m'
music_server_uid: '10001'
music_server_gid: '10001'
music_server_music_gid: '33'
music_server_backup_location: 'Nextcloud:music_server_backup'
user_name: 'ansible'
EOF

cat > "$tmpdir/render.yml" <<EOF
---
- hosts: localhost
  gather_facts: false
  connection: local
  tasks:
    - name: Render dynamic_dns.env
      ansible.builtin.template:
        src: ${repo_root}/roles/dynamic_dns/templates/dynamic_dns.env.j2
        dest: ${render_dir}/dynamic_dns.env

    - name: Render traefik.env
      ansible.builtin.template:
        src: ${repo_root}/roles/reverse_proxy/templates/traefik.env.j2
        dest: ${render_dir}/traefik.env

    - name: Render postgres.env
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/postgres.env.j2
        dest: ${render_dir}/postgres.env

    - name: Render nextcloud.env
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/nextcloud.env.j2
        dest: ${render_dir}/nextcloud.env

    - name: Render paperless.env
      ansible.builtin.template:
        src: ${repo_root}/roles/paperless_ngx/templates/paperless.env.j2
        dest: ${render_dir}/paperless.env

    - name: Render traefik_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/reverse_proxy/templates/traefik_container.sh.j2
        dest: ${render_dir}/traefik_container.sh

    - name: Render traefik_container.service
      ansible.builtin.template:
        src: ${repo_root}/roles/reverse_proxy/templates/traefik_container.service.j2
        dest: ${render_dir}/traefik_container.service

    - name: Render Traefik security middleware
      ansible.builtin.template:
        src: ${repo_root}/roles/reverse_proxy/templates/security.yml.j2
        dest: ${render_dir}/security.yml

    - name: Render Traefik dashboard router
      ansible.builtin.template:
        src: ${repo_root}/roles/reverse_proxy/templates/dashboard.yml.j2
        dest: ${render_dir}/dashboard.yml

    - name: Render postgres_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/postgres_container.sh.j2
        dest: ${render_dir}/postgres_container.sh

    - name: Render nextcloud_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/nextcloud_container.sh.j2
        dest: ${render_dir}/nextcloud_container.sh

    - name: Render nextcloud_configure.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/nextcloud_configure.sh.j2
        dest: ${render_dir}/nextcloud_configure.sh

    - name: Render nextcloud_scan_path.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/nextcloud_scan_path.sh.j2
        dest: ${render_dir}/nextcloud_scan_path.sh

    - name: Render redis_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/redis_container.sh.j2
        dest: ${render_dir}/redis_container.sh

    - name: Render paperless_ngx.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/paperless_ngx/templates/paperless_ngx.sh.j2
        dest: ${render_dir}/paperless_ngx.sh

    - name: Render backup_vaultwarden.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/vaultwarden/templates/backup_db.j2
        dest: ${render_dir}/backup_vaultwarden.sh

    - name: Render playbook_runner.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/playbook_runner/templates/playbook_runner.sh.j2
        dest: ${render_dir}/playbook_runner.sh

    - name: Render backup_playbook_runner.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/playbook_runner/templates/backup_playbook_runner.sh.j2
        dest: ${render_dir}/backup_playbook_runner.sh

    - name: Render music_server.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/music_server/templates/music_server.sh.j2
        dest: ${render_dir}/music_server.sh

    - name: Render music_server.service
      ansible.builtin.template:
        src: ${repo_root}/roles/music_server/templates/music_server.service.j2
        dest: ${render_dir}/music_server.service

    - name: Render backup_music_server.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/music_server/templates/backup_music_server.sh.j2
        dest: ${render_dir}/backup_music_server.sh

    - name: Render migrate_container_networks.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/container_network_migration/templates/migrate_container_networks.sh.j2
        dest: ${render_dir}/migrate_container_networks.sh
EOF

ANSIBLE_LOCAL_TEMP="$tmpdir/.ansible-local" \
ANSIBLE_REMOTE_TEMP="$tmpdir/.ansible-remote" \
XDG_CACHE_HOME="$tmpdir/.cache" \
ansible-playbook -i localhost, "$tmpdir/render.yml" -e @"$tmpdir/vars.yml" >/dev/null

shellcheck "$render_dir/migrate_container_networks.sh"
pass "migrate_container_networks.sh passes ShellCheck after rendering"

shellcheck "$render_dir/nextcloud_scan_path.sh"
pass "nextcloud_scan_path.sh passes ShellCheck after rendering"

shellcheck "$render_dir/playbook_runner.sh" "$render_dir/backup_playbook_runner.sh"
pass "playbook_runner.sh and backup_playbook_runner.sh pass ShellCheck after rendering"

shellcheck "$render_dir/music_server.sh" "$render_dir/backup_music_server.sh"
pass "music_server.sh and backup_music_server.sh pass ShellCheck after rendering"

get_sourced_var() {
  local file="$1"
  local var_name="$2"

  bash -lc 'set -euo pipefail; file=$1; var_name=$2; set -a; . "$file"; set +a; printf "%s" "${!var_name}"' bash "$file" "$var_name"
}

assert_sourced_var() {
  local file="$1"
  local var_name="$2"
  local expected="$3"
  local label="$4"
  local actual

  actual=$(get_sourced_var "$file" "$var_name")
  if [ "$actual" = "$expected" ]; then
    pass "$label"
  else
    echo "Expected: $expected"
    echo "Actual:   $actual"
    fail "$label"
  fi
}

assert_contains() {
  local file="$1"
  local text="$2"
  local label="$3"

  grep -Fq -- "$text" "$file" && pass "$label" || fail "$label"
}

assert_line_before() {
  local file="$1"
  local first_text="$2"
  local second_text="$3"
  local label="$4"
  local first_line
  local second_line

  first_line=$(grep -n -F -- "$first_text" "$file" | head -n 1 | cut -d: -f1 || true)
  second_line=$(grep -n -F -- "$second_text" "$file" | head -n 1 | cut -d: -f1 || true)

  if [[ -n "$first_line" && -n "$second_line" && "$first_line" -lt "$second_line" ]]; then
    pass "$label"
  else
    fail "$label"
  fi
}

assert_not_contains() {
  local file="$1"
  local text="$2"
  local label="$3"

  if grep -Fq -- "$text" "$file"; then
    fail "$label"
  else
    pass "$label"
  fi
}

echo "=== Shell-Sourced Secret Env Regression Tests ==="

assert_contains "$render_dir/migrate_container_networks.sh" \
  "/usr/bin/podman network create --internal --subnet 172.16.1.32/29 nextcloud_proxy_net" \
  "migrate_container_networks.sh preserves internal network mode"
assert_contains "$render_dir/migrate_container_networks.sh" \
  "/usr/bin/podman network create traefik_egress_net" \
  "migrate_container_networks.sh preserves external egress network mode"
assert_not_contains "$render_dir/migrate_container_networks.sh" \
  "/usr/bin/podman network create --internal traefik_egress_net" \
  "migrate_container_networks.sh does not isolate egress networks"

assert_sourced_var "$render_dir/dynamic_dns.env" "PORKBUN_API_KEY" "$porkbun_api_key" "dynamic_dns.env preserves PORKBUN_API_KEY"
assert_sourced_var "$render_dir/dynamic_dns.env" "PORKBUN_SECRET_KEY" "$porkbun_secret_key" "dynamic_dns.env preserves PORKBUN_SECRET_KEY"
assert_sourced_var "$render_dir/traefik.env" "PORKBUN_SECRET_API_KEY" "$porkbun_secret_key" "traefik.env preserves PORKBUN_SECRET_API_KEY"
assert_sourced_var "$render_dir/postgres.env" "POSTGRES_PASSWORD" "$postgres_admin_password" "postgres.env preserves POSTGRES_PASSWORD"
assert_sourced_var "$render_dir/postgres.env" "NEXTCLOUD_DB_PASSWORD" "$nextcloud_db_password" "postgres.env preserves NEXTCLOUD_DB_PASSWORD"
assert_sourced_var "$render_dir/postgres.env" "PAPERLESS_DB_PASSWORD" "$paperless_db_password" "postgres.env preserves PAPERLESS_DB_PASSWORD"
assert_sourced_var "$render_dir/nextcloud.env" "NEXTCLOUD_ADMIN_PASSWORD" "$nextcloud_admin_password" "nextcloud.env preserves NEXTCLOUD_ADMIN_PASSWORD"
assert_sourced_var "$render_dir/nextcloud.env" "NEXTCLOUD_TRUSTED_DOMAINS" "$nextcloud_trusted_domains" "nextcloud.env preserves NEXTCLOUD_TRUSTED_DOMAINS"
assert_sourced_var "$render_dir/nextcloud.env" "POSTGRES_HOST" "test-postgres-backend.test.dns.podman" "nextcloud.env uses the backend Postgres alias"
assert_sourced_var "$render_dir/nextcloud.env" "REDIS_HOST" "test-redis-backend.test.dns.podman" "nextcloud.env uses the backend Redis alias"
assert_sourced_var "$render_dir/nextcloud.env" "TRUSTED_PROXIES" "172.16.1.32/29" "nextcloud.env trusts the proxy-facing network"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_DBPASS" "$paperless_db_password" "paperless.env preserves PAPERLESS_DBPASS"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_DBHOST" "test-postgres-backend.test.dns.podman" "paperless.env uses the backend Postgres alias"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_REDIS" "redis://test-redis-backend.test.dns.podman:6379" "paperless.env uses the backend Redis alias"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_SECRET_KEY" "$paperless_secret_key" "paperless.env preserves PAPERLESS_SECRET_KEY"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_DBENGINE" "postgresql" "paperless.env declares the PostgreSQL engine explicitly"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_TRUSTED_PROXIES" "172.16.1.43" "paperless.env trusts only the Traefik proxy hop"

assert_not_contains "$render_dir/traefik_container.sh" "--env-file" "traefik_container.sh no longer uses --env-file"
assert_contains "$render_dir/traefik_container.sh" '. "/etc/homelab/secrets/traefik.env"' "traefik_container.sh sources traefik.env"
assert_contains "$render_dir/traefik_container.sh" "--env PORKBUN_API_KEY" "traefik_container.sh passes PORKBUN_API_KEY"
assert_contains "$render_dir/traefik_container.sh" "--env PORKBUN_SECRET_API_KEY" "traefik_container.sh passes PORKBUN_SECRET_API_KEY"
assert_contains "$render_dir/traefik_container.sh" "--network=traefik_egress_net:alias=test-traefik-egress" "traefik_container.sh joins dedicated egress network with an alias"
assert_contains "$render_dir/traefik_container.sh" "--network=nextcloud_proxy_net:ip=172.16.1.35,alias=test-traefik-proxy" "traefik_container.sh joins route-declared proxy network with a static IP and alias"
# Podman hands an unpinned Traefik the first free subnet address, which is the
# one the service container requests; the second container to start then fails
# with "requested ip address ... is already allocated".
assert_not_contains "$render_dir/traefik_container.sh" "--network=nextcloud_proxy_net:alias=" "traefik_container.sh never leaves a route proxy address to Podman IPAM"
assert_not_contains "$render_dir/traefik_container.sh" "ip=172.16.1.34" "traefik_container.sh does not claim the Nextcloud backend address"
assert_contains "$render_dir/traefik_container.sh" "--add-host=test-nextcloud-proxy.test.dns.podman:172.16.1.34" "traefik_container.sh resolves Nextcloud proxy alias through /etc/hosts"
assert_line_before "$render_dir/traefik_container.sh" "--network=nextcloud_proxy_net" "--network=traefik_egress_net" "traefik_container.sh attaches app networks before egress for Podman DNS"
assert_not_contains "$render_dir/traefik_container.sh" "--network=nextcloud_container_net" "traefik_container.sh does not join backend network"
assert_not_contains "$render_dir/traefik_container.sh" "podman pull" "traefik_container.sh no longer calls podman pull"
assert_contains "$render_dir/traefik_container.sh" "--pull=never" "traefik_container.sh uses --pull=never"
assert_contains "$render_dir/traefik_container.service" "After=network-online.target postgres_container.service redis_container.service nextcloud_container.service paperless_ngx.service vaultwarden.service" "traefik_container.service orders after rendered backend service units"
assert_contains "$render_dir/security.yml" "dashboard-basic-auth:" "security.yml defines dashboard BasicAuth middleware"
assert_contains "$render_dir/security.yml" "basicAuth:" "security.yml renders Traefik BasicAuth config"
assert_contains "$render_dir/security.yml" 'admin:$apr1$example$T2v8QdKqzJ8D7c4s1bYhZ/' "security.yml renders configured dashboard user hash"
assert_contains "$render_dir/dashboard.yml" "dashboard-basic-auth@file" "dashboard.yml applies dashboard BasicAuth middleware"

assert_not_contains "$render_dir/postgres_container.sh" "--env-file" "postgres_container.sh no longer uses --env-file"
assert_contains "$render_dir/postgres_container.sh" '. "/etc/homelab/secrets/postgres.env"' "postgres_container.sh sources postgres.env"
assert_contains "$render_dir/postgres_container.sh" "--env POSTGRES_PASSWORD" "postgres_container.sh passes POSTGRES_PASSWORD"
assert_contains "$render_dir/postgres_container.sh" "--env NEXTCLOUD_DB_PASSWORD" "postgres_container.sh passes NEXTCLOUD_DB_PASSWORD"
assert_contains "$render_dir/postgres_container.sh" "--env PAPERLESS_DB_PASSWORD" "postgres_container.sh passes PAPERLESS_DB_PASSWORD"
assert_contains "$render_dir/postgres_container.sh" "--network=nextcloud_container_net:ip=172.16.1.2,alias=test-postgres-backend" "postgres_container.sh joins backend network with a static IP and alias"
assert_not_contains "$render_dir/postgres_container.sh" "podman pull" "postgres_container.sh no longer calls podman pull"
assert_contains "$render_dir/postgres_container.sh" "--pull=never" "postgres_container.sh uses --pull=never"
assert_contains "$render_dir/postgres_container.sh" "--mount type=tmpfs,destination=/var/run/postgresql,tmpfs-size=16M,tmpfs-mode=0750,U=true" "postgres_container.sh mounts service-owned socket tmpfs"
assert_not_contains "$render_dir/postgres_container.sh" '/run:/var/run/postgresql' "postgres_container.sh does not host-persist the socket directory"

assert_not_contains "$render_dir/nextcloud_container.sh" "--env-file" "nextcloud_container.sh no longer uses --env-file"
assert_contains "$render_dir/nextcloud_container.sh" '. "/etc/homelab/secrets/nextcloud.env"' "nextcloud_container.sh sources nextcloud.env"
assert_contains "$render_dir/nextcloud_container.sh" "--env NEXTCLOUD_ADMIN_PASSWORD" "nextcloud_container.sh passes NEXTCLOUD_ADMIN_PASSWORD"
assert_contains "$render_dir/nextcloud_container.sh" "--env NEXTCLOUD_TRUSTED_DOMAINS" "nextcloud_container.sh passes NEXTCLOUD_TRUSTED_DOMAINS"
assert_contains "$render_dir/nextcloud_container.sh" "--network=nextcloud_container_net:ip=172.16.1.4,alias=test-nextcloud-backend" "nextcloud_container.sh joins backend network with a static IP and alias"
assert_contains "$render_dir/nextcloud_container.sh" "--network=nextcloud_proxy_net:ip=172.16.1.34,alias=test-nextcloud-proxy" "nextcloud_container.sh joins proxy network with a static IP and alias"
assert_contains "$render_dir/nextcloud_container.sh" "--add-host=test-postgres-backend.test.dns.podman:172.16.1.2" "nextcloud_container.sh resolves Postgres alias through /etc/hosts"
assert_contains "$render_dir/nextcloud_container.sh" "--add-host=test-redis-backend.test.dns.podman:172.16.1.3" "nextcloud_container.sh resolves Redis alias through /etc/hosts"
assert_not_contains "$render_dir/nextcloud_container.sh" "podman pull" "nextcloud_container.sh no longer calls podman pull"
assert_contains "$render_dir/nextcloud_container.sh" "--pull=never" "nextcloud_container.sh uses --pull=never"
assert_contains "$render_dir/nextcloud_configure.sh" "cloud.example.com" "nextcloud_configure.sh reconciles configured trusted domains"
assert_contains "$render_dir/nextcloud_configure.sh" "172.16.1.32/29" "nextcloud_configure.sh reconciles trusted proxy CIDR"
assert_contains "$render_dir/nextcloud_configure.sh" "test-postgres-backend.test.dns.podman" "nextcloud_configure.sh reconciles persistent Postgres host"
assert_contains "$render_dir/nextcloud_configure.sh" "test-redis-backend.test.dns.podman" "nextcloud_configure.sh reconciles persistent Redis host"
assert_contains "$render_dir/nextcloud_configure.sh" "config:system:set overwrite.cli.url" "nextcloud_configure.sh reconciles overwrite CLI URL"
assert_contains "$render_dir/nextcloud_scan_path.sh" "--user 33:33" "nextcloud_scan_path.sh runs occ as the Nextcloud file owner"
assert_contains "$render_dir/nextcloud_scan_path.sh" "--workdir /var/www/html" "nextcloud_scan_path.sh sets an explicit Nextcloud working directory"
assert_contains "$render_dir/nextcloud_scan_path.sh" "nextcloud php /var/www/html/occ" "nextcloud_scan_path.sh uses the absolute occ path"
assert_contains "$render_dir/nextcloud_scan_path.sh" 'occ files:scan --path="$scan_path"' "nextcloud_scan_path.sh scans the requested path"
assert_contains "$render_dir/nextcloud_scan_path.sh" '/usr/bin/flock --wait "$lock_wait" 9' "nextcloud_scan_path.sh serializes simultaneous daily scans"
assert_contains "$render_dir/nextcloud_scan_path.sh" "max_attempts=12" "nextcloud_scan_path.sh retries transient scan failures"
assert_contains "$render_dir/nextcloud_scan_path.sh" "Unknown user" "nextcloud_scan_path.sh detects semantic occ failures"
assert_contains "$render_dir/nextcloud_scan_path.sh" "Error during scan" "nextcloud_scan_path.sh fails on per-file scan errors"
assert_contains "$render_dir/nextcloud_scan_path.sh" '[ "$scan_errors" -eq 0 ]' "nextcloud_scan_path.sh reads the summary Errors column"
assert_contains "$render_dir/nextcloud_scan_path.sh" "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" "nextcloud_scan_path.sh pins the PATH cron does not provide"
assert_contains "$render_dir/nextcloud_scan_path.sh" 'export HOME="${HOME:-/root}"' "nextcloud_scan_path.sh pins HOME for podman"
assert_contains "$render_dir/nextcloud_scan_path.sh" "/usr/bin/timeout --kill-after=30s" "nextcloud_scan_path.sh kills a hung occ instead of holding the lock"
assert_contains "$render_dir/nextcloud_scan_path.sh" "maintenance: true" "nextcloud_scan_path.sh waits out maintenance and upgrade mode"
assert_contains "$render_dir/nextcloud_scan_path.sh" 'occ info:file "$scan_path"' "nextcloud_scan_path.sh confirms the path reached the file cache"
assert_contains "$render_dir/nextcloud_scan_path.sh" '/srv/nextcloud/data${scan_path}' "nextcloud_scan_path.sh checks the on-disk path before scanning"

assert_not_contains "$render_dir/redis_container.sh" "--env-file" "redis_container.sh no longer uses --env-file"
assert_contains "$render_dir/redis_container.sh" '. "/etc/homelab/secrets/redis.env"' "redis_container.sh sources redis.env"
assert_contains "$render_dir/redis_container.sh" "--env TZ" "redis_container.sh passes TZ"
assert_contains "$render_dir/redis_container.sh" "--network=nextcloud_container_net:ip=172.16.1.3,alias=test-redis-backend" "redis_container.sh joins backend network with a static IP and alias"
assert_not_contains "$render_dir/redis_container.sh" "podman pull" "redis_container.sh no longer calls podman pull"
assert_contains "$render_dir/redis_container.sh" "--pull=never" "redis_container.sh uses --pull=never"

assert_not_contains "$render_dir/paperless_ngx.sh" "--env-file" "paperless_ngx.sh no longer uses --env-file"
assert_contains "$render_dir/paperless_ngx.sh" '. "/etc/homelab/secrets/paperless.env"' "paperless_ngx.sh sources paperless.env"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_DBPASS" "paperless_ngx.sh passes PAPERLESS_DBPASS"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_URL" "paperless_ngx.sh passes PAPERLESS_URL"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_SECRET_KEY" "paperless_ngx.sh passes PAPERLESS_SECRET_KEY"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_DBENGINE" "paperless_ngx.sh passes PAPERLESS_DBENGINE"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_TRUSTED_PROXIES" "paperless_ngx.sh passes PAPERLESS_TRUSTED_PROXIES"
assert_contains "$render_dir/paperless_ngx.sh" "--network=nextcloud_container_net:ip=172.16.1.5,alias=test-paperless-backend" "paperless_ngx.sh joins backend network with a static IP and alias"
assert_contains "$render_dir/paperless_ngx.sh" "--network=paperless_proxy_net:ip=172.16.1.42,alias=test-paperless-proxy" "paperless_ngx.sh joins proxy network with a static IP and alias"
assert_contains "$render_dir/paperless_ngx.sh" "--add-host=test-postgres-backend.test.dns.podman:172.16.1.2" "paperless_ngx.sh resolves Postgres alias through /etc/hosts"
assert_contains "$render_dir/paperless_ngx.sh" "--add-host=test-redis-backend.test.dns.podman:172.16.1.3" "paperless_ngx.sh resolves Redis alias through /etc/hosts"
assert_not_contains "$render_dir/paperless_ngx.sh" "podman pull" "paperless_ngx.sh no longer calls podman pull"
assert_contains "$render_dir/paperless_ngx.sh" "--pull=never" "paperless_ngx.sh uses --pull=never"

assert_contains "$render_dir/playbook_runner.sh" "--network=playbook_runner_container_net:ip=172.16.1.58,alias=test-playbook-runner-proxy" "playbook_runner.sh joins its proxy network with a static IP and alias"
assert_contains "$render_dir/playbook_runner.sh" "--network=playbook_runner_egress_net:alias=test-playbook-runner-egress" "playbook_runner.sh joins its egress network"
assert_not_contains "$render_dir/playbook_runner.sh" "nextcloud_container_net" "playbook_runner.sh stays off the backend network"
assert_contains "$render_dir/playbook_runner.sh" "--env PR_TRUSTED_PROXIES=172.16.1.59" "playbook_runner.sh trusts only Traefik's address for X-Forwarded-For"
assert_contains "$render_dir/playbook_runner.sh" "--secret playbook_runner_admin_password,target=/run/secrets/playbook_runner_admin_password" "playbook_runner.sh mounts the admin password as a secret when one is set"
assert_not_contains "$render_dir/playbook_runner.sh" "run;admin" "playbook_runner.sh never carries the admin password itself"
assert_contains "$render_dir/playbook_runner.sh" "--pull=never" "playbook_runner.sh uses --pull=never"
assert_contains "$render_dir/backup_playbook_runner.sh" "/usr/bin/tar -C \"/srv/playbook-runner\"" "backup_playbook_runner.sh archives the data directory"

assert_contains "$render_dir/music_server.sh" "--network=music_server_container_net:ip=172.16.1.50,alias=test-music-server-proxy" "music_server.sh joins its proxy network with a static IP and alias"
assert_not_contains "$render_dir/music_server.sh" "nextcloud_container_net" "music_server.sh stays off the backend network"
assert_contains "$render_dir/music_server.sh" "--env MS_TRUSTED_PROXIES=172.16.1.51" "music_server.sh trusts only Traefik's address for X-Forwarded-For"
assert_contains "$render_dir/music_server.sh" "--volume /srv/nextcloud/data/admin/files/Music:/music:ro,z" "music_server.sh mounts the music read-only"
assert_contains "$render_dir/music_server.sh" "--secret music_server_users,target=/run/secrets/music_server_users" "music_server.sh mounts the users file as a secret"
assert_not_contains "$render_dir/music_server.sh" "music;pw" "music_server.sh never carries a password itself"
assert_contains "$render_dir/music_server.sh" "--pull=never" "music_server.sh uses --pull=never"
assert_contains "$render_dir/music_server.service" "After=nextcloud_container.service" "music_server.service starts after Nextcloud when the music is in its data directory"
assert_contains "$render_dir/backup_music_server.sh" "/usr/bin/tar -C \"/srv/music-server/data\"" "backup_music_server.sh archives only the data directory"
assert_contains "$render_dir/backup_music_server.sh" '/usr/bin/install -o 33 -g 33 -m 0660 "$ARCHIVE" "$DEST/"' "backup_music_server.sh installs backups with the normalized Nextcloud file mode"


assert_contains "$render_dir/backup_vaultwarden.sh" '/usr/bin/install -d -o 33 -g 33 -m 0770 "$DEST"' "backup_vaultwarden.sh creates the Nextcloud destination with Nextcloud ownership"
assert_contains "$render_dir/backup_vaultwarden.sh" '/usr/bin/install -o 33 -g 33 -m 0660 "$BACKUP_FILE" "$DEST/"' "backup_vaultwarden.sh installs backups with the normalized Nextcloud file mode"
assert_not_contains "$render_dir/backup_vaultwarden.sh" '/usr/bin/cp "$BACKUP_FILE" "$DEST/"' "backup_vaultwarden.sh no longer copies backups as root"


for backup_script in backup_vaultwarden.sh backup_music_server.sh; do
  assert_contains "$render_dir/$backup_script" \
    '/usr/local/bin/nextcloud_scan_path.sh' \
    "$backup_script uses the managed Nextcloud scan helper"
  if grep -n 'nextcloud_scan_path.sh' "$render_dir/$backup_script" | grep -q '|| true'; then
    fail "$backup_script must not discard targeted scan failures"
  else
    pass "$backup_script reports targeted scan failures instead of discarding them"
  fi
done

echo "=== Regression tests complete. ==="

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

docker_username=$(cat <<'EOF'
docker user; "quoted" \ slash & dollars $HOME
EOF
)
docker_password=$(cat <<'EOF'
pa;ss "word" \ slash & dollars $HOME and 'single'
EOF
)
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
semaphore_db_password=$(cat <<'EOF'
sem;db "quoted" \ slash & dollars $HOME and 'single'
EOF
)
nextcloud_admin_password=$(cat <<'EOF'
nc;admin "quoted" \ slash & dollars $HOME and 'single'
EOF
)
semaphore_admin_password=$(cat <<'EOF'
sem;admin "quoted" \ slash & dollars $HOME and 'single'
EOF
)
semaphore_encryption_key=$(cat <<'EOF'
enc;key "quoted" \ slash & dollars $HOME and 'single'
EOF
)
nextcloud_trusted_domains=$(cat <<'EOF'
cloud.example.com cloud-alt.example.com
EOF
)
semaphore_ssh_args=$(cat <<'EOF'
-o UserKnownHostsFile=/etc/semaphore/ssh_known_hosts -o StrictHostKeyChecking=yes
EOF
)

cat > "$tmpdir/vars.yml" <<EOF
secret_env_dir: /etc/homelab/secrets
docker_username: 'docker user; "quoted" \ slash & dollars \$HOME'
docker_password: 'pa;ss "word" \ slash & dollars \$HOME and ''single'''
homelab_domain: 'example.com'
homelab_subdomain: 'dyn-sub'
porkbun_api_key: 'pk1_; "quoted" \ slash & dollars \$HOME'
porkbun_api_key_secret: 'sk1_; "quoted" \ slash & dollars \$HOME and ''single'''
postgres_admin_user: 'postgres-admin'
postgres_admin_password: 'pg;admin "quoted" \ slash & dollars \$HOME and ''single'''
nextcloud_database_name: 'nextcloud-db'
nextcloud_db_user: 'nextcloud-user'
nextcloud_db_password: 'nc;db "quoted" \ slash & dollars \$HOME and ''single'''
paperless_database_name: 'paperless-db'
paperless_db_user: 'paperless-user'
paperless_db_password: 'pl;db "quoted" \ slash & dollars \$HOME and ''single'''
semaphore_database_name: 'semaphore-db'
semaphore_db_user: 'semaphore-user'
semaphore_db_password: 'sem;db "quoted" \ slash & dollars \$HOME and ''single'''
nextcloud_admin_user: 'nextcloud-admin'
nextcloud_admin_password: 'nc;admin "quoted" \ slash & dollars \$HOME and ''single'''
nextcloud_trusted_domains: 'cloud.example.com cloud-alt.example.com'
nextcloud_dns_name: 'cloud.example.com'
paperless_dns_name: 'paperless.example.com'
semaphore_admin_name: 'sem-admin'
semaphore_admin_email: 'sem-admin@example.com'
semaphore_admin_password: 'sem;admin "quoted" \ slash & dollars \$HOME and ''single'''
semaphore_encryption_key: 'enc;key "quoted" \ slash & dollars \$HOME and ''single'''
traefik_image: 'docker.io/traefik:v3'
traefik_networks:
  - 'proxy_net'
  - 'backend_net'
traefik_path: '/srv/traefik'
postgres_image: 'docker.io/postgres:17'
postgres_path: '/srv/postgres'
nextcloud_image: 'docker.io/nextcloud:31-apache'
nextcloud_path: '/srv/nextcloud'
redis_image: 'docker.io/redis:7'
paperless_image: 'ghcr.io/paperless-ngx/paperless-ngx:2.14.7'
paperless_data_path: '/srv/paperless/data'
paperless_media_path: '/srv/paperless/media'
paperless_export_path: '/srv/paperless/export'
paperless_consume_path: '/srv/paperless/consume'
semaphore_image: 'docker.io/semaphoreui/semaphore:v2.13.6'
EOF

cat > "$tmpdir/render.yml" <<EOF
---
- hosts: localhost
  gather_facts: false
  connection: local
  tasks:
    - name: Render docker_login.env
      ansible.builtin.template:
        src: ${repo_root}/roles/standard_podman/templates/docker_login.env.j2
        dest: ${render_dir}/docker_login.env

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

    - name: Render semaphore.env
      ansible.builtin.template:
        src: ${repo_root}/roles/semaphore/templates/semaphore.env.j2
        dest: ${render_dir}/semaphore.env

    - name: Render login_to_docker.service
      ansible.builtin.template:
        src: ${repo_root}/roles/standard_podman/templates/login_to_docker.j2
        dest: ${render_dir}/login_to_docker.service

    - name: Render traefik_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/reverse_proxy/templates/traefik_container.sh.j2
        dest: ${render_dir}/traefik_container.sh

    - name: Render postgres_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/postgres_container.sh.j2
        dest: ${render_dir}/postgres_container.sh

    - name: Render nextcloud_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/nextcloud_container.sh.j2
        dest: ${render_dir}/nextcloud_container.sh

    - name: Render redis_container.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/nextcloud/templates/redis_container.sh.j2
        dest: ${render_dir}/redis_container.sh

    - name: Render paperless_ngx.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/paperless_ngx/templates/paperless_ngx.sh.j2
        dest: ${render_dir}/paperless_ngx.sh

    - name: Render semaphore.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/semaphore/templates/semaphore.sh.j2
        dest: ${render_dir}/semaphore.sh
EOF

ANSIBLE_LOCAL_TEMP="$tmpdir/.ansible-local" \
ANSIBLE_REMOTE_TEMP="$tmpdir/.ansible-remote" \
XDG_CACHE_HOME="$tmpdir/.cache" \
ansible-playbook -i localhost, "$tmpdir/render.yml" -e @"$tmpdir/vars.yml" >/dev/null

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

assert_sourced_var "$render_dir/docker_login.env" "DOCKER_USERNAME" "$docker_username" "docker_login.env preserves DOCKER_USERNAME"
assert_sourced_var "$render_dir/docker_login.env" "DOCKER_PASSWORD" "$docker_password" "docker_login.env preserves DOCKER_PASSWORD"
assert_sourced_var "$render_dir/dynamic_dns.env" "PORKBUN_API_KEY" "$porkbun_api_key" "dynamic_dns.env preserves PORKBUN_API_KEY"
assert_sourced_var "$render_dir/dynamic_dns.env" "PORKBUN_SECRET_KEY" "$porkbun_secret_key" "dynamic_dns.env preserves PORKBUN_SECRET_KEY"
assert_sourced_var "$render_dir/traefik.env" "PORKBUN_SECRET_API_KEY" "$porkbun_secret_key" "traefik.env preserves PORKBUN_SECRET_API_KEY"
assert_sourced_var "$render_dir/postgres.env" "POSTGRES_PASSWORD" "$postgres_admin_password" "postgres.env preserves POSTGRES_PASSWORD"
assert_sourced_var "$render_dir/postgres.env" "NEXTCLOUD_DB_PASSWORD" "$nextcloud_db_password" "postgres.env preserves NEXTCLOUD_DB_PASSWORD"
assert_sourced_var "$render_dir/postgres.env" "PAPERLESS_DB_PASSWORD" "$paperless_db_password" "postgres.env preserves PAPERLESS_DB_PASSWORD"
assert_sourced_var "$render_dir/postgres.env" "SEMAPHORE_DB_PASSWORD" "$semaphore_db_password" "postgres.env preserves SEMAPHORE_DB_PASSWORD"
assert_sourced_var "$render_dir/nextcloud.env" "NEXTCLOUD_ADMIN_PASSWORD" "$nextcloud_admin_password" "nextcloud.env preserves NEXTCLOUD_ADMIN_PASSWORD"
assert_sourced_var "$render_dir/nextcloud.env" "NEXTCLOUD_TRUSTED_DOMAINS" "$nextcloud_trusted_domains" "nextcloud.env preserves NEXTCLOUD_TRUSTED_DOMAINS"
assert_sourced_var "$render_dir/paperless.env" "PAPERLESS_DBPASS" "$paperless_db_password" "paperless.env preserves PAPERLESS_DBPASS"
assert_sourced_var "$render_dir/semaphore.env" "SEMAPHORE_ADMIN_PASSWORD" "$semaphore_admin_password" "semaphore.env preserves SEMAPHORE_ADMIN_PASSWORD"
assert_sourced_var "$render_dir/semaphore.env" "SEMAPHORE_ACCESS_KEY_ENCRYPTION" "$semaphore_encryption_key" "semaphore.env preserves SEMAPHORE_ACCESS_KEY_ENCRYPTION"
assert_sourced_var "$render_dir/semaphore.env" "ANSIBLE_SSH_ARGS" "$semaphore_ssh_args" "semaphore.env preserves ANSIBLE_SSH_ARGS"

assert_not_contains "$render_dir/login_to_docker.service" "EnvironmentFile=" "login_to_docker.service no longer uses EnvironmentFile"
assert_contains "$render_dir/login_to_docker.service" '. "/etc/homelab/secrets/docker_login.env"' "login_to_docker.service sources docker_login.env"

assert_not_contains "$render_dir/traefik_container.sh" "--env-file" "traefik_container.sh no longer uses --env-file"
assert_contains "$render_dir/traefik_container.sh" '. "/etc/homelab/secrets/traefik.env"' "traefik_container.sh sources traefik.env"
assert_contains "$render_dir/traefik_container.sh" "--env PORKBUN_API_KEY" "traefik_container.sh passes PORKBUN_API_KEY"
assert_contains "$render_dir/traefik_container.sh" "--env PORKBUN_SECRET_API_KEY" "traefik_container.sh passes PORKBUN_SECRET_API_KEY"

assert_not_contains "$render_dir/postgres_container.sh" "--env-file" "postgres_container.sh no longer uses --env-file"
assert_contains "$render_dir/postgres_container.sh" '. "/etc/homelab/secrets/postgres.env"' "postgres_container.sh sources postgres.env"
assert_contains "$render_dir/postgres_container.sh" "--env POSTGRES_PASSWORD" "postgres_container.sh passes POSTGRES_PASSWORD"
assert_contains "$render_dir/postgres_container.sh" "--env NEXTCLOUD_DB_PASSWORD" "postgres_container.sh passes NEXTCLOUD_DB_PASSWORD"
assert_contains "$render_dir/postgres_container.sh" "--env PAPERLESS_DB_PASSWORD" "postgres_container.sh passes PAPERLESS_DB_PASSWORD"
assert_contains "$render_dir/postgres_container.sh" "--env SEMAPHORE_DB_PASSWORD" "postgres_container.sh passes SEMAPHORE_DB_PASSWORD"

assert_not_contains "$render_dir/nextcloud_container.sh" "--env-file" "nextcloud_container.sh no longer uses --env-file"
assert_contains "$render_dir/nextcloud_container.sh" '. "/etc/homelab/secrets/nextcloud.env"' "nextcloud_container.sh sources nextcloud.env"
assert_contains "$render_dir/nextcloud_container.sh" "--env NEXTCLOUD_ADMIN_PASSWORD" "nextcloud_container.sh passes NEXTCLOUD_ADMIN_PASSWORD"
assert_contains "$render_dir/nextcloud_container.sh" "--env NEXTCLOUD_TRUSTED_DOMAINS" "nextcloud_container.sh passes NEXTCLOUD_TRUSTED_DOMAINS"

assert_not_contains "$render_dir/redis_container.sh" "--env-file" "redis_container.sh no longer uses --env-file"
assert_contains "$render_dir/redis_container.sh" '. "/etc/homelab/secrets/redis.env"' "redis_container.sh sources redis.env"
assert_contains "$render_dir/redis_container.sh" "--env TZ" "redis_container.sh passes TZ"

assert_not_contains "$render_dir/paperless_ngx.sh" "--env-file" "paperless_ngx.sh no longer uses --env-file"
assert_contains "$render_dir/paperless_ngx.sh" '. "/etc/homelab/secrets/paperless.env"' "paperless_ngx.sh sources paperless.env"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_DBPASS" "paperless_ngx.sh passes PAPERLESS_DBPASS"
assert_contains "$render_dir/paperless_ngx.sh" "--env PAPERLESS_URL" "paperless_ngx.sh passes PAPERLESS_URL"

assert_not_contains "$render_dir/semaphore.sh" "--env-file" "semaphore.sh no longer uses --env-file"
assert_contains "$render_dir/semaphore.sh" '. "/etc/homelab/secrets/semaphore.env"' "semaphore.sh sources semaphore.env"
assert_contains "$render_dir/semaphore.sh" "--env SEMAPHORE_ADMIN_PASSWORD" "semaphore.sh passes SEMAPHORE_ADMIN_PASSWORD"
assert_contains "$render_dir/semaphore.sh" "--env SEMAPHORE_ACCESS_KEY_ENCRYPTION" "semaphore.sh passes SEMAPHORE_ACCESS_KEY_ENCRYPTION"
assert_contains "$render_dir/semaphore.sh" "--env ANSIBLE_SSH_ARGS" "semaphore.sh passes ANSIBLE_SSH_ARGS"

echo "=== Regression tests complete. ==="

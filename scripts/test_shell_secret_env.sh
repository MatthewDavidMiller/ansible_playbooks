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

cat > "$tmpdir/vars.yml" <<EOF
secret_env_dir: /etc/homelab/secrets
homelab_domain: 'example.com'
homelab_subdomain: 'dyn-sub'
porkbun_api_key: 'pk1_; "quoted" \ slash & dollars \$HOME'
porkbun_api_key_secret: 'sk1_; "quoted" \ slash & dollars \$HOME and ''single'''
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
    vaultwarden_proxy: 'test-vaultwarden-proxy'
    playbook_runner_proxy: 'test-playbook-runner-proxy'
    playbook_runner_egress: 'test-playbook-runner-egress'
    music_server_proxy: 'test-music-server-proxy'
    homedrive_proxy: 'test-homedrive-proxy'
    traefik_proxy: 'test-traefik-proxy'
    traefik_egress: 'test-traefik-egress'
route_proxy_network_subnets:
  vaultwarden_container_net: '172.16.1.16/29'
container_static_ips:
  vaultwarden_proxy: '172.16.1.18'
  playbook_runner_proxy: '172.16.1.58'
  music_server_proxy: '172.16.1.50'
  homedrive_proxy: '172.16.1.66'
route_proxy_container_ips:
  vaultwarden_container_net: '172.16.1.18'
route_proxy_traefik_ips:
  vaultwarden_container_net: '172.16.1.19'
  playbook_runner_container_net: '172.16.1.59'
  music_server_container_net: '172.16.1.51'
  homedrive_container_net: '172.16.1.67'
proxy_config:
  - name: 'vaultwarden'
    proxy_fqdn: 'vault.example.com'
    proxy_upstream_port: '80'
    proxy_upstream_protocol: 'http'
    container_destination: '{{ container_dns.aliases.vaultwarden_proxy }}.{{ container_dns.domain }}'
    proxy_network: 'vaultwarden_container_net'
container_service_names: 'vaultwarden'
container_network_migrations:
  - name: 'vaultwarden_container_net'
    subnet: '172.16.1.16/29'
    internal: true
  - name: 'traefik_egress_net'
    subnet: ''
    internal: false
homedrive_backup_user: 'alice'
vaultwarden_path: '/srv/vaultwarden'
vaultwarden_image: 'docker.io/vaultwarden/server@sha256:7777777777777777777777777777777777777777777777777777777777777777'
vaultwarden_backup_location: 'vaultwarden_backup'
playbook_runner_path: '/srv/playbook-runner'
playbook_runner_image: 'ghcr.io/matthewdavidmiller/playbook-runner@sha256:9999999999999999999999999999999999999999999999999999999999999999'
playbook_runner_admin_password: 'run;admin "quoted" \\ slash & dollars \$HOME'
playbook_runner_timezone: 'America/New_York'
playbook_runner_keep_runs: 500
playbook_runner_uid: '10001'
playbook_runner_gid: '10001'
playbook_runner_egress_network: 'playbook_runner_egress_net'
playbook_runner_backup_location: 'playbook_runner_backup'
music_server_path: '/srv/music-server'
music_server_music_path: '/srv/music-library'
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
music_server_backup_location: 'music_server_backup'
homedrive_path: '/srv/homedrive/store'
homedrive_export_path: '/srv/homedrive/exports'
homedrive_exports: 'alice:Music=>music'
homedrive_image: 'ghcr.io/matthewdavidmiller/homedrive@sha256:6666666666666666666666666666666666666666666666666666666666666666'
homedrive_users:
  - name: 'alice'
    password: 'drive;pw "quoted" \\ slash & dollars \$HOME'
    admin: true
homedrive_min_free_gb: 10
homedrive_prune_keep: 7
homedrive_drill_sample: 20
homedrive_keep_all_days: 30
homedrive_trash_days: 90
homedrive_memory: '1g'
homedrive_uid: '10001'
homedrive_gid: '10001'
homedrive_borg_repo: '/srv/backup/homedrive'
homedrive_drill_path: '/srv/backup/homedrive-drill'
homedrive_borg_passphrase: 'a test passphrase of some length'
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

    - name: Render homedrive.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/homedrive.sh.j2
        dest: ${render_dir}/homedrive.sh

    - name: Render homedrive.service
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/homedrive.service.j2
        dest: ${render_dir}/homedrive.service

    - name: Render homedrive_import_path.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/homedrive_import_path.sh.j2
        dest: ${render_dir}/homedrive_import_path.sh

    - name: Render homedrive_prune_path.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/homedrive_prune_path.sh.j2
        dest: ${render_dir}/homedrive_prune_path.sh

    - name: Render the daily backups with homedrive as their destination
      ansible.builtin.template:
        src: ${repo_root}/roles/{{ item.role }}/templates/{{ item.template }}
        dest: ${render_dir}/{{ item.dest }}
      vars:
        homedrive_backup_user: alice
      loop:
        - {role: vaultwarden, template: backup_db.j2, dest: backup_vaultwarden_homedrive.sh}
        - {role: playbook_runner, template: backup_playbook_runner.sh.j2, dest: backup_playbook_runner_homedrive.sh}
        - {role: music_server, template: backup_music_server.sh.j2, dest: backup_music_server_homedrive.sh}

    - name: Render homedrive_repair.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/homedrive_repair.sh.j2
        dest: ${render_dir}/homedrive_repair.sh

    - name: Render homedrive_restore_drill.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/homedrive_restore_drill.sh.j2
        dest: ${render_dir}/homedrive_restore_drill.sh

    - name: Render backup_homedrive.sh
      ansible.builtin.template:
        src: ${repo_root}/roles/homedrive/templates/backup_homedrive.sh.j2
        dest: ${render_dir}/backup_homedrive.sh

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

shellcheck "$render_dir/playbook_runner.sh" "$render_dir/backup_playbook_runner.sh"
pass "playbook_runner.sh and backup_playbook_runner.sh pass ShellCheck after rendering"

shellcheck "$render_dir/music_server.sh" "$render_dir/backup_music_server.sh"
pass "music_server.sh and backup_music_server.sh pass ShellCheck after rendering"

shellcheck "$render_dir/homedrive.sh" "$render_dir/homedrive_import_path.sh" "$render_dir/homedrive_prune_path.sh" "$render_dir/backup_homedrive.sh" "$render_dir/homedrive_repair.sh" "$render_dir/homedrive_restore_drill.sh"
pass "homedrive scripts pass ShellCheck after rendering"

shellcheck "$render_dir/backup_vaultwarden_homedrive.sh" "$render_dir/backup_playbook_runner_homedrive.sh" "$render_dir/backup_music_server_homedrive.sh"
pass "the daily backups pass ShellCheck with homedrive as their destination"


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
  "/usr/bin/podman network create --internal --subnet 172.16.1.16/29 vaultwarden_container_net" \
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

assert_not_contains "$render_dir/traefik_container.sh" "--env-file" "traefik_container.sh no longer uses --env-file"
assert_contains "$render_dir/traefik_container.sh" '. "/etc/homelab/secrets/traefik.env"' "traefik_container.sh sources traefik.env"
assert_contains "$render_dir/traefik_container.sh" "--env PORKBUN_API_KEY" "traefik_container.sh passes PORKBUN_API_KEY"
assert_contains "$render_dir/traefik_container.sh" "--env PORKBUN_SECRET_API_KEY" "traefik_container.sh passes PORKBUN_SECRET_API_KEY"
assert_contains "$render_dir/traefik_container.sh" "--network=traefik_egress_net:alias=test-traefik-egress" "traefik_container.sh joins dedicated egress network with an alias"
assert_contains "$render_dir/traefik_container.sh" "--network=vaultwarden_container_net:ip=172.16.1.19,alias=test-traefik-proxy" "traefik_container.sh joins route-declared proxy network with a static IP and alias"
# Podman hands an unpinned Traefik the first free subnet address, which is the
# one the service container requests; the second container to start then fails
# with "requested ip address ... is already allocated".
assert_not_contains "$render_dir/traefik_container.sh" "--network=vaultwarden_container_net:alias=" "traefik_container.sh never leaves a route proxy address to Podman IPAM"
assert_not_contains "$render_dir/traefik_container.sh" "ip=172.16.1.18" "traefik_container.sh does not claim the service's own address"
assert_contains "$render_dir/traefik_container.sh" "--add-host=test-vaultwarden-proxy.test.dns.podman:172.16.1.18" "traefik_container.sh resolves the Vaultwarden proxy alias through /etc/hosts"
assert_line_before "$render_dir/traefik_container.sh" "--network=vaultwarden_container_net" "--network=traefik_egress_net" "traefik_container.sh attaches app networks before egress for Podman DNS"
assert_not_contains "$render_dir/traefik_container.sh" "--network=nextcloud_container_net" "traefik_container.sh does not join backend network"
assert_not_contains "$render_dir/traefik_container.sh" "podman pull" "traefik_container.sh no longer calls podman pull"
assert_contains "$render_dir/traefik_container.sh" "--pull=never" "traefik_container.sh uses --pull=never"
assert_contains "$render_dir/traefik_container.service" "After=network-online.target vaultwarden.service" "traefik_container.service orders after rendered backend service units"
assert_contains "$render_dir/security.yml" "dashboard-basic-auth:" "security.yml defines dashboard BasicAuth middleware"
assert_contains "$render_dir/security.yml" "basicAuth:" "security.yml renders Traefik BasicAuth config"
assert_contains "$render_dir/security.yml" 'admin:$apr1$example$T2v8QdKqzJ8D7c4s1bYhZ/' "security.yml renders configured dashboard user hash"
assert_contains "$render_dir/dashboard.yml" "dashboard-basic-auth@file" "dashboard.yml applies dashboard BasicAuth middleware"





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
assert_contains "$render_dir/music_server.sh" "--volume /srv/music-library:/music:ro,z" "music_server.sh mounts the music read-only"
assert_contains "$render_dir/music_server.sh" "--secret music_server_users,target=/run/secrets/music_server_users" "music_server.sh mounts the users file as a secret"
assert_not_contains "$render_dir/music_server.sh" "music;pw" "music_server.sh never carries a password itself"
assert_contains "$render_dir/music_server.sh" "--pull=never" "music_server.sh uses --pull=never"
assert_contains "$render_dir/homedrive.sh" "--network=homedrive_container_net:ip=172.16.1.66,alias=test-homedrive-proxy" "homedrive.sh joins its proxy network with a pinned address"
assert_contains "$render_dir/homedrive_repair.sh" "--network=none" "homedrive_repair.sh runs the repair without a network"
assert_contains "$render_dir/homedrive_repair.sh" '--volume "$src:/repair/$i:ro,z"' "homedrive_repair.sh mounts the backup copies read-only"
assert_not_contains "$render_dir/homedrive_repair.sh" "label=disable" "homedrive_repair.sh keeps SELinux separation"
assert_contains "$render_dir/homedrive_repair.sh" "/usr/bin/systemctl start homedrive.service" "homedrive_repair.sh starts the server again"
assert_contains "$render_dir/backup_homedrive.sh" '/usr/bin/borg check --lock-wait 3600 "$REPO"' "backup_homedrive.sh checks the backup repository weekly"
assert_contains "$render_dir/backup_homedrive.sh" 'report local --ok' "backup_homedrive.sh reports each local run to homedrive"
assert_not_contains "$render_dir/backup_homedrive.sh" '/usr/local/bin/homedrive_restore_drill.sh' "backup_homedrive.sh never runs a restore drill itself (drills run when asked for)"
assert_contains "$render_dir/homedrive_restore_drill.sh" 'drill-plan --sample' "homedrive_restore_drill.sh has the light drill"
assert_not_contains "$render_dir/homedrive_restore_drill.sh" '[ "$KEEP" = true ] && echo' "homedrive_restore_drill.sh exits 0 after a drill that passed without --keep"
assert_contains "$render_dir/backup_homedrive.sh" '/usr/bin/stat -c %d "$STORE")" = "$(/usr/bin/stat -c %d "$REPO")"' "backup_homedrive.sh reports a repository on the store's own disk"
assert_contains "$render_dir/backup_homedrive.sh" "--encryption=repokey-blake2" "backup_homedrive.sh encrypts a new repository when a passphrase is set"
assert_contains "$render_dir/backup_homedrive.sh" 'BORG_PASSCOMMAND="/usr/bin/cat /etc/homelab/secrets/homedrive_borg_passphrase"' "backup_homedrive.sh reads the passphrase from its root-only file"
assert_not_contains "$render_dir/backup_homedrive.sh" "a test passphrase" "backup_homedrive.sh never carries the passphrase itself"
assert_contains "$render_dir/homedrive_restore_drill.sh" "BORG_PASSCOMMAND" "homedrive_restore_drill.sh can open an encrypted repository"
assert_contains "$render_dir/homedrive_restore_drill.sh" "--network=none" "homedrive_restore_drill.sh restores without a network"
assert_contains "$render_dir/homedrive_restore_drill.sh" "restore-drill --to /restore" "homedrive_restore_drill.sh restores every drive to plain files"
assert_contains "$render_dir/homedrive_restore_drill.sh" "hd-server drill-compare" "homedrive_restore_drill.sh compares the restore with the live drive"
assert_contains "$render_dir/homedrive_restore_drill.sh" "report-backup --kind drill" "homedrive_restore_drill.sh reports its result to homedrive"
assert_not_contains "$render_dir/homedrive_restore_drill.sh" "label=disable" "homedrive_restore_drill.sh keeps SELinux separation"

# The drill deletes its scratch space. Run its own guard functions (taken
# from the rendered script) against real directories: scratch space that
# overlaps the store or the backups, or holds files the drill did not put
# there, is refused and nothing is deleted.
drill_guard="$tmpdir/drill_guard.sh"
awk '/^MARKER=/,/^cleanup\(\)/' "$render_dir/homedrive_restore_drill.sh" \
  | sed -e '$d' -e 's#/usr/bin/##g' > "$drill_guard"
grep -q 'check_scratch()' "$drill_guard" || fail "homedrive_restore_drill.sh defines its scratch guard"
drill_case() {  # drill_case SCRATCH STORE REPO: 0 if the drill would use SCRATCH
  (
    # shellcheck disable=SC2034 # read by the sourced guard functions
    SCRATCH="$1" STORE="$2" REPO="$3"
    # shellcheck source=/dev/null
    . "$drill_guard"
    check_scratch >/dev/null && empty_scratch
  )
}
d="$tmpdir/drill"
mkdir -p "$d/hd/store/meta" "$d/backup/repo" "$d/elsewhere"
echo keep > "$d/hd/store/store.id"
ln -s "$d/hd" "$d/link-to-hd"
for scratch in "$d/hd" "$d/hd/store" "$d/hd/store/x" "$d/backup" "$d/link-to-hd"; do
  if drill_case "$scratch" "$d/hd/store" "$d/backup/repo"; then
    fail "the drill refuses scratch space $scratch overlapping the store or backups"
  fi
done
[ -f "$d/hd/store/store.id" ] || fail "a refused drill deleted nothing"
# Its marker alone does not make space the drill's: the store moved in.
touch "$d/hd/.homedrive-drill-scratch"
if drill_case "$d/hd" "$d/hd/store" "$d/backup/repo"; then
  fail "the drill refuses marked scratch space that holds the store"
fi
[ -f "$d/hd/store/store.id" ] || fail "a refused drill deleted nothing"
# And space without its marker is never emptied, whatever calls it.
(
  SCRATCH="$d/elsewhere"
  # shellcheck source=/dev/null
  . "$drill_guard"
  mkdir -p "$SCRATCH/store"
  echo mine > "$SCRATCH/store/file"
  empty_scratch
)
[ -f "$d/elsewhere/store/file" ] || fail "the drill empties only marked scratch space"
mkdir -p "$d/elsewhere/store" && echo mine > "$d/elsewhere/store/file"
if drill_case "$d/elsewhere" "$d/hd/store" "$d/backup/repo"; then
  fail "the drill refuses scratch space holding files it did not put there"
fi
[ -f "$d/elsewhere/store/file" ] || fail "foreign scratch content survives"
mkdir -p "$d/scratch"
drill_case "$d/scratch" "$d/hd/store" "$d/backup/repo" || fail "the drill uses empty scratch space"
mkdir -p "$d/scratch/store/x" "$d/scratch/plain"
drill_case "$d/scratch" "$d/hd/store" "$d/backup/repo" || fail "the drill reuses its own scratch space"
[ ! -e "$d/scratch/store" ] && [ -f "$d/hd/store/store.id" ] \
  && pass "homedrive_restore_drill.sh empties only its own scratch space" \
  || fail "homedrive_restore_drill.sh empties only its own scratch space"
assert_not_contains "$render_dir/homedrive.sh" "nextcloud_container_net" "homedrive.sh stays off the backend network"
assert_contains "$render_dir/homedrive.sh" "--env HD_TRUSTED_PROXIES=172.16.1.67" "homedrive.sh trusts only Traefik's address for X-Forwarded-For"
assert_contains "$render_dir/homedrive.sh" "--volume /srv/homedrive/store:/var/lib/homedrive:Z" "homedrive.sh mounts the store privately"
assert_contains "$render_dir/homedrive.sh" "--volume /srv/homedrive/exports:/srv/exports:z" "homedrive.sh shares the exports with readers"
assert_contains "$render_dir/homedrive.sh" "--env HD_EXPORTS='alice:Music=>music'" "homedrive.sh passes the export spec, quoted"
assert_contains "$render_dir/homedrive.sh" "--secret homedrive_users,target=/run/secrets/homedrive_users" "homedrive.sh mounts the users file as a secret"
assert_not_contains "$render_dir/homedrive.sh" "drive;pw" "homedrive.sh never carries a password itself"
assert_contains "$render_dir/homedrive.sh" "--pull=never" "homedrive.sh uses --pull=never"
assert_contains "$render_dir/homedrive.service" "RequiresMountsFor=/srv/homedrive/store" "homedrive.service waits for the store's mount"
assert_contains "$render_dir/backup_homedrive.sh" "hd-server checkpoint" "backup_homedrive.sh checkpoints before backing up"
assert_contains "$render_dir/homedrive_import_path.sh" "podman exec -i homedrive hd-server import" "homedrive_import_path.sh imports through the admin socket"

# With homedrive as the destination, a backup is stored only through the
# server, and nothing is deleted by the script itself: old files go to the
# drive's trash through prune, which always keeps the newest few.
for backup_script in backup_vaultwarden_homedrive.sh backup_playbook_runner_homedrive.sh backup_music_server_homedrive.sh; do
  assert_contains "$render_dir/$backup_script" "/usr/local/bin/homedrive_import_path.sh alice" "$backup_script stores the backup through homedrive"
  assert_not_contains "$render_dir/$backup_script" "nextcloud" "$backup_script has nothing to do with Nextcloud"
  assert_not_contains "$render_dir/$backup_script" "-delete" "$backup_script deletes nothing itself"
  assert_not_contains "$render_dir/$backup_script" "rclone" "$backup_script does not use rclone"
done
assert_contains "$render_dir/backup_playbook_runner_homedrive.sh" "homedrive_prune_path.sh alice \\" "backup_playbook_runner.sh prunes through homedrive"
assert_contains "$render_dir/backup_playbook_runner_homedrive.sh" "'playbook_runner_*.tar.gz' 30" "backup_playbook_runner.sh prunes only its own files over 30 days old"
assert_contains "$render_dir/backup_music_server_homedrive.sh" "'music_server_*.tar.gz' 30" "backup_music_server.sh prunes only its own files over 30 days old"
assert_not_contains "$render_dir/backup_vaultwarden_homedrive.sh" "homedrive_prune_path" "backup_vaultwarden.sh keeps every day's file, as before"
assert_contains "$render_dir/homedrive_prune_path.sh" "--keep 7" "homedrive_prune_path.sh always keeps the newest seven"
assert_contains "$render_dir/backup_music_server.sh" "/usr/bin/tar -C \"/srv/music-server/data\"" "backup_music_server.sh archives only the data directory"

echo "=== Regression tests complete. ==="

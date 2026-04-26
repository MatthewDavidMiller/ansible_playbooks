#!/bin/bash

set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

assert_no_match() {
  local pattern="$1"
  local label="$2"
  shift 2
  if rg -n --glob '!archive/**' --glob '!.git/**' --glob '!scripts/test_supply_chain_policy.sh' "$pattern" "$@" >/tmp/supply_chain_policy.out 2>&1; then
    cat /tmp/supply_chain_policy.out
    fail "$label"
  fi
  pass "$label"
}

assert_no_fixed_match() {
  local text="$1"
  local label="$2"
  shift 2
  if rg -n -F --glob '!archive/**' --glob '!.git/**' --glob '!scripts/test_supply_chain_policy.sh' "$text" "$@" >/tmp/supply_chain_policy.out 2>&1; then
    cat /tmp/supply_chain_policy.out
    fail "$label"
  fi
  pass "$label"
}

assert_match() {
  local pattern="$1"
  local label="$2"
  shift 2
  if rg -n "$pattern" "$@" >/tmp/supply_chain_policy.out 2>&1; then
    pass "$label"
    return
  fi
  cat /tmp/supply_chain_policy.out
  fail "$label"
}

assert_not_tracked() {
  local label="$1"
  local path
  shift
  for path in "$@"; do
    if git ls-files --error-unmatch "$path" >/tmp/supply_chain_policy.out 2>&1; then
      cat /tmp/supply_chain_policy.out
      fail "$label"
    fi
  done
  pass "$label"
}

assert_task_has_no_log() {
  local file="$1"
  local dest="$2"
  local label="$3"

  awk -v dest="$dest" '
    $0 ~ dest { in_task=1; next }
    in_task && $0 ~ /^[[:space:]]*-[[:space:]]name:/ { exit 1 }
    in_task && $0 ~ /^[[:space:]]*no_log:[[:space:]]*true[[:space:]]*$/ { found=1; exit 0 }
    END { if (!found) exit 1 }
  ' "$file" && pass "$label" || fail "$label"
}

echo "=== Supply Chain Policy Checks ==="

assert_match "^artifact_locked_images:" "container artifact lock file exists" artifacts/containers.lock.yml
assert_match "^collections:" "pinned collection manifest exists" collections/requirements.yml
assert_no_fixed_match "--pull=newer" "maintained launch scripts do not auto-pull on start" roles docs scripts example_inventory.yml vm1.yml
assert_no_fixed_match "--privileged" "maintained launch scripts do not run privileged containers" roles docs scripts example_inventory.yml vm1.yml
assert_no_match "[:=][[:space:]]*[^[:space:]'\"]+:latest\\b" "maintained configuration does not use mutable latest tags" roles docs scripts example_inventory.yml vm1.yml
assert_no_match "artifact_registry_(host|username|password)" "maintained path does not require registry inventory variables" example_inventory.yml roles docs scripts vm1.yml
assert_no_match "state:[[:space:]]*latest" "maintained roles do not perform blanket latest-package convergence outside the update role" roles --glob '!roles/standard_update_packages/**'
assert_match "security:[[:space:]]*true" "standard_update_packages applies security-only updates during normal convergence" roles/standard_update_packages/tasks/main.yml
assert_match "ansible-galaxy collection install -r collections/requirements\\.yml" "control-node installs use the pinned collection manifest" scripts/desktop_local_ansible.sh docs/guides/getting-started.md
assert_no_match "ansible-galaxy collection install (community|ansible\\.posix)" "collection installs must not bypass the pinned requirements file" scripts docs
assert_no_match "\\.latest\\." "mutable cloud image URLs are not allowed" scripts/proxmox_initial_setup.py artifacts/cloud_images.lock.yml docs/guides/proxmox-setup.md
assert_not_tracked "real local Trivy VEX/ignore files are not committed" .trivyignore .trivyignore.yaml trivy-vex.json logs/.trivyignore logs/.trivyignore.yaml logs/trivy-vex.json logs/container-vulnerability-findings.log logs/container-vulnerability-remediation.md

echo "=== Security Design Policy Checks ==="

assert_no_fixed_match 'owner: "{{ user_name }}"' "root-run maintained scripts are not owned by the SSH user" roles
assert_no_fixed_match "UsePAM no" "SSH keeps PAM session/account controls available" roles/standard_ssh/templates/10-standard-hardening.conf.j2
assert_match "PasswordAuthentication no" "SSH disables password authentication" roles/standard_ssh/templates/10-standard-hardening.conf.j2
assert_match "PermitRootLogin no" "SSH disables root login" roles/standard_ssh/templates/10-standard-hardening.conf.j2
assert_match "X11Forwarding no" "SSH disables X11 forwarding" roles/standard_ssh/templates/10-standard-hardening.conf.j2
assert_match "AllowTcpForwarding no" "SSH disables TCP forwarding by default" roles/standard_ssh/templates/10-standard-hardening.conf.j2
assert_match "LogLevel VERBOSE" "SSH logs key auth details" roles/standard_ssh/templates/10-standard-hardening.conf.j2
assert_match "dashboard-basic-auth@file" "Traefik dashboard requires BasicAuth middleware" roles/reverse_proxy/templates/dashboard.yml.j2
assert_match "basicAuth:" "Traefik dashboard BasicAuth middleware is defined" roles/reverse_proxy/templates/security.yml.j2
assert_match "traefik_dashboard_basic_auth_users \\| length > 0" "reverse_proxy requires dashboard BasicAuth users" roles/reverse_proxy/tasks/main.yml
assert_match "management_network != '0[.]0[.]0[.]0/0'" "reverse_proxy rejects broad management CIDR" roles/reverse_proxy/tasks/main.yml
assert_match "ip_ansible != '0[.]0[.]0[.]0/0'" "reverse_proxy rejects broad Ansible CIDR" roles/reverse_proxy/tasks/main.yml
assert_match "Validate reverse proxy route definitions" "reverse_proxy validates route definitions" roles/reverse_proxy/tasks/main.yml
assert_match "Validate reverse proxy route names are unique" "reverse_proxy rejects duplicate route names and FQDNs" roles/reverse_proxy/tasks/main.yml
assert_match "Validate firewalld ingress inputs" "firewalld validates ingress inputs before applying policy" roles/standard_firewalld/tasks/main.yml
assert_match "management_network != '0[.]0[.]0[.]0/0'" "firewalld rejects broad management CIDR" roles/standard_firewalld/tasks/main.yml
assert_match "ip_ansible != '0[.]0[.]0[.]0/0'" "firewalld rejects broad Ansible CIDR" roles/standard_firewalld/tasks/main.yml
assert_match "owner: root" "backup role sets root ownership on managed backup paths/scripts" roles/backup/tasks/main.yml
assert_match "umask 077" "Borg backup script uses restrictive umask" roles/backup/templates/backup_files.sh.j2
assert_match "trap cleanup EXIT" "remote Borg backup unmounts through cleanup trap" roles/backup/templates/backup_files.sh.j2
assert_match "mode: \"0700\"" "Vaultwarden role restricts private data directories" roles/vaultwarden/tasks/main.yml

assert_task_has_no_log roles/dynamic_dns/tasks/main.yml 'dest:.*secret_env_dir.*/dynamic_dns[.]env' "dynamic_dns env rendering uses no_log"
assert_task_has_no_log roles/reverse_proxy/tasks/main.yml 'dest:.*secret_env_dir.*/traefik[.]env' "Traefik env rendering uses no_log"
assert_task_has_no_log roles/nextcloud/tasks/main.yml 'dest:.*secret_env_dir.*/postgres[.]env' "PostgreSQL env rendering uses no_log"
assert_task_has_no_log roles/nextcloud/tasks/main.yml 'dest:.*secret_env_dir.*/nextcloud[.]env' "Nextcloud env rendering uses no_log"
assert_task_has_no_log roles/paperless_ngx/tasks/main.yml 'dest:.*secret_env_dir.*/paperless[.]env' "Paperless env rendering uses no_log"
assert_task_has_no_log roles/semaphore/tasks/main.yml 'dest:.*secret_env_dir.*/semaphore[.]env' "Semaphore env rendering uses no_log"
assert_task_has_no_log roles/standard_rclone/tasks/main.yml 'dest:.*/root/[.]config/rclone/rclone[.]conf' "rclone config rendering uses no_log"

echo "=== Supply chain policy checks passed ==="

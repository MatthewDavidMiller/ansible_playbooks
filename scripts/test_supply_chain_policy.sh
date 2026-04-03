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

echo "=== Supply Chain Policy Checks ==="

assert_match "^artifact_locked_images:" "container artifact lock file exists" artifacts/containers.lock.yml
assert_match "^collections:" "pinned collection manifest exists" collections/requirements.yml
assert_no_fixed_match "--pull=newer" "maintained launch scripts do not auto-pull on start" roles docs scripts example_inventory.yml vm1.yml
assert_no_match "[:=][[:space:]]*[^[:space:]'\"]+:latest\\b" "maintained configuration does not use mutable latest tags" roles docs scripts example_inventory.yml vm1.yml
assert_no_match "artifact_registry_(host|username|password)" "maintained path does not require registry inventory variables" example_inventory.yml roles docs scripts vm1.yml
assert_no_match "state:[[:space:]]*latest" "maintained roles do not perform blanket latest-package convergence outside the update role" roles --glob '!roles/standard_update_packages/**'
assert_match "security:[[:space:]]*true" "standard_update_packages applies security-only updates during normal convergence" roles/standard_update_packages/tasks/main.yml
assert_match "ansible-galaxy collection install -r collections/requirements\\.yml" "control-node installs use the pinned collection manifest" scripts/desktop_local_ansible.sh docs/guides/getting-started.md
assert_no_match "ansible-galaxy collection install (community|ansible\\.posix)" "collection installs must not bypass the pinned requirements file" scripts docs
assert_no_match "\\.latest\\." "mutable cloud image URLs are not allowed" scripts/proxmox_initial_setup.py artifacts/cloud_images.lock.yml docs/guides/proxmox-setup.md

echo "=== Supply chain policy checks passed ==="

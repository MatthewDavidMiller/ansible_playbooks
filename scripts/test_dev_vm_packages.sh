#!/bin/bash
# Validate dev_vm package install strategy for Rocky Linux 10 / EPEL.
#
# Catches:
#   1. Policy regressions that reintroduce known-broken EPEL packages via dnf
#   2. dnf dependency resolution failures for the current package baseline
#   3. Missing pip-delivered Python CLI tools expected on the workstation
#
# Usage:
#   bash scripts/test_dev_vm_packages.sh
#   DEV_VM_PACKAGE_DEPSOLVE=0 bash scripts/test_dev_vm_packages.sh   # policy only
#   DEV_VM_PACKAGE_IMAGE=<immutable-rocky-digest-ref> bash scripts/test_dev_vm_packages.sh
#
# Requires: python3 + PyYAML (provided by ansible), and Podman or Docker for depsolve.

set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

defaults_file="roles/dev_vm/defaults/main.yml"
# Known pure-Python CLIs that historically break as EPEL RPMs on EL10 because
# of missing python3.XXdist(...) virtual provides. Keep them on pip --user.
pip_preferred_packages=(
  yamllint
  ansible-lint
  pre-commit
)

DEV_VM_PACKAGE_DEPSOLVE="${DEV_VM_PACKAGE_DEPSOLVE:-1}"
DEV_VM_PACKAGE_IMAGE="${DEV_VM_PACKAGE_IMAGE:-$(python3 -c 'import yaml; print(yaml.safe_load(open("artifacts/test_images.lock.yml"))["test_locked_images"]["rocky_linux_10"]["image"])')}"

[[ "$DEV_VM_PACKAGE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || fail "DEV_VM_PACKAGE_IMAGE must be an immutable digest reference"

command -v python3 >/dev/null 2>&1 || fail "python3 is required"

extract_lists() {
  python3 - "$defaults_file" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(f"PyYAML is required (ansible provides it): {exc}\n")
    sys.exit(2)

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text())
if not isinstance(data, dict):
    sys.stderr.write(f"{path}: expected a YAML mapping\n")
    sys.exit(2)

for key in ("dev_vm_packages", "dev_vm_python_user_packages"):
    value = data.get(key)
    if not isinstance(value, list) or not value:
        sys.stderr.write(f"{path}: {key} must be a non-empty list\n")
        sys.exit(2)
    print(key)
    for item in value:
        if not isinstance(item, str) or not item.strip():
            sys.stderr.write(f"{path}: {key} contains an empty/non-string entry\n")
            sys.exit(2)
        print(item)
    print("--")
PY
}

mapfile -t _raw_lists < <(extract_lists)

dev_vm_packages=()
dev_vm_python_user_packages=()
current=""
for line in "${_raw_lists[@]}"; do
  case "$line" in
    dev_vm_packages|dev_vm_python_user_packages)
      current="$line"
      continue
      ;;
    --)
      current=""
      continue
      ;;
  esac
  case "$current" in
    dev_vm_packages) dev_vm_packages+=("$line") ;;
    dev_vm_python_user_packages) dev_vm_python_user_packages+=("$line") ;;
    *) fail "unexpected package list parse state for line: $line" ;;
  esac
done

list_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

echo "=== dev_vm package policy checks ==="

[[ ${#dev_vm_packages[@]} -gt 0 ]] || fail "dev_vm_packages is empty"
[[ ${#dev_vm_python_user_packages[@]} -gt 0 ]] || fail "dev_vm_python_user_packages is empty"
pass "package lists are non-empty (${#dev_vm_packages[@]} dnf, ${#dev_vm_python_user_packages[@]} pip)"

for pkg in "${pip_preferred_packages[@]}"; do
  if list_contains "$pkg" "${dev_vm_packages[@]}"; then
    fail "$pkg must not be installed via dnf (EPEL EL10 python dist provides are fragile); use dev_vm_python_user_packages"
  fi
  if ! printf '%s\n' "${dev_vm_python_user_packages[@]}" | sed 's/[<>=!~].*$//' | rg -qx "$pkg"; then
    fail "$pkg must be installed via pip --user in dev_vm_python_user_packages"
  fi
  pass "$pkg is pip-delivered (not dnf)"
done

for pkg in "${dev_vm_python_user_packages[@]}"; do
  if list_contains "$pkg" "${dev_vm_packages[@]}"; then
    fail "$pkg is listed in both dnf and pip package lists"
  fi
done
pass "no overlap between dnf and pip package lists"

required_dnf=(
  tmux
  git
  nodejs
  npm
  python3
  python3-pip
  ansible-core
  podman
  fuse-overlayfs
  passt
  shadow-utils
  ShellCheck
  gh
)
for pkg in "${required_dnf[@]}"; do
  list_contains "$pkg" "${dev_vm_packages[@]}" || fail "required dnf package missing from dev_vm_packages: $pkg"
done
pass "required dnf baseline packages are present"

if ! printf '%s\n' "${dev_vm_packages[@]}" | rg -q '^c-ares[[:space:]]*>=[[:space:]]*1[.]34[.]6'; then
  fail "dev_vm_packages must require c-ares >= 1.34.6 for the Node.js 22 ares_query_dnsrec ABI"
fi
pass "Node.js c-ares ABI compatibility floor is present"

echo "=== dev_vm dnf dependency resolution (Rocky 10 + EPEL) ==="

if [[ "$DEV_VM_PACKAGE_DEPSOLVE" != "1" ]]; then
  echo "SKIP: dnf depsolve (DEV_VM_PACKAGE_DEPSOLVE=$DEV_VM_PACKAGE_DEPSOLVE)"
  echo "=== dev_vm package checks passed (policy only) ==="
  exit 0
fi

container_engine=""
if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
  container_engine=podman
elif command -v docker >/dev/null 2>&1; then
  container_engine=docker
else
  fail "a working Podman or Docker engine is required for package depsolve (or set DEV_VM_PACKAGE_DEPSOLVE=0)"
fi

base_pkgs_file=$(mktemp)
container_script=$(mktemp)
trap 'rm -f "$base_pkgs_file" "$container_script"' EXIT

printf '%s\n' "${dev_vm_packages[@]}" >"$base_pkgs_file"

cat >"$container_script" <<'EOS'
set -euo pipefail

mapfile -t base_pkgs < /tmp/dev_vm_base_pkgs.txt

dnf_resolve() {
  local label="$1"
  shift
  echo "Depsolving: $label"
  echo "  packages: $*"
  # --assumeno runs a full solver without downloading RPMs or mutating the image.
  # dnf exits non-zero when the user would answer "no"; treat solver errors only
  # (Problem:/nothing provides/No match) as failures.
  local out rc
  set +e
  out=$(dnf -y --assumeno install "$@" 2>&1)
  rc=$?
  set -e
  if echo "$out" | grep -Eq 'Problem:|nothing provides|No match for argument|Error: Unable to find|Conflicts:'; then
    echo "$out"
    echo "FAIL: $label did not resolve (dnf rc=$rc)"
    exit 1
  fi
  if ! echo "$out" | grep -Eq 'Dependencies resolved|Nothing to do|Package .* already installed'; then
    echo "$out"
    echo "FAIL: $label produced unexpected dnf output (dnf rc=$rc)"
    exit 1
  fi
  echo "PASS: $label resolves"
}

# Match vm2.yml / standard_update_packages: install EPEL and enable CRB.
# CRB is required for many EPEL packages (e.g. yamllint → python3-pathspec).
echo "Installing EPEL and enabling CRB (matching standard_update_packages)..."
dnf -y -q install dnf-plugins-core epel-release
if command -v crb >/dev/null 2>&1; then
  crb enable >/dev/null
elif dnf repolist --all 2>/dev/null | grep -qiE '(^|\s)crb(\s|$)'; then
  dnf config-manager --set-enabled crb
else
  echo "FAIL: CRB helper/repo not available in image"
  exit 1
fi
dnf -y -q makecache

# Regression fixture: without CRB, EPEL yamllint fails with the original error.
# Prove the broken mode still exists upstream so we never drop the CRB enable step.
echo "Regression: yamllint must fail depsolve when CRB is disabled..."
crb disable >/dev/null 2>&1 || dnf config-manager --set-disabled crb >/dev/null
dnf -y -q makecache
set +e
yamllint_out=$(dnf -y --assumeno install yamllint 2>&1)
set -e
if ! echo "$yamllint_out" | grep -Eq 'Problem:|nothing provides.*pathspec'; then
  echo "$yamllint_out"
  echo "FAIL: expected yamllint EPEL RPM to fail without CRB (repo composition may have changed)"
  exit 1
fi
echo "PASS: yamllint EPEL RPM fails without CRB (original regression still reproducible)"

echo "Re-enabling CRB (production path)..."
if command -v crb >/dev/null 2>&1; then
  crb enable >/dev/null
else
  dnf config-manager --set-enabled crb
fi
dnf -y -q makecache

echo "Regression: yamllint must resolve once CRB is enabled..."
dnf_resolve "yamllint (EPEL + CRB smoke)" yamllint

dnf_resolve "dev_vm_packages" "${base_pkgs[@]}"

echo "All dnf package sets resolved successfully"
EOS

echo "Running depsolve in $container_engine ($DEV_VM_PACKAGE_IMAGE)..."
# Feed the script on stdin so host /tmp mounts do not need exec (SELinux/noexec).
# Package lists are copied in as ordinary read-only data files.
"$container_engine" run --rm -i \
  -v "$base_pkgs_file:/tmp/dev_vm_base_pkgs.txt:ro,Z" \
  "$DEV_VM_PACKAGE_IMAGE" \
  bash -s <"$container_script"

pass "Rocky 10 + EPEL + CRB dnf depsolve for the rootless-Podman dev_vm package list"

echo "=== dev_vm package checks passed ==="

#!/bin/bash
# Central lint and syntax gate, shared by the Makefile, the local test runner,
# and the pre-commit hook.
#
# Runs inside the toolbox image (see scripts/toolbox.sh), which is where every
# linter this calls comes from.

set -euo pipefail

case "${1:-}" in
  "") ;;
  -h|--help)
    echo "Usage: $0"
    exit 0
    ;;
  *)
    echo "Usage: $0" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Keep validator caches out of the repository and working in restricted shells.
# The toolbox image already points these at its own writable HOME; these
# defaults are what a host run gets.
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/ansible-playbooks-cache}"
export ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-/tmp/ansible-playbooks-local}"
export ANSIBLE_REMOTE_TEMP="${ANSIBLE_REMOTE_TEMP:-/tmp/ansible-playbooks-remote}"

# There is no mode that runs a smaller lint set. A linter this environment
# lacks is a provisioning failure, and reporting it as a pass would hide every
# finding the linter exists to make.
MISSING_TOOLS=()
missing_tool() {
  echo "ERROR: $1 is required (run 'make install' to build the toolbox)" >&2
  MISSING_TOOLS+=("$1")
}

SYNTAX_CHECK_PLAYBOOKS=(vm1.yml homelab_vms.yml update_homelab_vms.yml reboot_vms.yml)
# A throwaway inline inventory: --syntax-check parses the play and its role
# tree, and needs the target group names to resolve, not real hosts.
SYNTAX_CHECK_INVENTORY='vm1,homelab,'

# Every bash script in the tree plus the hooks, which carry no extension.
# Discovered rather than listed so a new script is covered the moment it lands.
mapfile -d '' -t SHELL_SCRIPTS < <(
  find "${PROJECT_ROOT}" \
    -path "${PROJECT_ROOT}/.git" -prune -o \
    -path "${PROJECT_ROOT}/collections/ansible_collections" -prune -o \
    -path "${PROJECT_ROOT}/env" -prune -o \
    -path "${PROJECT_ROOT}/logs" -prune -o \
    -type f \( -name '*.sh' -o -path "${PROJECT_ROOT}/hooks/*" \) \
    -print0
)

echo "--- Bash syntax (${#SHELL_SCRIPTS[@]} scripts) ---"
for script in "${SHELL_SCRIPTS[@]}"; do
  bash -n "${script}"
done
echo "PASS: bash syntax"

echo ""
echo "--- ShellCheck ---"
if command -v shellcheck >/dev/null 2>&1; then
  # SC2015 (a && b || c), SC2016 (single-quoted $ in Jinja and SQL literals),
  # and SC2054 (commas inside quoted engine arguments) all fire on deliberate
  # idioms throughout these scripts.
  shellcheck -e SC2015,SC2016,SC2054 "${SHELL_SCRIPTS[@]}"
  echo "PASS: ShellCheck"
else
  missing_tool shellcheck
fi

echo ""
echo "--- YAML lint ---"
if command -v yamllint >/dev/null 2>&1; then
  # git ls-files rather than find, so the ignore rules in .gitignore decide
  # what is in scope and an untracked new file is still checked before commit.
  mapfile -t YAML_FILES < <(
    git ls-files --cached --others --exclude-standard '*.yml' '*.yaml' |
      while IFS= read -r path; do [[ -f "${path}" ]] && echo "${path}"; done
  )
  yamllint -c .yamllint.yml "${YAML_FILES[@]}"
  echo "PASS: YAML lint (${#YAML_FILES[@]} files)"
else
  missing_tool yamllint
fi

echo ""
echo "--- Python compilation ---"
python3 -m py_compile scripts/*.py filter_plugins/*.py tests/*.py
echo "PASS: Python compilation"

echo ""
echo "--- ansible-lint ---"
if command -v ansible-lint >/dev/null 2>&1; then
  ansible-lint
  echo "PASS: ansible-lint"
else
  missing_tool ansible-lint
fi

echo ""
echo "--- Ansible syntax check ---"
if command -v ansible-playbook >/dev/null 2>&1; then
  for playbook in "${SYNTAX_CHECK_PLAYBOOKS[@]}"; do
    [[ -f "${playbook}" ]] || continue
    ansible-playbook --syntax-check -i "${SYNTAX_CHECK_INVENTORY}" "${playbook}"
  done
  echo "PASS: ansible syntax check"
else
  missing_tool ansible-playbook
fi

if ((${#MISSING_TOOLS[@]} > 0)); then
  echo ""
  printf 'Missing required linters: %s\n' "${MISSING_TOOLS[*]}" >&2
  exit 1
fi

echo ""
echo "=== All linters passed ==="

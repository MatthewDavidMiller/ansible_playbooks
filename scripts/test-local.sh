#!/bin/bash
# Local validation runner: lint, supply-chain policy, Python unit tests, secret
# rendering, and the static container policy checks. No images are pulled.
#
# Usage: ./scripts/test-local.sh
#
# Runs inside the toolbox image (see scripts/toolbox.sh).
#
# The runtime container tests are deliberately not reachable from here. They
# need to talk to the engine through its own command line rather than through
# the toolbox's mounted socket, so they are driven from the host by
# scripts/run-runtime-container-tests.sh, which `make test-full` runs after
# this. See that script for why.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

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

# run_test LABEL COMMAND [ARG...]
#
# Every gate reports through here so the run's output names which checks
# actually executed. A gate invoked directly would still abort the run under
# `set -e`, but silently -- indistinguishable from one that was skipped.
run_test() {
  local label="$1"
  shift
  echo "=== ${label} ==="
  if "$@"; then
    echo -e "${GREEN}PASSED${NC}: ${label}"
  else
    echo -e "${RED}FAILED${NC}: ${label}"
    exit 1
  fi
  echo ""
}

echo "=== Ansible Playbooks validation ==="
echo "Project root: ${PROJECT_ROOT}"
echo ""

run_test "Lint and syntax" "${SCRIPT_DIR}/lint.sh"
run_test "Supply chain policy" bash "${SCRIPT_DIR}/test_supply_chain_policy.sh"
run_test "Artifact promotion policy" python3 "${SCRIPT_DIR}/promote_artifacts.py" --validate-policy
run_test "Python unit tests" python3 -m unittest discover -s tests -p 'test_*.py'
run_test "Secret rendering" bash "${SCRIPT_DIR}/test_shell_secret_env.sh"
run_test "Container static policy" bash "${SCRIPT_DIR}/test_container_security.sh" static

echo -e "${GREEN}=== All checks passed ===${NC}"
echo "Runtime container tests were not run. Use 'make test-full'."

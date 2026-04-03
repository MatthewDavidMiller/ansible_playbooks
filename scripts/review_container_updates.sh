#!/bin/bash
# Resolve updated container digests, verify them, and run the repo's
# supply-chain and container-hardening checks before deployment.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_ROOT"

python3 scripts/promote_artifacts.py --write "$@"
bash scripts/test_supply_chain_policy.sh
bash scripts/test_container_security.sh

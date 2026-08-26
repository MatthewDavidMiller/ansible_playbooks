#!/bin/bash
# Run the runtime container security suite against the host engine.
#
# Usage: ./scripts/run-runtime-container-tests.sh [target...]   (default: all)
#
# This is the one gate that cannot simply go through the toolbox the way the
# others do, because it is the only one that needs full fidelity from the
# engine's own command line rather than just somewhere to run.
#
# Podman's Docker-API compatibility layer rejects the `uid=`/`gid=` tmpfs mount
# options that the PostgreSQL socket fixture depends on -- it accepts `mode=`
# and `size=` on the same mount, so this is a gap in that layer, not a
# difference between the engines. Reached through it with a Docker client, the
# suite dies on `unknown mount option "uid=999"` before its first assertion.
#
# So the suite runs wherever it can talk to the engine natively: on the host
# when Podman owns it, and inside the toolbox when Docker does, which keeps
# the Docker case free of any host dependency beyond the engine itself.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

case "${1:-}" in
  -h|--help)
    sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
esac

SUITE=(bash "${SCRIPT_DIR}/test_container_security.sh" "$@")

# Deliberately the same preference order the suite itself uses, and the same
# usability test: an engine that does not answer is not a candidate.
for engine in docker podman; do
  if command -v "${engine}" >/dev/null 2>&1 && "${engine}" info >/dev/null 2>&1; then
    case "${engine}" in
      docker)
        echo "Running the runtime container suite in the toolbox (Docker host engine)."
        exec "${SCRIPT_DIR}/toolbox.sh" "${SUITE[@]}"
        ;;
      podman)
        echo "Running the runtime container suite on the host (Podman host engine)."
        echo "Podman's Docker-API layer cannot express the tmpfs uid= this suite needs,"
        echo "so it talks to Podman directly. This needs python3 with PyYAML on the host."
        if ! python3 -c 'import yaml' >/dev/null 2>&1; then
          echo "ERROR: python3 with PyYAML is required on the host for this suite." >&2
          echo "       It reads the pinned image digests out of the lock files." >&2
          exit 1
        fi
        exec env DOCKER=podman "${SUITE[@]}"
        ;;
    esac
  fi
done

echo "ERROR: no usable container engine found for the runtime container tests." >&2
echo "       Start Docker or Podman and confirm this user can reach its socket." >&2
exit 1

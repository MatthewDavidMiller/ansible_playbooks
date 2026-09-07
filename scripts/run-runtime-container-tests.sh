#!/bin/bash
# Run the runtime container security suite against the host's Podman.
#
# Usage: ./scripts/run-runtime-container-tests.sh [target...]   (default: all)
#
# This is the one gate that does not run inside the toolbox. Every other gate
# only needs somewhere to run; this one needs a local Podman rather than the
# podman-remote client the toolbox carries.
#
# Its fixtures are host directories it hands to containers running under the
# caller's subuid range, so setting them up and handing them back means
# entering that user namespace with `podman unshare chown`. The remote client
# refuses outright: "cannot use command \"podman unshare\" with the remote
# podman client". There is no remote form of it, because a user namespace is
# local to the machine that has the files.
#
# So the suite runs on the host, which is also where its Podman already is.
# That makes it the only part of this repository that wants something on the
# host besides Podman itself -- python3 with PyYAML, to read the pinned digests
# out of the lock files -- and it says so and stops rather than failing
# obscurely if that is missing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

case "${1:-}" in
  -h|--help)
    sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
esac

PODMAN="${PODMAN:-podman}"

if ! command -v "${PODMAN}" >/dev/null 2>&1 || ! "${PODMAN}" info >/dev/null 2>&1; then
  echo "ERROR: no usable Podman for the runtime container tests." >&2
  echo "       These gates run on rootless Podman; check 'podman info'." >&2
  exit 1
fi

if [[ "$("${PODMAN}" info --format '{{.Host.Security.Rootless}}' 2>/dev/null)" != "true" ]]; then
  echo "ERROR: Podman is running rootful." >&2
  echo "       The suite's fixture cleanup uses 'podman unshare', and its" >&2
  echo "       containers are expected to be unprivileged. Run it as an" >&2
  echo "       unprivileged user with rootless Podman set up." >&2
  exit 1
fi

if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  echo "ERROR: python3 with PyYAML is required on the host for this suite." >&2
  echo "       It reads the pinned image digests out of the lock files." >&2
  exit 1
fi

echo "Running the runtime container suite on the host against rootless Podman."
exec bash "${SCRIPT_DIR}/test_container_security.sh" "$@"

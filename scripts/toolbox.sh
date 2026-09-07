#!/bin/bash
# Run a validation gate inside the toolbox image.
#
# Usage: ./scripts/toolbox.sh <command> [args...]
#        ./scripts/toolbox.sh --build          Build (or rebuild) the image only
#        ./scripts/toolbox.sh --shell          Interactive shell in the toolbox
#
# Rootless Podman is the only engine this pipeline supports, and the only thing
# it needs from the host. ansible-core, ansible-lint, yamllint, shellcheck,
# Python, and the pinned collections all live in the image built from
# tools/toolbox/Dockerfile.
#
# Rootless is a requirement rather than a preference. A rootful engine runs the
# gate as real root, so every file a gate writes into the working tree comes
# back owned by root; rootless maps the caller to the container's root and
# --userns=keep-id maps the caller's uid to itself, so the tree stays theirs.
# Supporting both meant detecting which was in use and mapping uids two
# different ways, and getting that detection wrong is silent: the gate runs as
# a subuid and dies on a permission error somewhere inside the tree.
#
# Set PODMAN to point at a specific binary. It is word-split, so it takes a
# prefix:
#
#   PODMAN=/usr/local/bin/podman ./scripts/toolbox.sh ./scripts/lint.sh

set -euo pipefail

# Already inside the toolbox: run the command rather than nesting a container.
# The gates chain into each other and every entry point routes through here, so
# this is the ordinary case during a gate run, not an edge case.
if [[ -n "${ANSIBLE_PLAYBOOKS_IN_TOOLBOX:-}" && "${1:-}" != "--build" ]]; then
  [[ $# -gt 0 ]] || { echo "Usage: $0 <command> [args...]" >&2; exit 2; }
  exec "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOCKERFILE="${PROJECT_ROOT}/tools/toolbox/Dockerfile"
REQUIREMENTS="${PROJECT_ROOT}/tests/requirements-dev.txt"
COLLECTIONS="${PROJECT_ROOT}/collections/requirements.yml"
TEST_LOCK_FILE="${TEST_LOCK_FILE:-${PROJECT_ROOT}/artifacts/test_images.lock.yml}"
TOOLBOX_REPO=ansible-toolbox

# Where the host's Podman API socket is mounted inside the toolbox. The path is
# fixed rather than mirrored from the host, because the only thing that reads it
# in there is a podman-remote client this script points at it.
TOOLBOX_SOCKET=/run/podman/podman.sock

# The engine is an array, not a string: PODMAN may carry a prefix.
ENGINE=()

# Resolve the base image from the same lock file the runtime container tests
# read. Deliberately parsed with sed rather than a YAML library: this runs on
# the host, where the only thing this repository asks for is Podman, and PyYAML
# is not guaranteed to be installed.
alpine_ref() {
  local ref
  ref="$(
    sed -n 's|^[[:space:]]*image:[[:space:]]*\([^[:space:]]*alpine@sha256:[0-9a-f]\{64\}\)[[:space:]]*$|\1|p' \
      "${TEST_LOCK_FILE}" | head -n 1
  )"
  if [[ -z "${ref}" ]]; then
    echo "ERROR: no digest-pinned alpine image found in ${TEST_LOCK_FILE}" >&2
    return 1
  fi
  printf '%s\n' "${ref}"
}

# The tag is the digest of everything that determines what lands in the image.
# A changed base digest, Python pin, or collection version therefore names a
# different image, and the rebuild happens on the next gate run.
toolbox_tag() {
  local digest
  digest="$(
    {
      cat "${DOCKERFILE}" "${REQUIREMENTS}" "${COLLECTIONS}"
      alpine_ref
    } | sha256sum | cut -c1-16
  )"
  printf '%s:%s\n' "${TOOLBOX_REPO}" "${digest}"
}

# Drop the builds this one replaces.
#
# Content-hash tags mean a bumped pin names a new image and silently strands
# the old one. Without this, routine version bumps leave a pile of images
# nothing will ever run again.
#
# Failures are ignored on purpose: `rmi` refuses an image a container is still
# using, which is exactly what a gate running concurrently in the previous
# toolbox looks like. That one survives and is collected on the next build.
prune_superseded_toolboxes() {
  # Both the match below and this comparison are made on the unqualified name.
  # Podman lists a locally built image as localhost/<repo>:<tag> while the tag
  # computed here is bare, so comparing the qualified name would find no match
  # for the image just built, treat it as superseded, and delete it -- leaving
  # every gate run to rebuild from scratch.
  local keep="${1##*/}" image removed=0
  while read -r image; do
    [[ -n "${image}" && "${image##*/}" != "${keep}" ]] || continue
    if "${ENGINE[@]}" rmi "${image}" >/dev/null 2>&1; then
      removed=$((removed + 1))
    fi
  done < <(
    # Anchoring to either the start or a slash matches the local name without
    # also matching some other registry's image whose name merely ends in ours.
    "${ENGINE[@]}" images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null |
      grep -E "(^|/)${TOOLBOX_REPO}:" || true
  )
  ((removed > 0)) && echo "Removed ${removed} superseded toolbox image(s)." >&2
  return 0
}

build_toolbox() {
  local tag="$1" ref
  ref="$(alpine_ref)"
  echo "=== Building toolbox image ${tag} (base ${ref}) ===" >&2
  # --format docker: Podman defaults to OCI image metadata, which ignores the
  # Dockerfile's SHELL instruction.
  #
  # The build context is the repository root: the image copies the pinned
  # Python requirements and collection manifest out of the tree itself.
  "${ENGINE[@]}" build --format docker \
    --build-arg "ALPINE_REF=${ref}" \
    -f "${DOCKERFILE}" -t "${tag}" "${PROJECT_ROOT}"
  # Only after the build succeeded: a failed one leaves the previous image as
  # the only working toolbox on the machine.
  prune_superseded_toolboxes "${tag}"
}

# Resolve rootless Podman, or explain what is missing and stop.
#
# Usability is tested rather than assumed: an installed CLI that cannot reach a
# service fails slowly and confusingly several steps later.
#
# The rootless check asks the engine instead of inferring from its name, since
# Podman also runs rootful. It is deliberately not a fallback to some other
# mapping -- a rootful engine is rejected, because a gate that leaves root-owned
# files in a working tree is worse than one that refuses to start.
resolve_engine() {
  local -a requested=()
  read -r -a requested <<< "${PODMAN:-podman}" || true

  if ! command -v "${requested[0]}" >/dev/null 2>&1; then
    echo "ERROR: podman is not on PATH: ${requested[0]}" >&2
    echo "       This repository's gates run on rootless Podman only." >&2
    return 1
  fi

  if ! "${requested[@]}" info >/dev/null 2>&1; then
    echo "ERROR: '${requested[*]}' is installed but not usable as invoked." >&2
    echo "       Check 'podman info' and retry." >&2
    return 1
  fi

  if [[ "$("${requested[@]}" info --format '{{.Host.Security.Rootless}}' 2>/dev/null)" != "true" ]]; then
    echo "ERROR: '${requested[*]}' is running rootful." >&2
    echo "       The gates run rootless so their writes stay owned by you." >&2
    echo "       Run them as an unprivileged user with rootless Podman set up" >&2
    echo "       (subuid/subgid ranges and a user podman.socket)." >&2
    return 1
  fi

  ENGINE=("${requested[@]}")
  return 0
}

# The host's Podman API socket, which is what lets the image-review tooling
# start its pinned tool containers from inside the toolbox.
#
# CONTAINER_HOST wins if it names one, which is how anyone running the service
# somewhere non-default points at it. Otherwise this is the socket the user's
# podman.socket unit creates.
host_socket() {
  local candidate

  if [[ "${CONTAINER_HOST:-}" == unix://* ]]; then
    candidate="${CONTAINER_HOST#unix://}"
    if [[ -S "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  fi

  candidate="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
  if [[ -S "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  return 1
}

main() {
  local tag mode="run" socket=""

  case "${1:-}" in
    --build) mode="build"; shift ;;
    --shell) mode="shell"; shift ;;
    -h|--help)
      sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    "")
      echo "Usage: $0 <command> [args...]" >&2
      exit 2
      ;;
  esac

  resolve_engine
  tag="$(toolbox_tag)"

  if [[ "${mode}" == "build" ]]; then
    build_toolbox "${tag}"
    exit 0
  fi

  if ! "${ENGINE[@]}" image inspect "${tag}" >/dev/null 2>&1; then
    build_toolbox "${tag}"
  fi

  local -a engine_args=(
    run --rm
    # The repository is mounted at the same absolute path it occupies on the
    # host, not at a fixed /work. Containers started from in here run on the
    # host engine and are handed bind-mount paths; the host resolves those in
    # its own filesystem, so any other mount point would make it mount the
    # wrong directory without saying so.
    -v "${PROJECT_ROOT}:${PROJECT_ROOT}"
    # The host's /tmp, for the same reason: a temporary path created in here
    # and handed to the host engine has to name the same directory on both
    # sides, or the host silently creates an empty one in its place.
    -v /tmp:/tmp
    -w "${PROJECT_ROOT}"
    # Keep files a gate writes into the tree owned by the invoking user.
    #
    # Rootless Podman maps the caller to the container's root, so an unmapped
    # uid in there resolves to a subuid the caller does not own, and a gate
    # would leave the working tree littered with files belonging to uid 100999.
    # keep-id maps the caller's uid to itself inside the namespace, which is
    # what makes --user mean what it says.
    --userns=keep-id
    --user "$(id -u):$(id -g)"
  )

  if socket="$(host_socket)"; then
    engine_args+=(-v "${socket}:${TOOLBOX_SOCKET}")
    # The client in the image is podman-remote, which talks to that socket
    # through Podman's own API rather than the Docker-compatible one.
    engine_args+=(-e "CONTAINER_HOST=unix://${TOOLBOX_SOCKET}")
  else
    echo "WARNING: no Podman API socket found; image-review tool fallbacks will fail" >&2
    echo "         Enable it with: systemctl --user enable --now podman.socket" >&2
  fi

  if [[ "${mode}" == "shell" ]]; then
    engine_args+=(-it "${tag}" bash)
  else
    engine_args+=("${tag}" "$@")
  fi

  exec "${ENGINE[@]}" "${engine_args[@]}"
}

main "$@"

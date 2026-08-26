#!/bin/bash
# Run a validation gate inside the toolbox image.
#
# Usage: ./scripts/toolbox.sh <command> [args...]
#        ./scripts/toolbox.sh --build          Build (or rebuild) the image only
#        ./scripts/toolbox.sh --shell          Interactive shell in the toolbox
#
# Docker or Podman is the only thing this needs from the host. ansible-core,
# ansible-lint, yamllint, shellcheck, Python, and the pinned collections all
# live in the image built from tools/toolbox/Dockerfile.
#
# Rootless and rootful daemons are both supported. Which one is in use is
# detected, not configured: it decides where the socket is and how the
# container's uid has to be mapped to keep a gate's writes owned by the caller.
#
# Set DOCKER to choose an engine explicitly, matching the override
# scripts/test_container_security.sh already honors. It is word-split the same
# way that script splits it, so a prefix works too:
#
#   DOCKER=podman ./scripts/toolbox.sh ./scripts/lint.sh
#   DOCKER="sudo docker" ./scripts/toolbox.sh ./scripts/lint.sh

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

# The engine is an array, not a string: DOCKER may carry a prefix such as
# "sudo docker" on a workstation whose user is not in the docker group.
ENGINE=()
ENGINE_KIND=""
ENGINE_ROOTLESS=""

# Resolve the base image from the same lock file the runtime container tests
# read. Deliberately parsed with sed rather than a YAML library: this runs on
# the host, where the only thing this repository asks for is a container
# engine, and PyYAML is not guaranteed to be installed.
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
    # Anchoring to either the start or a slash matches both engines' naming
    # without also matching some other registry's image whose name merely ends
    # in ours.
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
  local -a build_args=(build --build-arg "ALPINE_REF=${ref}" -f "${DOCKERFILE}" -t "${tag}")
  if [[ "${ENGINE_KIND}" == "podman" ]]; then
    # Podman defaults to OCI image metadata, which ignores the Dockerfile's
    # SHELL instruction.
    build_args+=(--format docker)
  fi
  # The build context is the repository root: the image copies the pinned
  # Python requirements and collection manifest out of the tree itself.
  "${ENGINE[@]}" "${build_args[@]}" "${PROJECT_ROOT}"
  # Only after the build succeeded: a failed one leaves the previous image as
  # the only working toolbox on the machine.
  prune_superseded_toolboxes "${tag}"
}

# Which engine a command names, read from its last word so a prefixed override
# such as "sudo docker" still identifies itself.
engine_kind() {
  local -a words=("$@")
  case "$(basename "${words[-1]}")" in
    docker) printf 'docker\n' ;;
    podman) printf 'podman\n' ;;
    *) return 1 ;;
  esac
}

# Prefer Docker when both are usable, fall back to Podman, and honor an
# explicit DOCKER override -- the same order scripts/test_container_security.sh
# uses, so a gate and a hand-run test agree on which engine they are talking to.
resolve_engine() {
  local kind path
  local -a requested=()

  # Word-split on purpose, exactly as scripts/test_container_security.sh does
  # with its own $DOCKER: the value may be a command with arguments.
  read -r -a requested <<< "${DOCKER:-}" || true

  if ((${#requested[@]} > 0)); then
    if ! command -v "${requested[0]}" >/dev/null 2>&1; then
      echo "ERROR: requested container engine is not on PATH: ${requested[0]}" >&2
      return 1
    fi
    if ! kind="$(engine_kind "${requested[@]}")"; then
      echo "ERROR: DOCKER must name docker or podman: ${DOCKER}" >&2
      return 1
    fi
    if ! "${requested[@]}" info >/dev/null 2>&1; then
      echo "ERROR: '${DOCKER}' is installed but not usable as invoked." >&2
      echo "       Start the engine's service and confirm socket access, then retry." >&2
      return 1
    fi
    ENGINE=("${requested[@]}")
    ENGINE_KIND="${kind}"
    return 0
  fi

  for kind in docker podman; do
    path="$(command -v "${kind}" 2>/dev/null || true)"
    if [[ -n "${path}" ]] && "${path}" info >/dev/null 2>&1; then
      ENGINE=("${path}")
      ENGINE_KIND="${kind}"
      return 0
    fi
  done

  echo "ERROR: no usable container engine found." >&2
  echo "       Install Docker or Podman and make sure its service is running." >&2
  echo "       For rootless Docker, export DOCKER_HOST or start its user" >&2
  echo "       service; for a root-owned socket, either join the group that" >&2
  echo "       owns it or run the gate with DOCKER=\"sudo docker\"." >&2
  return 1
}

# Whether the resolved engine is rootless.
#
# This decides more than a flag name. A rootless daemon maps the invoking user
# to the container's root, so root in here is that user out there and any other
# container uid lands on a subuid the user does not own. Every choice below
# that exists to keep a gate's writes owned by the caller therefore turns on
# this, not on the engine's name.
detect_rootless() {
  local info=""
  if [[ "${ENGINE_KIND}" == "podman" ]]; then
    info="$("${ENGINE[@]}" info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
    [[ "${info}" == "true" ]] && ENGINE_ROOTLESS=1
  else
    info="$("${ENGINE[@]}" info --format '{{.SecurityOptions}}' 2>/dev/null || true)"
    [[ "${info}" == *rootless* ]] && ENGINE_ROOTLESS=1
  fi
  return 0
}

# The socket is what lets the runtime container tests and the image-review
# tooling start containers on the host engine. Podman's lives elsewhere and
# speaks the Docker API, so it is mounted where the toolbox's docker CLI looks.
#
# Candidates are ordered by whether the daemon we just talked to is rootless,
# rather than by a fixed preference. On a workstation running both a rootful
# and a rootless daemon, both sockets exist, and mounting the other one would
# point the runtime tests at a different daemon than the one holding the
# toolbox image.
host_socket() {
  local candidate user_run="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  local -a candidates=()

  # An explicit DOCKER_HOST wins outright: it is how a rootless daemon
  # advertises itself, and how anyone running several daemons picks one.
  if [[ "${DOCKER_HOST:-}" == unix://* ]]; then
    candidate="${DOCKER_HOST#unix://}"
    if [[ -S "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  fi

  if [[ "${ENGINE_KIND}" == "podman" ]]; then
    candidates=("${user_run}/podman/podman.sock" /run/podman/podman.sock)
    [[ -n "${ENGINE_ROOTLESS}" ]] || candidates=("${candidates[1]}" "${candidates[0]}")
  else
    candidates=(/var/run/docker.sock "${user_run}/docker.sock")
    [[ -z "${ENGINE_ROOTLESS}" ]] || candidates=("${candidates[1]}" "${candidates[0]}")
  fi

  for candidate in "${candidates[@]}"; do
    if [[ -S "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

main() {
  local tag mode="run" socket=""

  case "${1:-}" in
    --build) mode="build"; shift ;;
    --shell) mode="shell"; shift ;;
    -h|--help)
      sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    "")
      echo "Usage: $0 <command> [args...]" >&2
      exit 2
      ;;
  esac

  resolve_engine
  detect_rootless
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
    # host, not at a fixed /work. scripts/test_container_security.sh starts
    # containers through the socket below and hands them bind-mount paths; the
    # host engine resolves those in its own filesystem, so any other mount
    # point would make it mount the wrong directory without saying so.
    -v "${PROJECT_ROOT}:${PROJECT_ROOT}"
    # The host's /tmp, for the same reason: those tests build fixtures under
    # `mktemp -d` and bind-mount them into containers the host engine starts.
    # A private /tmp in here means the host creates an empty directory in its
    # place and the fixture is silently missing.
    -v /tmp:/tmp
    -w "${PROJECT_ROOT}"
  )

  # Keep files a gate writes into the tree owned by the invoking user rather
  # than by root.
  #
  # A rootful engine runs the container as whichever uid it is handed, so it is
  # handed the caller's. A rootless one already maps the caller to the
  # container's root: naming any other uid in there resolves to a subuid that
  # owns nothing the caller can read, and a gate would leave the working tree
  # littered with files belonging to uid 100999. Podman takes the inverse
  # instruction to line the uids back up; rootless Docker has no equivalent
  # flag and needs none, so it is left at root, which is this user.
  if [[ -z "${ENGINE_ROOTLESS}" ]]; then
    engine_args+=(--user "$(id -u):$(id -g)")
  elif [[ "${ENGINE_KIND}" == "podman" ]]; then
    engine_args+=(--userns=keep-id)
  fi

  if socket="$(host_socket)"; then
    engine_args+=(-v "${socket}:/var/run/docker.sock")
    # Inside the toolbox the only client is the docker CLI, whichever engine
    # owns the socket. Telling the runtime tests that directly keeps them from
    # re-running their own detection against a PATH that has no podman on it.
    engine_args+=(-e DOCKER=docker)
    # And tell them whether that daemon is rootless, which decides the uid
    # scripts/test_container_security.sh restores fixture ownership to. Over a
    # Docker-API socket the engine's own name no longer implies the answer, and
    # this side has already worked it out against the host's native CLI.
    if [[ -n "${ENGINE_ROOTLESS}" ]]; then
      engine_args+=(-e ENGINE_ROOTLESS=1)
    fi
    # A mapped non-root user cannot read the socket without holding the group
    # that owns it. A rootless daemon's socket is already owned by the caller,
    # who is the container's root.
    if [[ "${ENGINE_KIND}" == "docker" && -z "${ENGINE_ROOTLESS}" ]]; then
      engine_args+=(--group-add "$(stat -c %g "${socket}")")
    fi
  else
    echo "WARNING: no container engine socket found; runtime container tests will fail" >&2
  fi

  if [[ "${mode}" == "shell" ]]; then
    engine_args+=(-it "${tag}" bash)
  else
    engine_args+=("${tag}" "$@")
  fi

  exec "${ENGINE[@]}" "${engine_args[@]}"
}

main "$@"

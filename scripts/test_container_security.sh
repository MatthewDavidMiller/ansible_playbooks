#!/bin/bash
# Container security flag test script
# Tests container capability, privilege, and memory flags
# for the maintained VM1 services before deploying to production via Ansible.
#
# Usage: bash scripts/test_container_security.sh [all|static|traefik|vaultwarden|music_server|homedrive]...
#        bash scripts/test_container_security.sh vaultwarden 2>&1 | tee /tmp/container_test_results.txt
# See docs/testing.md for full descriptions of each test.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOCK_FILE=${LOCK_FILE:-"$REPO_ROOT/artifacts/containers.lock.yml"}
TEST_LOCK_FILE=${TEST_LOCK_FILE:-"$REPO_ROOT/artifacts/test_images.lock.yml"}
# Rootless Podman is the only engine these tests run against, and the runtime
# targets assume it: fixture ownership is set and restored with
# `podman unshare`, which is meaningless without the caller's user namespace.
# The static target needs no engine at all, so a missing or unusable Podman is
# only reported here and left to fail at the first runtime command.
PODMAN=${PODMAN:-podman}
# Runtime tests use disposable bind mounts; avoid relabeling host paths.
ENGINE_RUN=("$PODMAN" run --security-opt label=disable)
usage() {
  sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
}
should_run() {
  local selected
  for selected in "${SELECTED_TESTS[@]}"; do
    [[ "$selected" == all || "$selected" == "$1" ]] && return 0
  done
  return 1
}
SELECTED_TESTS=("${@:-all}")
for selected_test in "${SELECTED_TESTS[@]}"; do
  case "$selected_test" in
    all|static|traefik|vaultwarden|music_server|homedrive) ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown test target: $selected_test" >&2
      usage >&2
      exit 2
      ;;
  esac
done
lock_image_ref() {
  python3 - "$LOCK_FILE" "$1" <<'PY'
from pathlib import Path
import sys

import yaml

lock_file = Path(sys.argv[1])
service = sys.argv[2]
data = yaml.safe_load(lock_file.read_text(encoding="utf-8"))
entry = data["artifact_locked_images"][service]
upstream_ref = entry["upstream_ref"]
digest = entry["approved_digest"]

if "@" in upstream_ref:
    image_name = upstream_ref.rsplit("@", 1)[0]
else:
    last_slash = upstream_ref.rfind("/")
    last_colon = upstream_ref.rfind(":")
    if last_colon > last_slash:
        image_name = upstream_ref[:last_colon]
    else:
        image_name = upstream_ref

print(f"{image_name}@{digest}")
PY
}
test_image_ref() {
  python3 - "$TEST_LOCK_FILE" "$1" <<'PY'
from pathlib import Path
import sys
import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data["test_locked_images"][sys.argv[2]]["image"])
PY
}

TRAEFIK_IMAGE=${TRAEFIK_IMAGE:-$(lock_image_ref traefik)}
VAULTWARDEN_IMAGE=${VAULTWARDEN_IMAGE:-$(lock_image_ref vaultwarden)}
MUSIC_SERVER_IMAGE=${MUSIC_SERVER_IMAGE:-$(lock_image_ref music_server)}
HOMEDRIVE_IMAGE=${HOMEDRIVE_IMAGE:-$(lock_image_ref homedrive)}
TEST_HELPER_IMAGE=${TEST_HELPER_IMAGE:-$(test_image_ref alpine)}
[[ "$TEST_HELPER_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || {
  echo "TEST_HELPER_IMAGE must be an immutable digest reference" >&2
  exit 2
}

cleanup()     { $PODMAN rm -f "$1" >/dev/null 2>&1 || true; }
# A fixture directory has to be owned by the uid the container runs as, which
# under rootless Podman is a subuid the caller cannot chown to directly. Both
# helpers therefore work from inside the caller's user namespace, where those
# subuids are addressable and 0:0 is the caller.
chown_test_path() {
  local owner="$1" path="$2"
  shift 2
  $PODMAN unshare chown "$@" "$owner" "$path"
}
cleanup_dir() {
  # Hand the tree back before removing it: rm cannot touch a subuid-owned one.
  $PODMAN unshare chown -R 0:0 "$1"
  rm -rf "$1"
}
cleanup_all_test_containers() {
  local name
  for name in \
    test_homedrive \
    test_homedrive_init \
    test_homedrive_no_store \
    test_music_server \
    test_traefik_cap \
    test_traefik_nocap \
    test_vaultwarden
  do
    cleanup "$name"
  done
}
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }
assert_file_contains() {
  local pattern="$1" label="$2" file="$3"
  if rg -q -- "$pattern" "$file"; then
    pass "$label"
  else
    fail "$label"
  fi
}
assert_file_not_contains() {
  local pattern="$1" label="$2" file="$3"
  if rg -q -- "$pattern" "$file"; then
    fail "$label"
  else
    pass "$label"
  fi
}
check_running() {
  local name="$1" label="$2"
  sleep 5
  if $PODMAN inspect --format='{{.State.Status}}' "$name" 2>/dev/null | grep -q running; then
    pass "$label"
  else
    fail "$label"
  fi
}

trap cleanup_all_test_containers EXIT
cleanup_all_test_containers

echo "=== Container Security Flag Tests ==="
echo "Targets: ${SELECTED_TESTS[*]}"
if container_engine_version=$($PODMAN --version 2>/dev/null); then
  echo "Container engine: $container_engine_version"
else
  echo "Container engine: not available (required only for runtime targets)"
fi
echo "User: $(id)"
echo ""

if should_run static; then
echo "--- TEST-00: Static hardening and network containment policy ---"
assert_file_contains "container_dns[.]aliases[.]vaultwarden_proxy" "Vaultwarden: proxy DNS alias is dictionary-driven" roles/vaultwarden/templates/vaultwarden.sh.j2
assert_file_contains "container_dns[.]aliases[.]traefik_proxy" "Traefik: proxy DNS alias is dictionary-driven" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "container_dns[.]aliases[.]traefik_egress" "Traefik: egress DNS alias is dictionary-driven" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "--add-host=.*route_proxy_container_ips" "Traefik: resolves proxy route names through container hosts entries" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "route_proxy_container_ips" "reverse_proxy: requires deterministic route backend IPs" roles/reverse_proxy/tasks/main.yml
assert_file_contains "ip=\\{\\{ route_proxy_traefik_ips\\[net\\] \\}\\}" "Traefik: uses a deterministic IP on every route proxy network" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "route_proxy_traefik_ips" "reverse_proxy: validates Traefik route addresses against the service addresses" roles/reverse_proxy/tasks/main.yml
assert_file_contains "route_proxy_traefik_ips" "reverse_proxy defaults: ships deterministic Traefik route addresses" roles/reverse_proxy/defaults/main.yml
assert_file_contains "proxy_network" "Variable reference: proxy routes declare their network" docs/variables.md
assert_file_contains "container_destination" "Variable reference: proxy routes declare their container destination" docs/variables.md
assert_file_not_contains "traefik_networks" "Variable reference: Traefik networks are derived from route config" docs/variables.md
assert_file_contains "proxy_network" "reverse_proxy: route validation requires explicit proxy network metadata" roles/reverse_proxy/tasks/main.yml
assert_file_contains "traefik_egress_network" "Traefik: uses a dedicated egress network for DNS-01/outbound traffic" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "attribute='proxy_network'" "Traefik: app network membership is derived from routes" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "--internal" "Shared network role: creates internal networks" roles/container_network/tasks/main.yml
assert_file_contains "container_network_internal: true" "Shared network role: networks are internal unless a caller opts out" roles/container_network/defaults/main.yml
assert_file_contains "homelab_network_needs_replacement" "Shared network role: replacement decision is made by the tested filter" roles/container_network/tasks/main.yml
assert_file_contains "Schedule deferred container network migration" "Migration coordinator: schedules deferred network replacement after the playbook finishes" roles/container_network_migration/tasks/main.yml
assert_file_contains "systemd-run" "Migration coordinator: uses a delayed background job for disruptive network replacement" roles/container_network_migration/tasks/main.yml
assert_file_contains "podman network rm --force --time 30" "Deferred migration: removes legacy networks after services are stopped" roles/container_network_migration/templates/migrate_container_networks.sh.j2
assert_file_contains "Reconcile route proxy networks" "reverse_proxy: creates route proxy networks before service roles run" roles/reverse_proxy/tasks/main.yml
assert_file_contains "Remove drifted container network" "Shared network role: recreates legacy non-internal networks" roles/container_network/tasks/main.yml
assert_file_contains "Queue container network" "Shared network role: queues disruptive replacements for the final migration job" roles/container_network/tasks/main.yml
assert_file_contains "reverse_proxy_deferred_route_networks" "reverse_proxy: defers destructive updates for control-plane route networks" roles/reverse_proxy/tasks/main.yml
assert_file_contains "--force" "Shared network role: force-removes attached legacy networks before recreating them" roles/container_network/tasks/main.yml
assert_file_not_contains "-p " "Vaultwarden: does not publish host ports" roles/vaultwarden/templates/vaultwarden.sh.j2
assert_file_not_contains "-p " "playbook-runner: does not publish host ports" roles/playbook_runner/templates/playbook_runner.sh.j2
assert_file_contains "--read-only" "Traefik: read-only root filesystem is configured" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "--read-only" "Vaultwarden: read-only root filesystem is configured" roles/vaultwarden/templates/vaultwarden.sh.j2
assert_file_contains "--read-only" "playbook-runner: read-only root filesystem is configured" roles/playbook_runner/templates/playbook_runner.sh.j2
assert_file_contains "--cap-drop=ALL" "Traefik: drops all capabilities before adding required bind capability" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "--cap-add=NET_BIND_SERVICE" "Traefik: only adds bind-service capability" roles/reverse_proxy/templates/traefik_container.sh.j2
assert_file_contains "--cap-drop=ALL" "Vaultwarden: drops all capabilities before adding required bind capability" roles/vaultwarden/templates/vaultwarden.sh.j2
assert_file_contains "--cap-drop=ALL" "playbook-runner: drops all capabilities" roles/playbook_runner/templates/playbook_runner.sh.j2
assert_file_not_contains "--cap-add" "playbook-runner: adds no capabilities back" roles/playbook_runner/templates/playbook_runner.sh.j2
assert_file_contains "destination=/run/playbook-runner,tmpfs-size=256M,tmpfs-mode=0700,U=true,noexec" "playbook-runner: run scratch space is a private noexec tmpfs" roles/playbook_runner/templates/playbook_runner.sh.j2
assert_file_contains "container_dns[.]aliases[.]playbook_runner_proxy" "playbook-runner: proxy DNS alias is dictionary-driven" roles/playbook_runner/templates/playbook_runner.sh.j2
assert_file_contains "playbook_runner_container_net" "reverse_proxy defaults: defers playbook-runner runtime network replacement" roles/reverse_proxy/defaults/main.yml
assert_file_not_contains "-p " "music-server: does not publish host ports" roles/music_server/templates/music_server.sh.j2
assert_file_contains "--read-only" "music-server: read-only root filesystem is configured" roles/music_server/templates/music_server.sh.j2
assert_file_contains "--user \\{\\{ music_server_uid \\}\\}:\\{\\{ music_server_gid \\}\\}" "music-server: runs as explicit non-root UID/GID" roles/music_server/templates/music_server.sh.j2
assert_file_contains "--cap-drop=ALL" "music-server: drops all capabilities" roles/music_server/templates/music_server.sh.j2
assert_file_not_contains "--cap-add" "music-server: adds no capabilities back" roles/music_server/templates/music_server.sh.j2
assert_file_contains "/music:ro,z" "music-server: mounts the music read-only" roles/music_server/templates/music_server.sh.j2
assert_file_contains "mode=0400" "music-server: secrets are readable only by the container user" roles/music_server/templates/music_server.sh.j2
assert_file_contains "container_dns[.]aliases[.]music_server_proxy" "music-server: proxy DNS alias is dictionary-driven" roles/music_server/templates/music_server.sh.j2
assert_file_not_contains "-p " "homedrive: does not publish host ports" roles/homedrive/templates/homedrive.sh.j2
assert_file_contains "--read-only" "homedrive: read-only root filesystem is configured" roles/homedrive/templates/homedrive.sh.j2
assert_file_contains "--user \\{\\{ homedrive_uid \\}\\}:\\{\\{ homedrive_gid \\}\\}" "homedrive: runs as explicit non-root UID/GID" roles/homedrive/templates/homedrive.sh.j2
assert_file_contains "--cap-drop=ALL" "homedrive: drops all capabilities" roles/homedrive/templates/homedrive.sh.j2
assert_file_not_contains "--cap-add" "homedrive: adds no capabilities back" roles/homedrive/templates/homedrive.sh.j2
assert_file_contains "mode=0400" "homedrive: the users secret is readable only by the container user" roles/homedrive/templates/homedrive.sh.j2
assert_file_contains "container_dns[.]aliases[.]homedrive_proxy" "homedrive: proxy DNS alias is dictionary-driven" roles/homedrive/templates/homedrive.sh.j2
echo ""
fi

# ---------------------------------------------------------------------------
if should_run traefik; then
echo "--- TEST-05: Traefik ---"
TEST_TRAEFIK_DIR=$(mktemp -d)
cat > "$TEST_TRAEFIK_DIR/traefik.yml" <<'EOF'
api:
  insecure: true
entryPoints:
  web:
    address: ":80"
EOF

# Test A: without NET_BIND_SERVICE (informational)
"${ENGINE_RUN[@]}" -d --name test_traefik_nocap \
  --cap-drop=ALL \
  --volume "$TEST_TRAEFIK_DIR/traefik.yml":/etc/traefik/traefik.yml:ro \
  -p 18080:80 \
  "$TRAEFIK_IMAGE"
sleep 5
$PODMAN inspect --format='{{.State.Status}}' test_traefik_nocap 2>/dev/null \
  | grep -q running \
  && echo "INFO: Traefik runs without NET_BIND_SERVICE (WSL does not enforce this cap)" \
  || echo "INFO: Traefik exits without NET_BIND_SERVICE — NET_BIND_SERVICE required on real kernel (expected)"
cleanup test_traefik_nocap

# Test B: with NET_BIND_SERVICE (must pass)
"${ENGINE_RUN[@]}" -d --name test_traefik_cap \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
  --memory=256m --memory-swap=256m \
  --pids-limit=200 \
  --volume "$TEST_TRAEFIK_DIR/traefik.yml":/etc/traefik/traefik.yml:ro \
  -p 18080:80 \
  "$TRAEFIK_IMAGE"
check_running test_traefik_cap "Traefik: starts with cap-drop=ALL + NET_BIND_SERVICE"

cleanup test_traefik_cap
rm -rf "$TEST_TRAEFIK_DIR"
echo ""
fi

# ---------------------------------------------------------------------------
if should_run vaultwarden; then
echo "--- TEST-07: Vaultwarden ---"
TEST_VW_DIR=$(mktemp -d)
chmod 0777 "$TEST_VW_DIR"

"${ENGINE_RUN[@]}" -d --name test_vaultwarden \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
  --memory=256m --memory-swap=256m \
  --pids-limit=200 \
  --volume "$TEST_VW_DIR":/data \
  -e SIGNUPS_ALLOWED=false \
  "$VAULTWARDEN_IMAGE"

check_running test_vaultwarden "Vaultwarden: starts with cap-drop=ALL + NET_BIND_SERVICE + no-new-privileges"

cleanup test_vaultwarden
rm -rf "$TEST_VW_DIR"
echo ""
fi

# ---------------------------------------------------------------------------
if should_run music_server; then
echo "--- TEST-09: music-server ---"
TEST_MS_DIR=$(mktemp -d)
mkdir -p "$TEST_MS_DIR/music" "$TEST_MS_DIR/data" "$TEST_MS_DIR/cache" "$TEST_MS_DIR/secrets"
printf '%064d\n' 7 | tr 0 7 > "$TEST_MS_DIR/secrets/key"
printf '%s\n' '{"version":1,"users":[{"name":"admin","password":"runtime-test-pw","admin":true}]}' \
  > "$TEST_MS_DIR/secrets/users"
chmod -R a+rX "$TEST_MS_DIR/music" "$TEST_MS_DIR/secrets"
chown_test_path 10001:10001 "$TEST_MS_DIR/data"
chown_test_path 10001:10001 "$TEST_MS_DIR/cache"

# The flags roles/music_server renders, with the secrets as read-only mounts
# in place of Podman secrets.
"${ENGINE_RUN[@]}" -d --name test_music_server \
  --user "10001:10001" \
  --group-add 33 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --memory=512m --memory-swap=512m \
  --pids-limit=200 \
  --volume "$TEST_MS_DIR/music":/music:ro \
  --volume "$TEST_MS_DIR/data":/var/lib/music-server \
  --volume "$TEST_MS_DIR/cache":/var/cache/music-server \
  --volume "$TEST_MS_DIR/secrets/key":/run/secrets/music_server_master_key:ro \
  --volume "$TEST_MS_DIR/secrets/users":/run/secrets/music_server_users:ro \
  "$MUSIC_SERVER_IMAGE"

check_running test_music_server "music-server: starts as 10001 with cap-drop=ALL, read-only, and no-new-privileges"
if $PODMAN exec test_music_server music-server healthcheck; then
  pass "music-server: answers its health check"
else
  fail "music-server: health check failed"
fi

cleanup test_music_server
cleanup_dir "$TEST_MS_DIR"
echo ""
fi

# ---------------------------------------------------------------------------
if should_run homedrive; then
echo "--- TEST-10: homedrive ---"
TEST_HD_DIR=$(mktemp -d)
mkdir -p "$TEST_HD_DIR/store" "$TEST_HD_DIR/secrets"
printf '%s\n' '{"version":1,"users":[{"name":"admin","password":"runtime-test-pw","admin":true,"quota_gb":1}]}' \
  > "$TEST_HD_DIR/secrets/users"
chmod -R a+rX "$TEST_HD_DIR/secrets"
chown_test_path 10001:10001 "$TEST_HD_DIR/store"

# The flags roles/homedrive renders, with the users secret as a read-only
# mount in place of a Podman secret.
HD_RUN=(
  --user "10001:10001"
  --cap-drop=ALL
  --security-opt=no-new-privileges:true
  --read-only
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m
  --memory=1g --memory-swap=1g
  --pids-limit=200
  --volume "$TEST_HD_DIR/store":/var/lib/homedrive
  --volume "$TEST_HD_DIR/secrets/users":/run/secrets/homedrive_users:ro
)

# Without a store.id the server must refuse to start, so an unmounted disk
# never becomes a new, empty store.
"${ENGINE_RUN[@]}" -d --name test_homedrive_no_store "${HD_RUN[@]}" "$HOMEDRIVE_IMAGE"
sleep 3
if [[ "$($PODMAN inspect --format='{{.State.Status}}' test_homedrive_no_store 2>/dev/null)" == running ]]; then
  fail "homedrive: started on a directory without store.id"
else
  pass "homedrive: refuses to start without store.id"
fi
cleanup test_homedrive_no_store

# The role's one-time init, with the same flags as the role's init task.
"${ENGINE_RUN[@]}" --rm --name test_homedrive_init --network=none \
  --user "10001:10001" --read-only --cap-drop=ALL --security-opt=no-new-privileges:true \
  --volume "$TEST_HD_DIR/store":/var/lib/homedrive \
  "$HOMEDRIVE_IMAGE" init >/dev/null || fail "homedrive: init failed on an empty store"
pass "homedrive: init creates a store as 10001 with cap-drop=ALL"

"${ENGINE_RUN[@]}" -d --name test_homedrive "${HD_RUN[@]}" "$HOMEDRIVE_IMAGE"
check_running test_homedrive "homedrive: starts as 10001 with cap-drop=ALL, read-only, and no-new-privileges"
if $PODMAN exec test_homedrive hd-server healthcheck; then
  pass "homedrive: answers its health check"
else
  fail "homedrive: health check failed"
fi

cleanup test_homedrive
cleanup_dir "$TEST_HD_DIR"
echo ""
fi

# ---------------------------------------------------------------------------
echo "=== Tests complete. Review PASS/FAIL/WARN/INFO lines above. ==="

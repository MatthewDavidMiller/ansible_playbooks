#!/bin/bash
# Container security flag test script
# Tests container capability, privilege, and memory flags
# for all services before deploying to production via Ansible.
#
# Usage: bash scripts/test_container_security.sh 2>&1 | tee /tmp/container_test_results.txt
# See docs/testing.md for full descriptions of each test.

set -euo pipefail

DOCKER=${DOCKER:-docker}

cleanup()     { $DOCKER rm -f "$1" 2>/dev/null || true; }
cleanup_dir() {
  # Restore ownership to current user via docker so rm -rf works without sudo
  $DOCKER run --rm -v "$(dirname "$1")":/mnt \
    alpine chown -R "$(id -u):$(id -g)" "/mnt/$(basename "$1")"
  rm -rf "$1"
}
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }
check_running() {
  local name="$1" label="$2"
  sleep 5
  $DOCKER inspect --format='{{.State.Status}}' "$name" 2>/dev/null \
    | grep -q running && pass "$label" || fail "$label"
}

echo "=== Container Security Flag Tests ==="
echo "Docker: $($DOCKER --version)"
echo "User: $(id)"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-01: PostgreSQL ---"
TEST_PG_DIR=$(mktemp -d)
chmod 0750 "$TEST_PG_DIR"
$DOCKER run --rm -v "$TEST_PG_DIR":/target alpine chown 999:999 /target

$DOCKER run -d --name test_postgres \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=4g --memory-swap=4g \
  --shm-size=256m \
  --env POSTGRES_USER=testuser \
  --env POSTGRES_PASSWORD=testpass \
  --env POSTGRES_DB=testdb \
  --env PGDATA=/var/lib/postgresql/data/pgdata \
  --volume "$TEST_PG_DIR":/var/lib/postgresql/data \
  docker.io/postgres:17

sleep 15
$DOCKER inspect --format='{{.State.Status}}' test_postgres 2>/dev/null \
  | grep -q running && pass "Postgres: starts with cap-drop=ALL + shm-size=256m + 0750/999:999 dir" \
  || fail "Postgres: starts with cap-drop=ALL + shm-size=256m + 0750/999:999 dir"
$DOCKER exec test_postgres pg_isready -U testuser \
  && pass "Postgres: pg_isready succeeds" || fail "Postgres: pg_isready failed"

cleanup test_postgres
cleanup_dir "$TEST_PG_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-02: Redis ---"
$DOCKER run -d --name test_redis \
  --cap-drop=ALL \
  --cap-add=CHOWN \
  --cap-add=FOWNER \
  --cap-add=DAC_OVERRIDE \
  --security-opt=no-new-privileges:true \
  --memory=512m --memory-swap=512m \
  docker.io/redis:latest

check_running test_redis "Redis: starts with cap-drop=ALL + CHOWN/FOWNER/DAC_OVERRIDE + 512m limit"
sleep 3
$DOCKER exec test_redis redis-cli ping \
  | grep -q PONG && pass "Redis: ping succeeds" || fail "Redis: ping failed"

cleanup test_redis
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-03: Nextcloud ---"
# NOTE: Nextcloud's entrypoint uses rsync --chown to copy its webroot on every start,
# requiring the CHOWN capability. --cap-drop=ALL breaks this. Production config uses
# --security-opt=no-new-privileges:true only (no --cap-drop=ALL).
TEST_NC_DIR=$(mktemp -d)
chmod 0770 "$TEST_NC_DIR"
$DOCKER run --rm -v "$TEST_NC_DIR":/target alpine chown 33:33 /target

$DOCKER run -d --name test_nextcloud \
  --security-opt=no-new-privileges:true \
  --memory=4g --memory-swap=4g \
  --volume "$TEST_NC_DIR":/var/www/html \
  -e SQLITE_DATABASE=testdb \
  docker.io/nextcloud:latest

sleep 20
$DOCKER inspect --format='{{.State.Status}}' test_nextcloud \
  | grep -q running \
  && pass "Nextcloud: starts with no-new-privileges (cap-drop=ALL omitted — requires CHOWN for rsync entrypoint)" \
  || fail "Nextcloud: failed to start"

cleanup test_nextcloud
cleanup_dir "$TEST_NC_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-04: Traefik ---"
TEST_TRAEFIK_DIR=$(mktemp -d)
cat > "$TEST_TRAEFIK_DIR/traefik.yml" <<'EOF'
api:
  insecure: true
entryPoints:
  web:
    address: ":80"
EOF

# Test A: without NET_BIND_SERVICE (informational)
$DOCKER run -d --name test_traefik_nocap \
  --cap-drop=ALL \
  --volume "$TEST_TRAEFIK_DIR/traefik.yml":/etc/traefik/traefik.yml:ro \
  -p 18080:80 \
  docker.io/traefik:v3
sleep 5
$DOCKER inspect --format='{{.State.Status}}' test_traefik_nocap 2>/dev/null \
  | grep -q running \
  && echo "INFO: Traefik runs without NET_BIND_SERVICE (WSL does not enforce this cap)" \
  || echo "INFO: Traefik exits without NET_BIND_SERVICE — NET_BIND_SERVICE required on real kernel (expected)"
cleanup test_traefik_nocap

# Test B: with NET_BIND_SERVICE (must pass)
$DOCKER run -d --name test_traefik_cap \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --memory=256m --memory-swap=256m \
  --volume "$TEST_TRAEFIK_DIR/traefik.yml":/etc/traefik/traefik.yml:ro \
  -p 18080:80 \
  docker.io/traefik:v3
check_running test_traefik_cap "Traefik: starts with cap-drop=ALL + NET_BIND_SERVICE"

cleanup test_traefik_cap
rm -rf "$TEST_TRAEFIK_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-05: Paperless NGX ---"
TEST_PL_DATA=$(mktemp -d)
TEST_PL_MEDIA=$(mktemp -d)
TEST_PL_EXPORT=$(mktemp -d)
TEST_PL_CONSUME=$(mktemp -d)
$DOCKER run --rm \
  -v "$TEST_PL_DATA":/d1 -v "$TEST_PL_MEDIA":/d2 \
  -v "$TEST_PL_EXPORT":/d3 -v "$TEST_PL_CONSUME":/d4 \
  alpine chown 1000:1000 /d1 /d2 /d3 /d4

$DOCKER run -d --name test_paperless \
  --cap-drop=ALL \
  --cap-add=CHOWN \
  --cap-add=SETUID \
  --cap-add=SETGID \
  --cap-add=FOWNER \
  --cap-add=DAC_OVERRIDE \
  --memory=2g --memory-swap=2g \
  -e USERMAP_UID=1000 \
  -e USERMAP_GID=1000 \
  -e PAPERLESS_REDIS=redis://nonexistent:6379 \
  -e PAPERLESS_DBHOST=nonexistent \
  --volume "$TEST_PL_DATA":/usr/src/paperless/data \
  --volume "$TEST_PL_MEDIA":/usr/src/paperless/media \
  --volume "$TEST_PL_EXPORT":/usr/src/paperless/export \
  --volume "$TEST_PL_CONSUME":/usr/src/paperless/consume \
  ghcr.io/paperless-ngx/paperless-ngx:latest
sleep 10
echo "Paperless status: $($DOCKER inspect --format='{{.State.Status}}' test_paperless 2>/dev/null)"
$DOCKER logs test_paperless 2>&1 | grep -qi "gosu\|permission denied\|operation not permitted" \
  && fail "Paperless: startup shows privilege errors with required caps" \
  || pass "Paperless: starts without privilege errors using CHOWN/SETUID/SETGID/FOWNER/DAC_OVERRIDE"
cleanup test_paperless

cleanup_dir "$TEST_PL_DATA"
cleanup_dir "$TEST_PL_MEDIA"
cleanup_dir "$TEST_PL_EXPORT"
cleanup_dir "$TEST_PL_CONSUME"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-06: Vaultwarden ---"
TEST_VW_DIR=$(mktemp -d)
chmod 0777 "$TEST_VW_DIR"

$DOCKER run -d --name test_vaultwarden \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --memory=256m --memory-swap=256m \
  --volume "$TEST_VW_DIR":/data \
  docker.io/vaultwarden/server:latest

check_running test_vaultwarden "Vaultwarden: starts with cap-drop=ALL + NET_BIND_SERVICE + no-new-privileges"

cleanup test_vaultwarden
rm -rf "$TEST_VW_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-07: Semaphore ---"
# Test A: baseline
$DOCKER run -d --name test_semaphore_base \
  -e SEMAPHORE_DB_DIALECT=bolt \
  -e SEMAPHORE_ADMIN=admin \
  -e SEMAPHORE_ADMIN_PASSWORD=Admin1234! \
  -e SEMAPHORE_ADMIN_NAME=Admin \
  -e SEMAPHORE_ADMIN_EMAIL=admin@test.local \
  -e SEMAPHORE_ACCESS_KEY_ENCRYPTION=aabbccddaabbccddaabbccddaabbccdd \
  docker.io/semaphoreui/semaphore:latest
sleep 8
$DOCKER inspect --format='{{.State.Status}}' test_semaphore_base \
  | grep -q running && pass "Semaphore: baseline starts" || fail "Semaphore: baseline failed"
cleanup test_semaphore_base

# Test B: with cap-drop=ALL
$DOCKER run -d --name test_semaphore_caps \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=512m --memory-swap=512m \
  -e SEMAPHORE_DB_DIALECT=bolt \
  -e SEMAPHORE_ADMIN=admin \
  -e SEMAPHORE_ADMIN_PASSWORD=Admin1234! \
  -e SEMAPHORE_ADMIN_NAME=Admin \
  -e SEMAPHORE_ADMIN_EMAIL=admin@test.local \
  -e SEMAPHORE_ACCESS_KEY_ENCRYPTION=aabbccddaabbccddaabbccddaabbccdd \
  docker.io/semaphoreui/semaphore:latest
sleep 8
$DOCKER inspect --format='{{.State.Status}}' test_semaphore_caps 2>/dev/null \
  | grep -q running \
  && pass "Semaphore: starts with cap-drop=ALL" \
  || echo "WARN: Semaphore exits with cap-drop=ALL — check logs for required capabilities"
echo "--- Semaphore cap-drop logs (last 20 lines) ---"
$DOCKER logs test_semaphore_caps 2>&1 | tail -20
cleanup test_semaphore_caps
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-08: Navidrome ---"
TEST_ND_DATA=$(mktemp -d)
TEST_ND_MUSIC=$(mktemp -d)
chmod 0770 "$TEST_ND_DATA"
$DOCKER run --rm -v "$TEST_ND_DATA":/target alpine chown "$(id -u):33" /target

$DOCKER run -d --name test_navidrome \
  --user "$(id -u):33" \
  --cap-drop=ALL \
  --cap-add=DAC_READ_SEARCH \
  --security-opt=no-new-privileges:true \
  --memory=512m --memory-swap=512m \
  --volume "$TEST_ND_MUSIC":/music:ro \
  --volume "$TEST_ND_DATA":/data \
  -e ND_LOGLEVEL=info \
  docker.io/deluan/navidrome:latest

check_running test_navidrome "Navidrome: starts with --user $(id -u):33 + cap-drop=ALL + DAC_READ_SEARCH"

cleanup test_navidrome
cleanup_dir "$TEST_ND_DATA"
rm -rf "$TEST_ND_MUSIC"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-09: Pi-hole ---"
TEST_PIHOLE_DIR=$(mktemp -d)
chmod 0770 "$TEST_PIHOLE_DIR"
$DOCKER run --rm -v "$TEST_PIHOLE_DIR":/target alpine chown 999:33 /target

$DOCKER run -d --name test_pihole \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --volume "$TEST_PIHOLE_DIR":/etc/pihole \
  --memory=256m --memory-swap=256m \
  -e TZ=America/New_York \
  -e FTLCONF_webserver_api_password=testpass \
  -e FTLCONF_dns_bogusPriv=false \
  -e FTLCONF_dns_domainNeeded=false \
  -e FTLCONF_dns_dnssec=true \
  -e FTLCONF_dns_listeningMode=all \
  -e FTLCONF_dns_upstreams=1.1.1.1 \
  -p 5353:53/tcp \
  -p 5353:53/udp \
  docker.io/pihole/pihole:latest

check_running test_pihole "Pi-hole: starts with cap-drop=ALL + NET_BIND_SERVICE"

cleanup test_pihole
cleanup_dir "$TEST_PIHOLE_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-10: WireGuard ---"
# WireGuard uses --privileged=true (required for kernel module access and sysctl).
# In environments without the wireguard kernel module (e.g. WSL without the module)
# the container will exit after failing modprobe — this is reported as INFO, not FAIL.
TEST_WG_DIR=$(mktemp -d)
chmod 0755 "$TEST_WG_DIR"

$DOCKER run -d --name test_wireguard \
  --privileged=true \
  --volume "$TEST_WG_DIR":/config/:Z \
  --sysctl="net.ipv4.conf.all.src_valid_mark=1" \
  --sysctl="net.ipv4.conf.all.forwarding=1" \
  --sysctl="net.ipv4.ip_forward=1" \
  --memory=128m --memory-swap=128m \
  -e TZ=America/New_York \
  -e SERVERURL=vpn.example.com \
  -e SERVERPORT=51820 \
  -e PEERS=testpeer \
  -e INTERNAL_SUBNET=10.13.13.0/24 \
  docker.io/linuxserver/wireguard:latest
sleep 10

WG_STATUS=$($DOCKER inspect --format='{{.State.Status}}' test_wireguard 2>/dev/null || echo "missing")
if [ "$WG_STATUS" = "running" ]; then
  pass "WireGuard: starts with --privileged=true"
else
  WG_LOGS=$($DOCKER logs test_wireguard 2>&1)
  if echo "$WG_LOGS" | grep -qi "wireguard\|modprobe\|module\|ip_tables\|nft"; then
    echo "INFO: WireGuard exited — kernel module not available in this environment (expected on WSL without wireguard module)"
  else
    echo "WARN: WireGuard exited unexpectedly; last 10 log lines:"
    echo "$WG_LOGS" | tail -10
  fi
fi

cleanup test_wireguard
cleanup_dir "$TEST_WG_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "=== Tests complete. Review PASS/FAIL/WARN/INFO lines above. ==="

#!/bin/bash
# Container security flag test script
# Tests container capability, privilege, and memory flags
# for the maintained VM1 services before deploying to production via Ansible.
#
# Usage: bash scripts/test_container_security.sh 2>&1 | tee /tmp/container_test_results.txt
# See docs/testing.md for full descriptions of each test.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOCK_FILE=${LOCK_FILE:-"$REPO_ROOT/artifacts/containers.lock.yml"}
DOCKER=${DOCKER:-docker}
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

POSTGRES_IMAGE=${POSTGRES_IMAGE:-$(lock_image_ref postgres)}
REDIS_IMAGE=${REDIS_IMAGE:-$(lock_image_ref redis)}
NEXTCLOUD_IMAGE=${NEXTCLOUD_IMAGE:-$(lock_image_ref nextcloud)}
TRAEFIK_IMAGE=${TRAEFIK_IMAGE:-$(lock_image_ref traefik)}
PAPERLESS_IMAGE=${PAPERLESS_IMAGE:-$(lock_image_ref paperless)}
VAULTWARDEN_IMAGE=${VAULTWARDEN_IMAGE:-$(lock_image_ref vaultwarden)}
SEMAPHORE_IMAGE=${SEMAPHORE_IMAGE:-$(lock_image_ref semaphore)}
NAVIDROME_IMAGE=${NAVIDROME_IMAGE:-$(lock_image_ref navidrome)}

cleanup()     { $DOCKER rm -f "$1" >/dev/null 2>&1 || true; }
cleanup_dir() {
  # Restore ownership to current user via docker so rm -rf works without sudo
  $DOCKER run --rm -v "$(dirname "$1")":/mnt \
    alpine chown -R "$(id -u):$(id -g)" "/mnt/$(basename "$1")"
  rm -rf "$1"
}
cleanup_all_test_containers() {
  local name
  for name in \
    test_navidrome \
    test_nextcloud \
    test_paperless \
    test_postgres \
    test_postgres_custom_migration \
    test_postgres_custom_seed \
    test_postgres_legacy_migration \
    test_postgres_legacy_seed \
    test_postgres_migration \
    test_postgres_migration_seed \
    test_postgres_mixed_migration \
    test_postgres_mixed_seed \
    test_postgres_roles \
    test_redis \
    test_semaphore_base \
    test_semaphore_caps \
    test_traefik_cap \
    test_traefik_nocap \
    test_vaultwarden
  do
    cleanup "$name"
  done
}
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }
check_running() {
  local name="$1" label="$2"
  sleep 5
  $DOCKER inspect --format='{{.State.Status}}' "$name" 2>/dev/null \
    | grep -q running && pass "$label" || fail "$label"
}

trap cleanup_all_test_containers EXIT
cleanup_all_test_containers

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
  "$POSTGRES_IMAGE"

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
echo "--- TEST-02: PostgreSQL Role Isolation ---"
$DOCKER run -d --name test_postgres_roles \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=postgres_admin \
  --env POSTGRES_PASSWORD=adminpass \
  --env POSTGRES_DB=postgres \
  "$POSTGRES_IMAGE"
sleep 15
$DOCKER exec test_postgres_roles psql -U postgres_admin -d postgres -c "CREATE ROLE nextcloud_user LOGIN PASSWORD 'ncpass';"
$DOCKER exec test_postgres_roles psql -U postgres_admin -d postgres -c "CREATE ROLE paperless_user LOGIN PASSWORD 'plpass';"
$DOCKER exec test_postgres_roles psql -U postgres_admin -d postgres -c "CREATE DATABASE nextcloud OWNER nextcloud_user;"
$DOCKER exec test_postgres_roles psql -U postgres_admin -d postgres -c "CREATE DATABASE paperless OWNER paperless_user;"
$DOCKER exec test_postgres_roles env PGPASSWORD=ncpass psql -h localhost -U nextcloud_user -d nextcloud -c "SELECT current_user;" \
  | grep -q nextcloud_user && pass "Postgres: nextcloud role can access its own database" \
  || fail "Postgres: nextcloud role access failed"
$DOCKER exec test_postgres_roles env PGPASSWORD=ncpass \
  psql -h localhost -U nextcloud_user -d paperless -c "CREATE TABLE cross_db_smoke(id int);" \
  >/tmp/test_postgres_roles.out 2>/tmp/test_postgres_roles.err \
  && fail "Postgres: nextcloud role unexpectedly managed paperless database" \
  || pass "Postgres: per-service ownership blocks cross-database writes by default"
cleanup test_postgres_roles
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-02B: PostgreSQL Existing Cluster Migration ---"
TEST_PG_MIG_DIR=$(mktemp -d)
TEST_PG_MIG_DATA="$TEST_PG_MIG_DIR/pgdata"
TEST_PG_MIG_INIT="$TEST_PG_MIG_DIR/custom-init"
mkdir -p "$TEST_PG_MIG_DATA" "$TEST_PG_MIG_INIT"
chmod 0750 "$TEST_PG_MIG_DATA" "$TEST_PG_MIG_INIT"
install -m 0755 "$REPO_ROOT/roles/nextcloud/files/db_wrapper.sh" \
  "$TEST_PG_MIG_INIT/db_wrapper.sh"
$DOCKER run --rm -v "$TEST_PG_MIG_DATA":/target alpine chown 999:999 /target
$DOCKER run --rm -v "$TEST_PG_MIG_INIT":/target alpine chown -R 999:999 /target

$DOCKER run -d --name test_postgres_migration_seed \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=nextcloud_user \
  --env POSTGRES_PASSWORD=oldsharedpass \
  --env POSTGRES_DB=nextcloud \
  --volume "$TEST_PG_MIG_DATA":/var/lib/postgresql/data \
  "$POSTGRES_IMAGE"

sleep 15
$DOCKER exec test_postgres_migration_seed env PGPASSWORD=oldsharedpass \
  psql -h localhost -U nextcloud_user -d postgres \
  -c "CREATE DATABASE paperless OWNER nextcloud_user;"
$DOCKER exec test_postgres_migration_seed env PGPASSWORD=oldsharedpass \
  psql -h localhost -U nextcloud_user -d postgres \
  -c "CREATE DATABASE semaphore OWNER nextcloud_user;"
$DOCKER exec test_postgres_migration_seed env PGPASSWORD=oldsharedpass \
  psql -h localhost -U nextcloud_user -d semaphore \
  -c "CREATE TABLE access_key (id serial primary key);"

cleanup test_postgres_migration_seed

$DOCKER run -d --name test_postgres_migration \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=postgres_admin \
  --env POSTGRES_PASSWORD=adminpass \
  --env POSTGRES_DB=nextcloud \
  --env NEXTCLOUD_DB_NAME=nextcloud \
  --env NEXTCLOUD_DB_USER=nextcloud_user \
  --env NEXTCLOUD_DB_PASSWORD=oldsharedpass \
  --env PAPERLESS_DB_NAME=paperless \
  --env PAPERLESS_DB_USER=paperless_user \
  --env PAPERLESS_DB_PASSWORD=plpass \
  --env SEMAPHORE_DB_NAME=semaphore \
  --env SEMAPHORE_DB_USER=semaphore_user \
  --env SEMAPHORE_DB_PASSWORD=sempass \
  --volume "$TEST_PG_MIG_DATA":/var/lib/postgresql/data \
  --volume "$TEST_PG_MIG_INIT":/custom-init \
  --entrypoint /custom-init/db_wrapper.sh \
  "$POSTGRES_IMAGE"

sleep 20
$DOCKER inspect --format='{{.State.Status}}' test_postgres_migration 2>/dev/null \
  | grep -q running && pass "Postgres migration: wrapper starts on existing shared-user data directory" \
  || fail "Postgres migration: wrapper failed on existing shared-user data directory"
$DOCKER exec test_postgres_migration env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres -c "SELECT current_user;" \
  | grep -q postgres_admin && pass "Postgres migration: postgres_admin is available after fallback bootstrap" \
  || fail "Postgres migration: postgres_admin was not created"
$DOCKER exec test_postgres_migration env PGPASSWORD=plpass \
  psql -h localhost -U paperless_user -d paperless -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres migration: paperless role owns migrated database" \
  || fail "Postgres migration: paperless role cannot manage migrated database"
$DOCKER exec test_postgres_migration env PGPASSWORD=sempass \
  psql -h localhost -U semaphore_user -d semaphore \
  -c "INSERT INTO access_key DEFAULT VALUES; CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres migration: semaphore role owns migrated database and serial-backed sequences" \
  || fail "Postgres migration: semaphore role cannot manage migrated database objects after sequence ownership migration"

cleanup test_postgres_migration
cleanup_dir "$TEST_PG_MIG_DATA"
cleanup_dir "$TEST_PG_MIG_INIT"
rm -rf "$TEST_PG_MIG_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-02C: PostgreSQL Legacy postgres Superuser Migration ---"
TEST_PG_LEGACY_DIR=$(mktemp -d)
TEST_PG_LEGACY_DATA="$TEST_PG_LEGACY_DIR/pgdata"
TEST_PG_LEGACY_INIT="$TEST_PG_LEGACY_DIR/custom-init"
mkdir -p "$TEST_PG_LEGACY_DATA" "$TEST_PG_LEGACY_INIT"
chmod 0750 "$TEST_PG_LEGACY_DATA" "$TEST_PG_LEGACY_INIT"
install -m 0755 "$REPO_ROOT/roles/nextcloud/files/db_wrapper.sh" \
  "$TEST_PG_LEGACY_INIT/db_wrapper.sh"
$DOCKER run --rm -v "$TEST_PG_LEGACY_DATA":/target alpine chown 999:999 /target
$DOCKER run --rm -v "$TEST_PG_LEGACY_INIT":/target alpine chown -R 999:999 /target

$DOCKER run -d --name test_postgres_legacy_seed \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_PASSWORD=legacysecret \
  --env POSTGRES_DB=nextcloud \
  --volume "$TEST_PG_LEGACY_DATA":/var/lib/postgresql/data \
  "$POSTGRES_IMAGE"

sleep 15
$DOCKER exec test_postgres_legacy_seed env PGPASSWORD=legacysecret \
  psql -h localhost -U postgres -d postgres \
  -c "CREATE DATABASE paperless OWNER postgres;"
$DOCKER exec test_postgres_legacy_seed env PGPASSWORD=legacysecret \
  psql -h localhost -U postgres -d postgres \
  -c "CREATE DATABASE semaphore OWNER postgres;"

cleanup test_postgres_legacy_seed

$DOCKER run -d --name test_postgres_legacy_migration \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=postgres_admin \
  --env POSTGRES_PASSWORD=adminpass \
  --env POSTGRES_DB=nextcloud \
  --env NEXTCLOUD_DB_NAME=nextcloud \
  --env NEXTCLOUD_DB_USER=nextcloud_user \
  --env NEXTCLOUD_DB_PASSWORD=ncpass \
  --env PAPERLESS_DB_NAME=paperless \
  --env PAPERLESS_DB_USER=paperless_user \
  --env PAPERLESS_DB_PASSWORD=plpass \
  --env SEMAPHORE_DB_NAME=semaphore \
  --env SEMAPHORE_DB_USER=semaphore_user \
  --env SEMAPHORE_DB_PASSWORD=sempass \
  --volume "$TEST_PG_LEGACY_DATA":/var/lib/postgresql/data \
  --volume "$TEST_PG_LEGACY_INIT":/custom-init \
  --entrypoint /custom-init/db_wrapper.sh \
  "$POSTGRES_IMAGE"

sleep 20
$DOCKER inspect --format='{{.State.Status}}' test_postgres_legacy_migration 2>/dev/null \
  | grep -q running && pass "Postgres legacy migration: wrapper starts on existing postgres-owned data directory" \
  || fail "Postgres legacy migration: wrapper failed on existing postgres-owned data directory"
$DOCKER exec test_postgres_legacy_migration env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres -c "SELECT current_user;" \
  | grep -q postgres_admin && pass "Postgres legacy migration: postgres_admin is available after fallback bootstrap" \
  || fail "Postgres legacy migration: postgres_admin was not created"
$DOCKER exec test_postgres_legacy_migration env PGPASSWORD=ncpass \
  psql -h localhost -U nextcloud_user -d nextcloud -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres legacy migration: nextcloud role owns migrated database" \
  || fail "Postgres legacy migration: nextcloud role cannot manage migrated database"
$DOCKER exec test_postgres_legacy_migration env PGPASSWORD=plpass \
  psql -h localhost -U paperless_user -d paperless -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres legacy migration: paperless role owns migrated database" \
  || fail "Postgres legacy migration: paperless role cannot manage migrated database"
$DOCKER exec test_postgres_legacy_migration env PGPASSWORD=sempass \
  psql -h localhost -U semaphore_user -d semaphore -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres legacy migration: semaphore role owns migrated database" \
  || fail "Postgres legacy migration: semaphore role cannot manage migrated database"

cleanup test_postgres_legacy_migration
cleanup_dir "$TEST_PG_LEGACY_DATA"
cleanup_dir "$TEST_PG_LEGACY_INIT"
rm -rf "$TEST_PG_LEGACY_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-02D: PostgreSQL Arbitrary Legacy Superuser Migration ---"
TEST_PG_CUSTOM_DIR=$(mktemp -d)
TEST_PG_CUSTOM_DATA="$TEST_PG_CUSTOM_DIR/pgdata"
TEST_PG_CUSTOM_INIT="$TEST_PG_CUSTOM_DIR/custom-init"
mkdir -p "$TEST_PG_CUSTOM_DATA" "$TEST_PG_CUSTOM_INIT"
chmod 0750 "$TEST_PG_CUSTOM_DATA" "$TEST_PG_CUSTOM_INIT"
install -m 0755 "$REPO_ROOT/roles/nextcloud/files/db_wrapper.sh" \
  "$TEST_PG_CUSTOM_INIT/db_wrapper.sh"
$DOCKER run --rm -v "$TEST_PG_CUSTOM_DATA":/target alpine chown 999:999 /target
$DOCKER run --rm -v "$TEST_PG_CUSTOM_INIT":/target alpine chown -R 999:999 /target

$DOCKER run -d --name test_postgres_custom_seed \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=legacy_admin \
  --env POSTGRES_PASSWORD=legacysecret \
  --env POSTGRES_DB=nextcloud \
  --volume "$TEST_PG_CUSTOM_DATA":/var/lib/postgresql/data \
  "$POSTGRES_IMAGE"

sleep 15
$DOCKER exec test_postgres_custom_seed env PGPASSWORD=legacysecret \
  psql -h localhost -U legacy_admin -d postgres \
  -c "CREATE DATABASE paperless OWNER legacy_admin;"
$DOCKER exec test_postgres_custom_seed env PGPASSWORD=legacysecret \
  psql -h localhost -U legacy_admin -d postgres \
  -c "CREATE DATABASE semaphore OWNER legacy_admin;"

cleanup test_postgres_custom_seed

$DOCKER run -d --name test_postgres_custom_migration \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=postgres_admin \
  --env POSTGRES_PASSWORD=adminpass \
  --env POSTGRES_LEGACY_BOOTSTRAP_USER=legacy_admin \
  --env POSTGRES_LEGACY_BOOTSTRAP_PASSWORD=legacysecret \
  --env POSTGRES_DB=nextcloud \
  --env NEXTCLOUD_DB_NAME=nextcloud \
  --env NEXTCLOUD_DB_USER=nextcloud_user \
  --env NEXTCLOUD_DB_PASSWORD=ncpass \
  --env PAPERLESS_DB_NAME=paperless \
  --env PAPERLESS_DB_USER=paperless_user \
  --env PAPERLESS_DB_PASSWORD=plpass \
  --env SEMAPHORE_DB_NAME=semaphore \
  --env SEMAPHORE_DB_USER=semaphore_user \
  --env SEMAPHORE_DB_PASSWORD=sempass \
  --volume "$TEST_PG_CUSTOM_DATA":/var/lib/postgresql/data \
  --volume "$TEST_PG_CUSTOM_INIT":/custom-init \
  --entrypoint /custom-init/db_wrapper.sh \
  "$POSTGRES_IMAGE"

sleep 20
$DOCKER inspect --format='{{.State.Status}}' test_postgres_custom_migration 2>/dev/null \
  | grep -q running && pass "Postgres custom migration: wrapper starts with explicit legacy bootstrap credentials" \
  || fail "Postgres custom migration: wrapper failed with explicit legacy bootstrap credentials"
$DOCKER exec test_postgres_custom_migration env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres -c "SELECT current_user;" \
  | grep -q postgres_admin && pass "Postgres custom migration: postgres_admin is available after legacy bootstrap override" \
  || fail "Postgres custom migration: postgres_admin was not created"
$DOCKER exec test_postgres_custom_migration env PGPASSWORD=ncpass \
  psql -h localhost -U nextcloud_user -d nextcloud -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres custom migration: nextcloud role owns migrated database" \
  || fail "Postgres custom migration: nextcloud role cannot manage migrated database"
$DOCKER exec test_postgres_custom_migration env PGPASSWORD=plpass \
  psql -h localhost -U paperless_user -d paperless -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres custom migration: paperless role owns migrated database" \
  || fail "Postgres custom migration: paperless role cannot manage migrated database"
$DOCKER exec test_postgres_custom_migration env PGPASSWORD=sempass \
  psql -h localhost -U semaphore_user -d semaphore -c "CREATE TABLE migration_smoke(id int);" \
  >/dev/null 2>&1 && pass "Postgres custom migration: semaphore role owns migrated database" \
  || fail "Postgres custom migration: semaphore role cannot manage migrated database"

cleanup test_postgres_custom_migration
cleanup_dir "$TEST_PG_CUSTOM_DATA"
cleanup_dir "$TEST_PG_CUSTOM_INIT"
rm -rf "$TEST_PG_CUSTOM_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-02E: PostgreSQL Mixed Object Ownership Migration ---"
TEST_PG_MIXED_DIR=$(mktemp -d)
TEST_PG_MIXED_DATA="$TEST_PG_MIXED_DIR/pgdata"
TEST_PG_MIXED_INIT="$TEST_PG_MIXED_DIR/custom-init"
mkdir -p "$TEST_PG_MIXED_DATA" "$TEST_PG_MIXED_INIT"
chmod 0750 "$TEST_PG_MIXED_DATA" "$TEST_PG_MIXED_INIT"
install -m 0755 "$REPO_ROOT/roles/nextcloud/files/db_wrapper.sh" \
  "$TEST_PG_MIXED_INIT/db_wrapper.sh"
$DOCKER run --rm -v "$TEST_PG_MIXED_DATA":/target alpine chown 999:999 /target
$DOCKER run --rm -v "$TEST_PG_MIXED_INIT":/target alpine chown -R 999:999 /target

$DOCKER run -d --name test_postgres_mixed_seed \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=postgres_admin \
  --env POSTGRES_PASSWORD=adminpass \
  --env POSTGRES_DB=nextcloud \
  --volume "$TEST_PG_MIXED_DATA":/var/lib/postgresql/data \
  "$POSTGRES_IMAGE"

sleep 15
$DOCKER exec test_postgres_mixed_seed env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres \
  -c "CREATE ROLE nextcloud_user LOGIN PASSWORD 'ncpass';"
$DOCKER exec test_postgres_mixed_seed env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres \
  -c "CREATE ROLE paperless_user LOGIN PASSWORD 'plpass';"
$DOCKER exec test_postgres_mixed_seed env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres \
  -c "CREATE ROLE semaphore_user LOGIN PASSWORD 'sempass';"
$DOCKER exec test_postgres_mixed_seed env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres \
  -c "CREATE DATABASE paperless OWNER paperless_user;"
$DOCKER exec test_postgres_mixed_seed env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d postgres \
  -c "CREATE DATABASE semaphore OWNER semaphore_user;"
$DOCKER exec test_postgres_mixed_seed env PGPASSWORD=adminpass \
  psql -h localhost -U postgres_admin -d semaphore \
  -c "CREATE TABLE django_migrations (id serial primary key, app text, name text, applied timestamptz);"

cleanup test_postgres_mixed_seed

$DOCKER run -d --name test_postgres_mixed_migration \
  --user 999:999 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=2g --memory-swap=2g \
  --shm-size=256m \
  --env POSTGRES_USER=postgres_admin \
  --env POSTGRES_PASSWORD=adminpass \
  --env POSTGRES_DB=nextcloud \
  --env NEXTCLOUD_DB_NAME=nextcloud \
  --env NEXTCLOUD_DB_USER=nextcloud_user \
  --env NEXTCLOUD_DB_PASSWORD=ncpass \
  --env PAPERLESS_DB_NAME=paperless \
  --env PAPERLESS_DB_USER=paperless_user \
  --env PAPERLESS_DB_PASSWORD=plpass \
  --env SEMAPHORE_DB_NAME=semaphore \
  --env SEMAPHORE_DB_USER=semaphore_user \
  --env SEMAPHORE_DB_PASSWORD=sempass \
  --volume "$TEST_PG_MIXED_DATA":/var/lib/postgresql/data \
  --volume "$TEST_PG_MIXED_INIT":/custom-init \
  --entrypoint /custom-init/db_wrapper.sh \
  "$POSTGRES_IMAGE"

sleep 20
$DOCKER inspect --format='{{.State.Status}}' test_postgres_mixed_migration 2>/dev/null \
  | grep -q running && pass "Postgres mixed migration: wrapper starts with existing service-owned databases" \
  || fail "Postgres mixed migration: wrapper failed with existing service-owned databases"
$DOCKER exec test_postgres_mixed_migration env PGPASSWORD=sempass \
  psql -h localhost -U semaphore_user -d semaphore \
  -c "SELECT * FROM django_migrations; INSERT INTO django_migrations(app, name) VALUES ('main', '0001_initial');" \
  >/dev/null 2>&1 && pass "Postgres mixed migration: semaphore role can access legacy admin-owned tables after normalization" \
  || fail "Postgres mixed migration: semaphore role still cannot access legacy admin-owned tables"

cleanup test_postgres_mixed_migration
cleanup_dir "$TEST_PG_MIXED_DATA"
cleanup_dir "$TEST_PG_MIXED_INIT"
rm -rf "$TEST_PG_MIXED_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-03: Redis ---"
$DOCKER run -d --name test_redis \
  --cap-drop=ALL \
  --cap-add=CHOWN \
  --cap-add=FOWNER \
  --cap-add=DAC_OVERRIDE \
  --security-opt=no-new-privileges:true \
  --memory=512m --memory-swap=512m \
  "$REDIS_IMAGE"

check_running test_redis "Redis: starts with cap-drop=ALL + CHOWN/FOWNER/DAC_OVERRIDE + 512m limit"
sleep 3
$DOCKER exec test_redis redis-cli ping \
  | grep -q PONG && pass "Redis: ping succeeds" || fail "Redis: ping failed"

cleanup test_redis
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-04: Nextcloud ---"
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
  "$NEXTCLOUD_IMAGE"

sleep 20
$DOCKER inspect --format='{{.State.Status}}' test_nextcloud \
  | grep -q running \
  && pass "Nextcloud: starts with no-new-privileges (cap-drop=ALL omitted — requires CHOWN for rsync entrypoint)" \
  || fail "Nextcloud: failed to start"

cleanup test_nextcloud
cleanup_dir "$TEST_NC_DIR"
echo ""

# ---------------------------------------------------------------------------
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
$DOCKER run -d --name test_traefik_nocap \
  --cap-drop=ALL \
  --volume "$TEST_TRAEFIK_DIR/traefik.yml":/etc/traefik/traefik.yml:ro \
  -p 18080:80 \
  "$TRAEFIK_IMAGE"
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
  "$TRAEFIK_IMAGE"
check_running test_traefik_cap "Traefik: starts with cap-drop=ALL + NET_BIND_SERVICE"

cleanup test_traefik_cap
rm -rf "$TEST_TRAEFIK_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-06: Paperless NGX ---"
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
  "$PAPERLESS_IMAGE"
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
echo "--- TEST-07: Vaultwarden ---"
TEST_VW_DIR=$(mktemp -d)
chmod 0777 "$TEST_VW_DIR"

$DOCKER run -d --name test_vaultwarden \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --memory=256m --memory-swap=256m \
  --volume "$TEST_VW_DIR":/data \
  -e SIGNUPS_ALLOWED=false \
  "$VAULTWARDEN_IMAGE"

check_running test_vaultwarden "Vaultwarden: starts with cap-drop=ALL + NET_BIND_SERVICE + no-new-privileges"

cleanup test_vaultwarden
rm -rf "$TEST_VW_DIR"
echo ""

# ---------------------------------------------------------------------------
echo "--- TEST-08: Semaphore ---"
# Test A: baseline
$DOCKER run -d --name test_semaphore_base \
  -e SEMAPHORE_DB_DIALECT=bolt \
  -e SEMAPHORE_ADMIN=admin \
  -e SEMAPHORE_ADMIN_PASSWORD=Admin1234! \
  -e SEMAPHORE_ADMIN_NAME=Admin \
  -e SEMAPHORE_ADMIN_EMAIL=admin@test.local \
  -e SEMAPHORE_ACCESS_KEY_ENCRYPTION=aabbccddaabbccddaabbccddaabbccdd \
  "$SEMAPHORE_IMAGE"
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
  -e ANSIBLE_SSH_ARGS="-o UserKnownHostsFile=/etc/ssh/ssh_known_hosts -o StrictHostKeyChecking=yes" \
  "$SEMAPHORE_IMAGE"
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
echo "--- TEST-09: Navidrome ---"
TEST_ND_DATA=$(mktemp -d)
TEST_ND_MUSIC=$(mktemp -d)
chmod 0770 "$TEST_ND_DATA"
$DOCKER run --rm -v "$TEST_ND_DATA":/target alpine chown 33:33 /target

$DOCKER run -d --name test_navidrome \
  --user "33:33" \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=256m --memory-swap=256m \
  --volume "$TEST_ND_MUSIC":/music:ro \
  --volume "$TEST_ND_DATA":/data \
  -e ND_LOGLEVEL=info \
  "$NAVIDROME_IMAGE"

check_running test_navidrome "Navidrome: starts with explicit non-root 33:33 + cap-drop=ALL"

cleanup test_navidrome
cleanup_dir "$TEST_ND_DATA"
rm -rf "$TEST_ND_MUSIC"
echo ""

# ---------------------------------------------------------------------------
echo "=== Tests complete. Review PASS/FAIL/WARN/INFO lines above. ==="

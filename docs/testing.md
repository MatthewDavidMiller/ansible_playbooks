# Testing

## CI/CD Pipeline

Checks run automatically on every `git commit` via a local pre-commit hook at `hooks/pre-commit`.

**Install the hook:**

```bash
git config core.hooksPath hooks
```

This only needs to be run once per clone. Git will then execute `hooks/pre-commit` before every commit.

**What runs:**

1. **`ansible-lint`** — Uses the `.ansible-lint` configuration at repo root. Catches playbook syntax errors, best practice violations, and role structural issues.
2. **Ansible syntax check** — Runs `ansible-playbook --syntax-check` against all main homelab playbooks (`vm1.yml`, `vpn.yml`, `pihole.yml`, `unificontroller.yml`, `apcontroller.yml`, `backup.yml`). Catches undefined role references, template parse errors, and structural YAML problems without connecting to any host.

**Container security tests** (`scripts/test_container_security.sh`) are run manually, not on every commit — they pull Docker images and take several minutes. Run them before deploying security flag changes to production. See [Container Security Testing](#container-security-testing) below.

**Skip the hook** (use sparingly):

```bash
git commit --no-verify
```

**Local vs production:** The `:Z` SELinux volume relabeling flags used in production Ansible roles are omitted from tests — they are only needed on Rocky Linux 10 with SELinux enforcing, not on the Ubuntu dev machine.

---

## Container Security Testing

Tests for verifying that proposed security flags (`--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory`, `--shm-size`) do not break container startup or functionality.

Run these from the development machine (Ubuntu WSL). Docker 29.2.1+ required; `podman` can be substituted.

> **Note:** `:Z` SELinux volume flags are omitted — not needed on Ubuntu.

---

## Quick Start

```bash
cd /home/matthew/matt_dev/ansible_playbooks
bash scripts/test_container_security.sh 2>&1 | tee /tmp/container_test_results.txt
grep -E "^(PASS|FAIL|WARN|INFO)" /tmp/container_test_results.txt
```

---

## Helper Functions

All tests rely on these helpers defined at the top of the test script:

```bash
cleanup() { docker rm -f "$1" 2>/dev/null || true; }
pass()    { echo "PASS: $1"; }
fail()    { echo "FAIL: $1"; exit 1; }
check_running() {
  sleep 5
  docker inspect --format='{{.State.Status}}' "$1" 2>/dev/null \
    | grep -q running && pass "$2" || fail "$2"
}
```

---

## TEST-01: PostgreSQL v17 — cap-drop + shm-size + directory ownership

**What it tests:** PostgreSQL 17 starts with `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory=4g`, and `--shm-size=256m`. Data directory is owned by UID 999 (the postgres user inside the image) with mode 0750. Verifies `pg_isready` returns success.

**Why it matters:** The shared PostgreSQL 17 container hosts databases for Nextcloud, Paperless NGX, and Semaphore. The `--shm-size=256m` is required because the default 64 MB container shm causes errors under normal Postgres load.

> **Note:** Directory ownership is set via a temporary Alpine container (`docker run --rm ... alpine chown`) rather than `sudo chown`, so the test runs without elevated privileges.

```bash
TEST_PG_DIR=$(mktemp -d)
chmod 0750 "$TEST_PG_DIR"
docker run --rm -v "$TEST_PG_DIR":/target alpine chown 999:999 /target

docker run -d --name test_postgres \
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

# PostgreSQL takes ~15s to initialise
sleep 15
docker inspect --format='{{.State.Status}}' test_postgres \
  | grep -q running && pass "Postgres: starts with cap-drop=ALL + shm-size=256m + 0750/999:999 dir" \
  || fail "Postgres: starts with cap-drop=ALL + shm-size=256m + 0750/999:999 dir"
docker exec test_postgres pg_isready -U testuser \
  && pass "Postgres: pg_isready succeeds" || fail "Postgres: pg_isready failed"

cleanup test_postgres
# Restore ownership to current user before rm (avoids sudo)
docker run --rm -v "$(dirname "$TEST_PG_DIR")":/mnt \
  alpine chown -R "$(id -u):$(id -g)" "/mnt/$(basename "$TEST_PG_DIR")"
rm -rf "$TEST_PG_DIR"
```

**Expected result:** `PASS` on both checks.

---

## TEST-02: Redis — cap-drop + memory limit

**What it tests:** Redis starts with `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory=512m`. Verifies `redis-cli ping` returns PONG.

**Why it matters:** Redis has no persistent volumes in this deployment; OOM kill is acceptable (Nextcloud reconnects). Memory limit prevents cache runaway.

```bash
docker run -d --name test_redis \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=512m --memory-swap=512m \
  docker.io/redis:latest

check_running test_redis "Redis: starts with cap-drop=ALL + 512m limit"

sleep 3
docker exec test_redis redis-cli ping \
  | grep -q PONG && pass "Redis: ping succeeds" || fail "Redis: ping failed"

cleanup test_redis
```

**Expected result:** `PASS` on both checks.

---

## TEST-03: Nextcloud — no-new-privileges + www-data volume ownership

**What it tests:** Nextcloud starts with `--security-opt=no-new-privileges:true` and `--memory=4g`. Data volume is owned by UID 33 (www-data) with mode 0770.

**Why it matters:** Nextcloud's entrypoint runs `rsync --chown` to copy the webroot on every container start. This requires the `CHOWN` capability, so `--cap-drop=ALL` is **not** applied to Nextcloud — doing so causes startup failure. Production config uses `--security-opt=no-new-privileges:true` only.

> **Note:** Directory ownership is set via a temporary Alpine container, not `sudo`.

```bash
TEST_NC_DIR=$(mktemp -d)
chmod 0770 "$TEST_NC_DIR"
docker run --rm -v "$TEST_NC_DIR":/target alpine chown 33:33 /target

docker run -d --name test_nextcloud \
  --security-opt=no-new-privileges:true \
  --memory=4g --memory-swap=4g \
  --volume "$TEST_NC_DIR":/var/www/html \
  -e SQLITE_DATABASE=testdb \
  docker.io/nextcloud:latest

# Nextcloud initialization takes ~20 seconds
sleep 20
docker inspect --format='{{.State.Status}}' test_nextcloud \
  | grep -q running \
  && pass "Nextcloud: starts with no-new-privileges (cap-drop=ALL omitted — requires CHOWN for rsync entrypoint)" \
  || fail "Nextcloud: failed to start"

cleanup test_nextcloud
docker run --rm -v "$(dirname "$TEST_NC_DIR")":/mnt \
  alpine chown -R "$(id -u):$(id -g)" "/mnt/$(basename "$TEST_NC_DIR")"
rm -rf "$TEST_NC_DIR"
```

**Expected result:** `PASS`. Some initialization log noise is acceptable.

---

## TEST-04: Traefik — cap-drop with and without NET_BIND_SERVICE

**What it tests:**
- **Test A (no cap):** Traefik with `--cap-drop=ALL` and no cap added back. On a real kernel, binding port 80 inside the container requires `NET_BIND_SERVICE`; this test documents whether WSL enforces this.
- **Test B (with cap):** Traefik with `--cap-drop=ALL --cap-add=NET_BIND_SERVICE`. Should always succeed.

**Why it matters:** The production Podman container on Rocky Linux WILL enforce capability restrictions. Traefik must have `NET_BIND_SERVICE` when `--cap-drop=ALL` is set.

```bash
TEST_TRAEFIK_DIR=$(mktemp -d)
cat > "$TEST_TRAEFIK_DIR/traefik.yml" <<'EOF'
api:
  insecure: true
entryPoints:
  web:
    address: ":80"
EOF

# Test A: without NET_BIND_SERVICE
docker run -d --name test_traefik_nocap \
  --cap-drop=ALL \
  --volume "$TEST_TRAEFIK_DIR/traefik.yml":/etc/traefik/traefik.yml:ro \
  -p 18080:80 \
  docker.io/traefik:v3
sleep 5
docker inspect --format='{{.State.Status}}' test_traefik_nocap 2>/dev/null \
  | grep -q running \
  && echo "INFO: Traefik runs without NET_BIND_SERVICE (WSL does not enforce this cap)" \
  || echo "INFO: Traefik exits without NET_BIND_SERVICE — NET_BIND_SERVICE is required (expected on real kernel)"
cleanup test_traefik_nocap

# Test B: with NET_BIND_SERVICE (must pass)
docker run -d --name test_traefik_cap \
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
```

**Expected result:** Test A is informational only. Test B: `PASS`.

---

## TEST-05: Paperless NGX — USERMAP compatibility with security flags

**What it tests:** Two sub-tests to determine whether `--security-opt=no-new-privileges:true` breaks Paperless NGX's `USERMAP_UID/GID` mechanism (which uses `gosu` to drop privileges on startup).

- **Test A:** `--cap-drop=ALL` only (no `no-new-privileges`). Should work cleanly.
- **Test B:** `--cap-drop=ALL` + `--security-opt=no-new-privileges:true`. May show permission errors if `gosu` is blocked.

**Why it matters:** If Test B fails, omit `--security-opt=no-new-privileges:true` from the Paperless container only.

> Redis and Postgres connections will fail (intentionally — no real backends in this test). Look for `gosu` or privilege-related errors, not connection errors.

> **Note:** Directory ownership is set via a temporary Alpine container, not `sudo`.

```bash
TEST_PL_DATA=$(mktemp -d)
TEST_PL_MEDIA=$(mktemp -d)
TEST_PL_EXPORT=$(mktemp -d)
TEST_PL_CONSUME=$(mktemp -d)
docker run --rm \
  -v "$TEST_PL_DATA":/d1 -v "$TEST_PL_MEDIA":/d2 \
  -v "$TEST_PL_EXPORT":/d3 -v "$TEST_PL_CONSUME":/d4 \
  alpine chown 1000:1000 /d1 /d2 /d3 /d4

# Test A: cap-drop=ALL only
docker run -d --name test_paperless_caps \
  --cap-drop=ALL \
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
echo "Test A status: $(docker inspect --format='{{.State.Status}}' test_paperless_caps 2>/dev/null)"
docker logs test_paperless_caps 2>&1 | grep -qi "gosu\|permission denied\|operation not permitted" \
  && echo "WARN A: Paperless cap-drop=ALL shows privilege errors" \
  || echo "INFO A: Paperless cap-drop=ALL looks clean"
cleanup test_paperless_caps

# Test B: cap-drop=ALL + no-new-privileges
docker run -d --name test_paperless_nnp \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
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
echo "Test B status: $(docker inspect --format='{{.State.Status}}' test_paperless_nnp 2>/dev/null)"
docker logs test_paperless_nnp 2>&1 | grep -qi "gosu\|permission denied\|operation not permitted" \
  && echo "WARN B: Paperless + no-new-privileges shows privilege errors — OMIT this flag from production" \
  || echo "INFO B: Paperless + no-new-privileges appears clean — safe to add"
cleanup test_paperless_nnp

# Restore ownership before rm (avoids sudo)
for d in "$TEST_PL_DATA" "$TEST_PL_MEDIA" "$TEST_PL_EXPORT" "$TEST_PL_CONSUME"; do
  docker run --rm -v "$(dirname "$d")":/mnt \
    alpine chown -R "$(id -u):$(id -g)" "/mnt/$(basename "$d")"
  rm -rf "$d"
done
```

**Expected result:** `INFO A` (clean). For Test B: `INFO B` means both flags are safe; `WARN B` means omit `--security-opt=no-new-privileges:true` from Paperless in production.

---

## TEST-06: Vaultwarden — cap-drop + no-new-privileges

**What it tests:** Vaultwarden (Rust binary) starts with `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory=256m`.

```bash
TEST_VW_DIR=$(mktemp -d)
chmod 0700 "$TEST_VW_DIR"

docker run -d --name test_vaultwarden \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=256m --memory-swap=256m \
  --volume "$TEST_VW_DIR":/data \
  docker.io/vaultwarden/server:latest

check_running test_vaultwarden "Vaultwarden: starts with cap-drop=ALL + no-new-privileges"

cleanup test_vaultwarden
rm -rf "$TEST_VW_DIR"
```

**Expected result:** `PASS`.

---

## TEST-07: Semaphore — cap-drop capability check

**What it tests:** Whether Semaphore (which runs Ansible and forks SSH subprocesses) can start with `--cap-drop=ALL`. Two sub-tests:

- **Test A:** Baseline without cap-drop (must pass).
- **Test B:** With `--cap-drop=ALL`. If Ansible's subprocess operations require capabilities, this will fail or produce errors.

> Uses `SEMAPHORE_DB_DIALECT=bolt` (file-based DB) to avoid needing a Postgres instance.

```bash
# Test A: baseline
docker run -d --name test_semaphore_base \
  -e SEMAPHORE_DB_DIALECT=bolt \
  -e SEMAPHORE_ADMIN=admin \
  -e SEMAPHORE_ADMIN_PASSWORD=Admin1234! \
  -e SEMAPHORE_ADMIN_NAME=Admin \
  -e SEMAPHORE_ADMIN_EMAIL=admin@test.local \
  -e SEMAPHORE_ACCESS_KEY_ENCRYPTION=aabbccddaabbccddaabbccddaabbccdd \
  docker.io/semaphoreui/semaphore:latest
sleep 8
docker inspect --format='{{.State.Status}}' test_semaphore_base \
  | grep -q running && pass "Semaphore: baseline starts" || fail "Semaphore: baseline failed"
cleanup test_semaphore_base

# Test B: with cap-drop=ALL
docker run -d --name test_semaphore_caps \
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
docker inspect --format='{{.State.Status}}' test_semaphore_caps 2>/dev/null \
  | grep -q running \
  && pass "Semaphore: starts with cap-drop=ALL" \
  || echo "WARN: Semaphore exits with cap-drop=ALL — check logs for required capabilities"
docker logs test_semaphore_caps 2>&1 | tail -20
cleanup test_semaphore_caps
```

**Expected result:** Test A: `PASS`. Test B: `PASS` is ideal; `WARN` means investigate logs to determine which capability to add back.

---

## TEST-08: Navidrome — existing --user flag + cap-drop

**What it tests:** Navidrome starts with its existing `--user $(id -u):33` flag plus the new `--cap-drop=ALL` and `--security-opt=no-new-privileges`. Data volume owned by `$(id-u):33`.

**Why it matters:** Navidrome already has the correct `--user` flag. This confirms cap hardening doesn't break it.

```bash
TEST_ND_DATA=$(mktemp -d)
TEST_ND_MUSIC=$(mktemp -d)
chmod 0770 "$TEST_ND_DATA"
docker run --rm -v "$TEST_ND_DATA":/target alpine chown "$(id -u):33" /target

docker run -d --name test_navidrome \
  --user "$(id -u):33" \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=512m --memory-swap=512m \
  --volume "$TEST_ND_MUSIC":/music:ro \
  --volume "$TEST_ND_DATA":/data \
  -e ND_LOGLEVEL=info \
  docker.io/deluan/navidrome:latest

check_running test_navidrome "Navidrome: starts with --user $(id -u):33 + cap-drop=ALL"

cleanup test_navidrome
docker run --rm -v "$(dirname "$TEST_ND_DATA")":/mnt \
  alpine chown -R "$(id -u):$(id -g)" "/mnt/$(basename "$TEST_ND_DATA")"
rm -rf "$TEST_ND_DATA" "$TEST_ND_MUSIC"
```

**Expected result:** `PASS`.

---

## TEST-09: WireGuard — privileged mode baseline

**What it tests:** The linuxserver WireGuard container starts with `--privileged=true` and `--memory=128m`. WireGuard requires privileged mode for kernel module loading and sysctl configuration; the standard `--cap-drop=ALL` pattern does not apply here.

**Why it matters:** WireGuard is the only container that uses `--privileged=true` instead of cap-drop. This test verifies the image starts correctly with that flag. In environments without the `wireguard` kernel module (e.g. WSL2 without the module), the container will exit immediately with a module-load error — this is reported as `INFO`, not `FAIL`.

```bash
TEST_WG_DIR=$(mktemp -d)
chmod 0755 "$TEST_WG_DIR"

docker run -d --name test_wireguard \
  --privileged=true \
  --volume "$TEST_WG_DIR":/config \
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

WG_STATUS=$(docker inspect --format='{{.State.Status}}' test_wireguard 2>/dev/null || echo "missing")
if [ "$WG_STATUS" = "running" ]; then
  pass "WireGuard: starts with --privileged=true"
else
  WG_LOGS=$(docker logs test_wireguard 2>&1)
  if echo "$WG_LOGS" | grep -qi "wireguard\|modprobe\|module\|ip_tables\|nft"; then
    echo "INFO: WireGuard exited — kernel module not available (expected on WSL without wireguard module)"
  else
    echo "WARN: WireGuard exited unexpectedly; last 10 log lines:"
    echo "$WG_LOGS" | tail -10
  fi
fi

cleanup test_wireguard
rm -rf "$TEST_WG_DIR"
```

**Expected result:** `PASS` when the host has the WireGuard kernel module loaded. `INFO` on WSL without the module. `WARN` indicates an unexpected failure worth investigating.

---

## Interpreting Results

| Output | Meaning |
|---|---|
| `PASS: ...` | Test succeeded — safe to deploy this flag combination |
| `FAIL: ...` | Test failed — do NOT deploy until root cause is resolved |
| `WARN: ...` | Potential issue found — review logs before deploying |
| `INFO: ...` | Informational — no action required |

After running, compare results against the compatibility matrix in the plan before applying changes to production via Ansible.

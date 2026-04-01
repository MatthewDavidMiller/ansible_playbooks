#!/bin/bash
set -euo pipefail

export POSTGRES_USER=${POSTGRES_USER:-postgres}
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-}
export POSTGRES_LEGACY_BOOTSTRAP_USER=${POSTGRES_LEGACY_BOOTSTRAP_USER:-}
export POSTGRES_LEGACY_BOOTSTRAP_PASSWORD=${POSTGRES_LEGACY_BOOTSTRAP_PASSWORD:-}
export POSTGRES_DB=${POSTGRES_DB:-postgres}

BOOTSTRAP_DB=postgres
BOOTSTRAP_USER=""
BOOTSTRAP_PASSWORD=""
BOOTSTRAP_HOST=localhost

echo "[INFO] Starting PostgreSQL in background..."
docker-entrypoint.sh postgres &
POSTGRES_PID=$!

# Wait for the final server (TCP) — the temp initdb server only listens on
# Unix socket (listen_addresses=''), so -h localhost skips it correctly.
echo "[INFO] Waiting for PostgreSQL to become available..."
until pg_isready -h localhost -U "$POSTGRES_USER" -d "$BOOTSTRAP_DB" >/dev/null 2>&1; do
    sleep 2
done

echo "[INFO] PostgreSQL is ready. Ensuring databases exist..."

can_connect() {
    local role_name="$1"
    local role_password="$2"

    [ -n "$role_name" ] || return 1

    PGPASSWORD="$role_password" \
        psql -h localhost -U "$role_name" -d "$BOOTSTRAP_DB" -w -Atqc \
        "SELECT CASE
            WHEN EXISTS (
                SELECT 1
                FROM pg_roles
                WHERE rolname = current_user
                  AND rolsuper
            ) THEN 1
            ELSE 0
        END" 2>/dev/null | grep -q '^1$'
}

set_bootstrap_role() {
    BOOTSTRAP_USER="$1"
    BOOTSTRAP_PASSWORD="$2"
    BOOTSTRAP_HOST="$3"
    if [ -n "$BOOTSTRAP_HOST" ]; then
        echo "[INFO] Using PostgreSQL bootstrap role over TCP: $BOOTSTRAP_USER"
    else
        echo "[INFO] Using PostgreSQL bootstrap role over local socket: $BOOTSTRAP_USER"
    fi
}

can_connect_local_postgres() {
    psql -U postgres -d "$BOOTSTRAP_DB" -w -Atqc \
        "SELECT CASE
            WHEN EXISTS (
                SELECT 1
                FROM pg_roles
                WHERE rolname = current_user
                  AND rolsuper
            ) THEN 1
            ELSE 0
        END" 2>/dev/null | grep -q '^1$'
}

resolve_bootstrap_role() {
    if can_connect "$POSTGRES_USER" "$POSTGRES_PASSWORD"; then
        set_bootstrap_role "$POSTGRES_USER" "$POSTGRES_PASSWORD" "localhost"
        return 0
    fi

    if can_connect "$POSTGRES_LEGACY_BOOTSTRAP_USER" "$POSTGRES_LEGACY_BOOTSTRAP_PASSWORD"; then
        set_bootstrap_role "$POSTGRES_LEGACY_BOOTSTRAP_USER" "$POSTGRES_LEGACY_BOOTSTRAP_PASSWORD" "localhost"
        return 0
    fi

    if can_connect "$NEXTCLOUD_DB_USER" "$NEXTCLOUD_DB_PASSWORD"; then
        set_bootstrap_role "$NEXTCLOUD_DB_USER" "$NEXTCLOUD_DB_PASSWORD" "localhost"
        return 0
    fi

    if can_connect "$PAPERLESS_DB_USER" "$PAPERLESS_DB_PASSWORD"; then
        set_bootstrap_role "$PAPERLESS_DB_USER" "$PAPERLESS_DB_PASSWORD" "localhost"
        return 0
    fi

    if can_connect "$SEMAPHORE_DB_USER" "$SEMAPHORE_DB_PASSWORD"; then
        set_bootstrap_role "$SEMAPHORE_DB_USER" "$SEMAPHORE_DB_PASSWORD" "localhost"
        return 0
    fi

    if can_connect_local_postgres; then
        set_bootstrap_role "postgres" "" ""
        return 0
    fi

    return 1
}

psql_admin() {
    local db_name="$1"
    shift

    if [ -n "$BOOTSTRAP_HOST" ]; then
        PGPASSWORD="$BOOTSTRAP_PASSWORD" \
            psql -h "$BOOTSTRAP_HOST" -U "$BOOTSTRAP_USER" -d "$db_name" -v ON_ERROR_STOP=1 "$@"
    else
        psql -U "$BOOTSTRAP_USER" -d "$db_name" -v ON_ERROR_STOP=1 "$@"
    fi
}

ensure_admin_role() {
    psql_admin "$BOOTSTRAP_DB" \
        -v role_name="$POSTGRES_USER" \
        -v role_password="$POSTGRES_PASSWORD" <<'SQL'
SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'role_name'
    ) THEN format(
        'ALTER ROLE %I WITH SUPERUSER LOGIN PASSWORD %L',
        :'role_name',
        :'role_password'
    )
    ELSE format(
        'CREATE ROLE %I WITH SUPERUSER LOGIN PASSWORD %L',
        :'role_name',
        :'role_password'
    )
END
\gexec
SQL
}

ensure_role() {
    local role_name="$1"
    local role_password="$2"

    psql_admin "$BOOTSTRAP_DB" \
        -v role_name="$role_name" \
        -v role_password="$role_password" <<'SQL'
SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'role_name'
    ) THEN format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'role_name',
        :'role_password'
    )
    ELSE format(
        'CREATE ROLE %I WITH LOGIN PASSWORD %L',
        :'role_name',
        :'role_password'
    )
END
\gexec
SQL
}

get_db_owner() {
    local db_name="$1"

    psql_admin "$BOOTSTRAP_DB" -Atq -v db_name="$db_name" <<'SQL'
SELECT pg_catalog.pg_get_userbyid(datdba)
FROM pg_database
WHERE datname = :'db_name';
SQL
}

ensure_database() {
    local db_name="$1"
    local db_owner="$2"
    local previous_owner=""

    previous_owner="$(get_db_owner "$db_name")"

    if [ -z "$previous_owner" ]; then
        psql_admin "$BOOTSTRAP_DB" -v db_name="$db_name" -v db_owner="$db_owner" <<'SQL'
SELECT format(
    'CREATE DATABASE %I OWNER %I',
    :'db_name',
    :'db_owner'
)
\gexec
SQL
        return 0
    fi

    if [ "$previous_owner" != "$db_owner" ]; then
        psql_admin "$BOOTSTRAP_DB" -v db_name="$db_name" -v db_owner="$db_owner" <<'SQL'
SELECT format(
    'ALTER DATABASE %I OWNER TO %I',
    :'db_name',
    :'db_owner'
)
\gexec
SQL

    fi

    psql_admin "$db_name" -v db_owner="$db_owner" <<'SQL'
SELECT format(
    'ALTER SCHEMA %I OWNER TO %I',
    n.nspname,
    :'db_owner'
)
FROM pg_namespace AS n
WHERE pg_catalog.pg_get_userbyid(n.nspowner) <> :'db_owner'
  AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
\gexec

SELECT format(
    CASE c.relkind
        WHEN 'r' THEN 'ALTER TABLE %I.%I OWNER TO %I'
        WHEN 'p' THEN 'ALTER TABLE %I.%I OWNER TO %I'
        WHEN 'S' THEN 'ALTER SEQUENCE %I.%I OWNER TO %I'
        WHEN 'v' THEN 'ALTER VIEW %I.%I OWNER TO %I'
        WHEN 'm' THEN 'ALTER MATERIALIZED VIEW %I.%I OWNER TO %I'
        WHEN 'f' THEN 'ALTER FOREIGN TABLE %I.%I OWNER TO %I'
    END,
    n.nspname,
    c.relname,
    :'db_owner'
)
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE pg_catalog.pg_get_userbyid(c.relowner) <> :'db_owner'
  AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_class'::regclass
        AND d.objid = c.oid
        AND d.deptype = 'e'
  )
  AND (
      c.relkind <> 'S'
      OR NOT EXISTS (
          SELECT 1
          FROM pg_depend AS d
          WHERE d.classid = 'pg_class'::regclass
            AND d.objid = c.oid
            AND d.refclassid = 'pg_class'::regclass
            AND d.deptype IN ('a', 'i')
      )
  )
\gexec

SELECT format(
    'ALTER ROUTINE %I.%I(%s) OWNER TO %I',
    n.nspname,
    p.proname,
    pg_catalog.pg_get_function_identity_arguments(p.oid),
    :'db_owner'
)
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE pg_catalog.pg_get_userbyid(p.proowner) <> :'db_owner'
  AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_proc'::regclass
        AND d.objid = p.oid
        AND d.deptype = 'e'
  )
\gexec

SELECT format(
    'ALTER TYPE %I.%I OWNER TO %I',
    n.nspname,
    t.typname,
    :'db_owner'
)
FROM pg_type AS t
JOIN pg_namespace AS n
  ON n.oid = t.typnamespace
LEFT JOIN pg_class AS c
  ON c.oid = t.typrelid
WHERE pg_catalog.pg_get_userbyid(t.typowner) <> :'db_owner'
  AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND t.typtype IN ('d', 'e', 'r')
  AND c.oid IS NULL
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_type'::regclass
        AND d.objid = t.oid
        AND d.deptype = 'e'
  )
\gexec

SELECT format(
    'ALTER EXTENSION %I OWNER TO %I',
    e.extname,
    :'db_owner'
)
FROM pg_extension AS e
WHERE pg_catalog.pg_get_userbyid(e.extowner) <> :'db_owner'
  AND e.extname <> 'plpgsql'
\gexec
SQL
}

if ! resolve_bootstrap_role; then
    echo "[ERROR] Could not authenticate to the existing PostgreSQL cluster with any known bootstrap credential." >&2
    echo "[ERROR] Tried postgres_admin, the optional legacy bootstrap role, the configured Nextcloud/Paperless/Semaphore DB users, and the legacy local postgres role." >&2
    exit 1
fi

ensure_admin_role

ensure_role "$NEXTCLOUD_DB_USER" "$NEXTCLOUD_DB_PASSWORD"
ensure_role "$PAPERLESS_DB_USER" "$PAPERLESS_DB_PASSWORD"
ensure_role "$SEMAPHORE_DB_USER" "$SEMAPHORE_DB_PASSWORD"

ensure_database "$NEXTCLOUD_DB_NAME" "$NEXTCLOUD_DB_USER"
ensure_database "$PAPERLESS_DB_NAME" "$PAPERLESS_DB_USER"
ensure_database "$SEMAPHORE_DB_NAME" "$SEMAPHORE_DB_USER"

echo "[INFO] Database setup complete."
wait $POSTGRES_PID

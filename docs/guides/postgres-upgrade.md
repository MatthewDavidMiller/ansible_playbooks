# PostgreSQL Major Version Upgrade Guide

Use this procedure when upgrading the PostgreSQL major version on VM1. The `postgres` container hosts three databases: Nextcloud, Paperless NGX, and Semaphore.

---

## Method: Dump/Restore

PostgreSQL data directories are not compatible between major versions. Two approaches exist:

**`pg_upgrade`** (via `tianon/postgres-upgrade` image): Performs a binary-level transformation of the data directory. Faster, but unreliable in Podman — link mode (`--link`) fails across container volume mounts in most configurations. The image's own README warns against using it as-is.

**Dump/Restore** (selected approach): `pg_dumpall` produces a portable SQL file that restores cleanly into any newer major version. Slower but straightforward, fully verifiable at each step, and universally supported.

---

## Application Compatibility

Before upgrading, verify that all three applications support the target PostgreSQL version:

| Application | Minimum version | Check |
|---|---|---|
| Nextcloud | 14 | [System requirements](https://docs.nextcloud.com/server/stable/admin_manual/installation/system_requirements.html) |
| Paperless-NGX | 14 | [Administration docs](https://docs.paperless-ngx.com/administration/) |
| Semaphore | Not explicitly documented | [Docker install guide](https://docs.semaphoreui.com/administration-guide/installation/docker) |

---

## Upgrade Procedure

### Phase 0 — Pre-migration backups

Run while all services are still up. This is the safety net if anything goes wrong.

```bash
# Full pg_dumpall — captures roles and all three databases
podman exec postgres pg_dumpall -U <nextcloud_database_user> > /root/pg_dumpall_$(date +%Y%m%d).sql

# Verify it is non-empty
wc -l /root/pg_dumpall_$(date +%Y%m%d).sql
```

### Phase 1 — Stop all dependent services

```bash
# Put Nextcloud in maintenance mode before stopping postgres
podman exec nextcloud php occ maintenance:mode --on

systemctl stop semaphore nextcloud_container paperless_ngx navidrome_container vaultwarden traefik
```

### Phase 2 — Final consistent dump and stop postgres

```bash
# Final dump with no app connections — guarantees a consistent snapshot
podman exec postgres pg_dumpall -U <nextcloud_database_user> > /root/pg_final_$(date +%Y%m%d_%H%M).sql

systemctl stop postgres_container

# Archive the old data directory — do not delete it yet
mv <postgres_path>/pgdata <postgres_path>/pgdata_bak

# Create a fresh empty pgdata directory for the new version
mkdir -p <postgres_path>/pgdata && chmod 0777 <postgres_path>/pgdata
```

### Phase 3 — Update and deploy the Ansible config

Update `roles/nextcloud/templates/postgres_container.sh.j2` to the target PostgreSQL version tag. Run the playbook to deploy the new image and any updated configuration:

```bash
ansible-playbook -i inventory.yml vm1.yml
```

### Phase 4 — Start the new postgres and restore

```bash
# Start the new postgres container — db_wrapper.sh will initialize and create all databases/roles
systemctl start postgres_container

# Wait for postgres to be ready
until podman exec postgres pg_isready -h localhost -U <nextcloud_database_user>; do sleep 3; done

# Restore all databases from the final dump
# Warnings like "role already exists" and "database already exists" are expected — db_wrapper.sh
# pre-creates them, and pg_dumpall's CREATE statements fail harmlessly on existing objects
podman exec -i postgres psql -U <nextcloud_database_user> < /root/pg_final_$(date +%Y%m%d_*).sql
```

### Phase 5 — Post-restore hygiene

```bash
# Fix collation version mismatch warnings (informational, not fatal)
# PostgreSQL tracks the glibc collation version in each database and warns when it changes
podman exec postgres psql -U <nextcloud_database_user> \
    -c "ALTER DATABASE <nextcloud_database_name> REFRESH COLLATION VERSION;"
podman exec postgres psql -U <nextcloud_database_user> \
    -c "ALTER DATABASE <paperless_database_name> REFRESH COLLATION VERSION;"
podman exec postgres psql -U <nextcloud_database_user> \
    -c "ALTER DATABASE <semaphore_database_name> REFRESH COLLATION VERSION;"

# Refresh query planner statistics — recommended by PostgreSQL after dump/restore
podman exec postgres vacuumdb --all --analyze-in-stages -U <nextcloud_database_user>
```

### Phase 6 — Start all services and verify

```bash
systemctl start redis_container nextcloud_container paperless_ngx \
    navidrome_container vaultwarden semaphore traefik

# Confirm all three databases are present
podman exec postgres psql -U <nextcloud_database_user> -c "\l"
# Expect: nextcloud, paperless, semaphore, postgres, template0, template1

# Take Nextcloud out of maintenance mode
podman exec nextcloud php occ maintenance:mode --off

# Spot-check application connectivity
podman logs semaphore 2>&1 | tail -20     # should show successful DB connection
curl -sk https://<nextcloud_dns_name>/status.php   # expect installed:true, maintenance:false
curl -sk https://<semaphore_dns_name>/api/ping     # expect 200
```

### Phase 7 — Cleanup (after 24 hours of verified normal operation)

```bash
rm -rf <postgres_path>/pgdata_bak
rm /root/pg_dumpall_*.sql /root/pg_final_*.sql
podman rmi docker.io/postgres:<old_version>
```

---

## Notes

**"Already exists" warnings during restore:** `pg_dumpall` emits `CREATE ROLE` and `CREATE DATABASE` statements. When restoring into a postgres instance where `db_wrapper.sh` has already created the roles and databases, these statements fail with "already exists". psql logs them as errors but continues — the subsequent `\connect` and data restore statements succeed normally.

**Collation version mismatch:** If the host OS upgrades glibc between PostgreSQL versions, the stored collation version in each database will differ from what PostgreSQL 17 reports. `REFRESH COLLATION VERSION` updates the stored version to match. This is informational — queries continue to work — but silencing the warning is good practice.

**Semaphore role password:** The `semaphore_database_user` role is created by `db_wrapper.sh` using the password rendered from `semaphore_database_user_password` at Ansible deploy time. The `CREATE ROLE ... PASSWORD` statement only runs at initial creation. If this password changes in inventory, update it manually:
```bash
podman exec postgres psql -U <nextcloud_database_user> \
    -c "ALTER ROLE <semaphore_database_user> PASSWORD 'newpassword';"
```

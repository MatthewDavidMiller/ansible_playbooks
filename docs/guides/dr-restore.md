# Disaster Recovery and Restore Guide

This guide covers two scenarios:

- **Part 1 — Initial Migration:** One-time migration from separate service VMs (100, 113, 114, 115) to VM1 (ID 120)
- **Part 2 — VM1 Disaster Recovery:** Rebuilding VM1 from backups after a failure

For VM provisioning details see [proxmox-setup.md](proxmox-setup.md).

---

## Backup Coverage Reference

| Data | Backup mechanism | Location |
|---|---|---|
| Nextcloud + Paperless DBs | Borg archive → rclone daily | `Nextcloud:<nextcloud_paperless_backup_location>` |
| Paperless document exports | Included in Borg archive above | same |
| Nextcloud user files | Borg archive on second NVMe disk (backup role, daily) | `{{ borg_backup_path }}` on VM1 |
| Vaultwarden SQLite DB | Direct cp to Nextcloud data dir (`backup_local: true`) | `{{ nextcloud_path }}/data/{{ nextcloud_admin_user }}/files/<vaultwarden_backup_location>` |
| Navidrome DB | Direct cp to Nextcloud data dir (`backup_local: true`) | `{{ nextcloud_path }}/data/{{ nextcloud_admin_user }}/files/<navidrome_backup_location>` |
| Semaphore PostgreSQL 17 DB | Direct cp to Nextcloud data dir (`backup_local: true`) | `{{ nextcloud_path }}/data/{{ nextcloud_admin_user }}/files/<semaphore_backup_location>` |
| Navidrome music | Local bind-mount of Nextcloud data dir — source is Nextcloud user files (backed up by Borg above) | n/a |
| SWAG/TLS certificates | Regeneratable via DNS-01 challenge | n/a |
| Redis | Cache only — acceptable loss | n/a |
| Proxmox node config | Script on Proxmox host → rclone daily | `Nextcloud:<proxmox_backup_location>` |

> Variable names above refer to host variables in your `inventory.yml`. See [inventory.md](../inventory.md#vm1-host-vm1-id-120).

---

## Proxmox Node Configuration

`/etc/pve/` holds all Proxmox node configuration: VM definitions, storage config, users, and datacenter settings. `scripts/backup_proxmox_config.sh` archives this directory and uploads it to Nextcloud daily via rclone. The script runs directly on the Proxmox host (not via Ansible).

### Restore procedure

**1. Download the latest archive from Nextcloud:**
```bash
rclone copy Nextcloud:<proxmox_backup_location>/proxmox_config_<DATE>.tar.gz /restore_staging/
```

Alternatively, download from the Nextcloud web UI.

**2. Extract to a staging directory:**
```bash
mkdir -p /restore_staging/pve
tar -xzf /restore_staging/proxmox_config_<DATE>.tar.gz -C /restore_staging/pve --strip-components 1
```

**3. Restore key configuration files:**

> Do not bulk-overwrite `/etc/pve/` — Proxmox's clustered filesystem manages parts of this directory live. Restore individual files as needed:

```bash
# VM configurations
cp /restore_staging/pve/qemu-server/*.conf /etc/pve/qemu-server/

# Storage, users, datacenter settings
cp /restore_staging/pve/storage.cfg /etc/pve/storage.cfg
cp /restore_staging/pve/user.cfg    /etc/pve/user.cfg
cp /restore_staging/pve/datacenter.cfg /etc/pve/datacenter.cfg
```

**4. Verify the node is healthy:**
```bash
pvesh get /nodes/<nodename>/status
```

---

## Alternative: Disk-Move Migration

If the Nextcloud data disk and Borg backup disk are **separate virtual disks** in Proxmox (not on the OS disk), you can detach them from the old VM and reattach to VM1 directly. This is faster than the full Borg restore in Part 1 because Nextcloud user files are already on the mounted disk — no extraction required.

The existing Ansible playbooks support this without changes: mounts are UUID-based and idempotent, directory creation is idempotent, and the Borg init script skips initialization if a repo already exists.

### When to use this

- **Initial migration (Part 1 alternative):** The Nextcloud data disk lives on VM 113 (or wherever Nextcloud was previously hosted) as a separate virtual disk.
- **Disaster recovery (Part 2 alternative):** VM1's OS disk failed but the Nextcloud data disk and/or Borg backup disk are intact — see the [Part 2 note below](#part-2-vm1-disaster-recovery-rebuild-from-backups) before starting a full restore.

### What each disk carries

| Disk | Inventory variable | Contains |
|---|---|---|
| Nextcloud data disk | `nextcloud_disk` → `nextcloud_path` | User files, config.php, apps, local Borg archive (`nextcloud_borg_backup_path`) with PG15 SQL dumps and Paperless exports, plus Vaultwarden/Navidrome/Semaphore backup files stored inside `nextcloud_path/data/` |
| Borg backup disk | `backup_disk` → `borg_backup_path` | Full daily Borg snapshots of the entire `nextcloud_path` directory tree |

The live PostgreSQL data directories (`postgres_path`, `semaphore_postgres_path`) are on the OS disk — they are separate configured paths, not under `nextcloud_path`, so they are not on the data disk and are not carried over when you move the disk to a new VM. Databases must be restored from the SQL dumps in the Borg archive.

> **Backup gap:** The SQL dumps in the Borg archive are from the last backup run (daily cron). The live filesystem on the data disk may be ahead of that by up to ~24 hours. After restoring the database, run `occ files:scan --all` (Step 5) to reconcile file presence between the database and the live filesystem. Note that DB-only data modified after the last backup — shares, comments, tags, calendar/contacts, app settings — will revert to the dump state and cannot be recovered from this backup strategy.

### SELinux note (Arch Linux source disk → Rocky Linux 10)

Arch Linux does not use SELinux, so files on the disk carry no SELinux xattrs. Rocky Linux 10 runs SELinux enforcing. Two different situations arise:

**Container-mounted directories** (`base/`, `data/`, `config/`, `apps/`, all Paperless dirs)
These are all mounted with the `:Z` Podman volume flag, which automatically relabels files to `container_file_t` on first container start. No manual action is needed, but **expect the first startup to be very slow** — Podman relabels every file recursively, which can take a long time for a large Nextcloud data directory. The container is not hung; it is relabeling. Check progress with:
```bash
journalctl -fu nextcloud_container
```

**Borg-accessed directories** (`nextcloud_borg_backup_path`, `borg_backup_path`)
These are read/written by the host-level `borg` process (via cron), not by a container, so `:Z` never relabels them. SELinux may deny borg access to unlabeled files. Run `restorecon` after `vm1.yml` completes and before the first backup cron fires:
```bash
restorecon -Rv <nextcloud_borg_backup_path>
restorecon -Rv <borg_backup_path>
```

**UID/GID ownership** — numeric UIDs are OS-agnostic. UID 33 (Nextcloud container user) is the same value on any distro. No ownership mapping is needed.

---

### Step 1: Move disks in Proxmox

Detach the Nextcloud data disk from the old VM and attach it to VM1. See [proxmox-setup.md — Detaching and Moving an Existing Disk](proxmox-setup.md#detaching-and-moving-an-existing-disk) for the Proxmox UI and CLI procedure.

If the Borg backup disk is also a separate virtual disk on the old backup VM (VM 106), repeat the process for that disk.

The UUIDs are stored on the disks themselves and do not change through a move. No inventory updates are needed.

### Step 2: Run the playbook

```bash
ansible-playbook -i inventory.yml vm1.yml
```

The playbook mounts both disks (data already present), deploys all container services, and sets up backup scripts. All Nextcloud user files and config are immediately available.

### Step 3: Restore PostgreSQL databases

The Borg archive at `nextcloud_borg_backup_path` (on the now-mounted Nextcloud data disk) contains the PostgreSQL dumps. No rclone download is needed.

**3a. List available archives:**
```bash
borg list <nextcloud_borg_backup_path>
```

**3b. Extract the latest archive to a staging directory:**
```bash
mkdir /restore_staging
cd /restore_staging
borg extract <nextcloud_borg_backup_path>::<archive_name>
```

> The archive contains the SQL dumps at the root level (`nextcloud_db_<DATE>.sql`, `paperless_db_<DATE>.sql`) and the Paperless export directory at its full original path (`<paperless_export_path>/<DATE>/`). After extraction, the SQL files are at `/restore_staging/nextcloud_db_<DATE>.sql` and `/restore_staging/paperless_db_<DATE>.sql`; the Paperless export is at `/restore_staging<paperless_export_path>/<DATE>/`.

**3c. Restore Nextcloud database:**

> **Note:** The dump includes `ALTER TABLE ... OWNER TO` and `GRANT` statements referencing the role that owned the database at backup time (typically the value of `nextcloud_database_user` at that time, e.g. `oc_admin`). If that role does not exist in the fresh instance, create it before importing — otherwise those statements error and ownership is not set correctly.

```bash
# Create the role referenced in the dump if it doesn't exist in the fresh instance
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> -d postgres \
  -c "CREATE ROLE oc_admin WITH LOGIN PASSWORD '<nextcloud_database_user_password>';"
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> -d postgres -c "DROP DATABASE IF EXISTS <nextcloud_database_name>;"
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> -d postgres -c "CREATE DATABASE <nextcloud_database_name>;"
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> <nextcloud_database_name> < /restore_staging/nextcloud_db_<DATE>.sql
```

**3d. Restore Paperless database:**
```bash
podman exec -i postgres psql -h localhost -U <paperless_database_user> -d postgres -c "DROP DATABASE IF EXISTS <paperless_database_name>;"
podman exec -i postgres psql -h localhost -U <paperless_database_user> -d postgres -c "CREATE DATABASE <paperless_database_name>;"
podman exec -i postgres psql -h localhost -U <paperless_database_user> <paperless_database_name> < /restore_staging/paperless_db_<DATE>.sql
```

**3e. Import Paperless documents:**
```bash
cp -r /restore_staging<paperless_export_path>/<DATE>/ <paperless_export_path>/
podman exec paperless document_importer /usr/src/paperless/export/<DATE>
```

### Step 4: Restore Navidrome, Vaultwarden, Semaphore

These backup files are stored inside `nextcloud_path/data/<nextcloud_admin_user>/files/` and are already available on the mounted disk. Follow Steps 3–5 from Part 1 below.

### Step 5: Rescan Nextcloud file index

The restored database reflects the last backup, but the live filesystem on the data disk may have newer files. This command rescans the filesystem and updates the database to match — adding missing entries, removing stale entries, and refreshing metadata.

```bash
podman exec nextcloud php occ files:scan --all
```

### Step 6: DNS cutover and verification

Follow Steps 6–7 from Part 1 below.

---

## Part 1: Initial Migration (Separate VMs → VM1)

### Pre-Migration Checklist

Before decommissioning any source VM:

1. Confirm rclone remotes are configured and reachable on each source VM:
   ```bash
   rclone ls Nextcloud:
   ```
2. Run backup scripts manually on each source VM and confirm success:
   ```bash
   # On VM 113 (Nextcloud/Paperless)
   bash /usr/local/bin/backup_nextcloud_paperless.sh

   # On VM 114 (Navidrome)
   bash /usr/local/bin/backup_navidrome.sh

   # On VM 115 (Vaultwarden)
   bash /usr/local/bin/backup_vaultwarden_db.sh

   # On VM 100 (Semaphore)
   bash /usr/local/bin/backup_semaphore.sh
   ```
3. Confirm backup files appear in Nextcloud (via web UI or `rclone ls Nextcloud:<backup_location>`).
4. Note the IP address of each source VM — you may need SSH access during restore.

---

### Step 1: Provision VM1

1. Clone the Rocky Linux 10 template:
   ```bash
   python3 scripts/proxmox_initial_setup.py
   ```
   This creates VMID 120. If VM1 already exists, skip this step.

2. Resize the root disk (required — VM1 needs 60 GB):
   ```bash
   qm resize 120 scsi0 60G
   ```

3. Configure cloud-init (IP, SSH key, user), then start the VM.

4. Run the playbook:
   ```bash
   ansible-playbook -i inventory.yml vm1.yml
   ```

---

### Step 2: Restore Nextcloud + Paperless

The Borg archive (`nextcloud_borg_backup_path`) contains PostgreSQL dumps for both Nextcloud and Paperless, plus Paperless document exports. Nextcloud user files (photos, documents) are in a separate Borg archive on the second NVMe disk (`borg_backup_path`) managed by the `backup` role.

**2a. Retrieve the Borg archive from Nextcloud:**
```bash
# On VM1 — download the Borg repo from Nextcloud
rclone sync Nextcloud:<nextcloud_paperless_backup_location> <nextcloud_borg_backup_path>
```

**2b. List available archives:**
```bash
borg list <nextcloud_borg_backup_path>
```

**2c. Extract the latest archive to a staging directory:**
```bash
mkdir /restore_staging
cd /restore_staging
borg extract <nextcloud_borg_backup_path>::<archive_name>
```

> The archive contains the SQL dumps at the root level (`nextcloud_db_<DATE>.sql`, `paperless_db_<DATE>.sql`) and the Paperless export directory at its full original path (`<paperless_export_path>/<DATE>/`). After extraction, the SQL files are at `/restore_staging/nextcloud_db_<DATE>.sql` and `/restore_staging/paperless_db_<DATE>.sql`; the Paperless export is at `/restore_staging<paperless_export_path>/<DATE>/`.

**2d. Restore Nextcloud database:**

> **Note:** The dump includes `ALTER TABLE ... OWNER TO` and `GRANT` statements referencing the role that owned the database at backup time (typically the value of `nextcloud_database_user` at that time, e.g. `oc_admin`). If that role does not exist in the fresh instance, create it before importing — otherwise those statements error and ownership is not set correctly.

```bash
# Create the role referenced in the dump if it doesn't exist in the fresh instance
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> -d postgres \
  -c "CREATE ROLE oc_admin WITH LOGIN PASSWORD '<nextcloud_database_user_password>';"
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> -d postgres -c "DROP DATABASE IF EXISTS <nextcloud_database_name>;"
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> -d postgres -c "CREATE DATABASE <nextcloud_database_name>;"
podman exec -i postgres psql -h localhost -U <nextcloud_database_user> <nextcloud_database_name> < /restore_staging/nextcloud_db_<DATE>.sql
```

**2e. Restore Paperless database:**
```bash
podman exec -i postgres psql -h localhost -U <paperless_database_user> -d postgres -c "DROP DATABASE IF EXISTS <paperless_database_name>;"
podman exec -i postgres psql -h localhost -U <paperless_database_user> -d postgres -c "CREATE DATABASE <paperless_database_name>;"
podman exec -i postgres psql -h localhost -U <paperless_database_user> <paperless_database_name> < /restore_staging/paperless_db_<DATE>.sql
```

**2f. Import Paperless documents:**
```bash
# Copy the export directory into place (borg preserves the full original path under /restore_staging)
cp -r /restore_staging<paperless_export_path>/<DATE>/ <paperless_export_path>/

# Trigger the document importer
podman exec paperless document_importer /usr/src/paperless/export/<DATE>
```

**2g. Restore Nextcloud user files from the Borg archive on the second NVMe disk:**
```bash
# List available archives
borg list <borg_backup_path>

# Extract the latest archive (contains the full nextcloud_path directory)
mkdir /restore_staging/nextcloud_files
cd /restore_staging/nextcloud_files
borg extract <borg_backup_path>::<archive_name>

# Copy user files into place
rsync -a /restore_staging/nextcloud_files/<nextcloud_path>/data/ <nextcloud_path>/data/
```

> **Prerequisites**: The second NVMe disk must be attached and formatted before running `vm1.yml`. See [VM1 Second Disk (Borg Backup)](proxmox-setup.md#vm1-second-disk-borg-backup) in the Proxmox setup guide. After provisioning, initialize the Borg repo with `bash /usr/local/bin/init_backup_repo.sh` and confirm backups are running before decommissioning source VMs.

**2h. Rescan Nextcloud file index:**
```bash
podman exec nextcloud php occ files:scan --all
```

---

### Step 3: Restore Navidrome

On VM1, Navidrome's music library is a local bind-mount of `<nextcloud_path>/data/<nextcloud_admin_user>/files/Music` — it will be available automatically once Nextcloud user files are restored (Step 2g). Only the database needs to be restored.

**3a. Copy backup from the Nextcloud data directory:**
```bash
cp <nextcloud_path>/data/<nextcloud_admin_user>/files/<navidrome_backup_location>/<latest>.db /restore_staging/
```

**3b. Stop Navidrome, restore the database, restart:**
```bash
systemctl stop navidrome_container
cp /restore_staging/<latest>.db <navidrome_path>/data/navidrome.db
systemctl start navidrome_container
```

---

### Step 4: Restore Vaultwarden

**4a. Locate the backup in the Nextcloud data directory:**
```bash
ls <nextcloud_path>/data/<nextcloud_admin_user>/files/<vaultwarden_backup_location>/
```

**4b. Stop Vaultwarden, restore the database, restart:**
```bash
systemctl stop vaultwarden
cp <nextcloud_path>/data/<nextcloud_admin_user>/files/<vaultwarden_backup_location>/vaultwarden_db-<DATE>.sqlite3 \
    <vaultwarden_path>/vw-data/db.sqlite3
chown 1000:1000 <vaultwarden_path>/vw-data/db.sqlite3
systemctl start vaultwarden
```

---

### Step 5: Restore Semaphore

**5a. Locate the SQL dump in the Nextcloud data directory:**
```bash
ls <nextcloud_path>/data/<nextcloud_admin_user>/files/<semaphore_backup_location>/
```

**5b. Restore the PostgreSQL 17 database:**
```bash
podman exec -i semaphore_postgres psql -h localhost -U <semaphore_database_user> -d postgres -c "DROP DATABASE IF EXISTS <semaphore_database_name>;"
podman exec -i semaphore_postgres psql -h localhost -U <semaphore_database_user> -d postgres -c "CREATE DATABASE <semaphore_database_name>;"
podman exec -i semaphore_postgres psql -h localhost -U <semaphore_database_user> <semaphore_database_name> \
    < <nextcloud_path>/data/<nextcloud_admin_user>/files/<semaphore_backup_location>/semaphore_db_<DATE>.sql
```

**5c. Restart Semaphore:**
```bash
systemctl restart semaphore
```

---

### Step 6: DNS Cutover

Update DNS records to point each service subdomain to VM1's IP address:

| Subdomain | Service |
|---|---|
| `nextcloud.<top_domain>` | Nextcloud |
| `paperless.<top_domain>` | Paperless NGX |
| `navidrome.<top_domain>` | Navidrome |
| `vault.<top_domain>` | Vaultwarden |
| `semaphore.<top_domain>` | Semaphore |

SWAG will issue a new wildcard certificate via DNS-01 challenge on first startup if the existing certificate does not carry over.

---

### Step 7: Verification

Confirm each service is functional:

- [ ] Nextcloud loads and user files are visible
- [ ] Paperless documents are present and searchable
- [ ] Navidrome music library is visible (populated from Nextcloud user files restored in Step 2g)
- [ ] Vaultwarden vault unlocks with existing credentials
- [ ] Semaphore projects and inventories are present
- [ ] SWAG issued a valid TLS certificate (check browser padlock)
- [ ] Backup scripts are running: `crontab -l`

---

## Part 2: VM1 Disaster Recovery (Rebuild from Backups)

Use this procedure if VM1 fails and must be rebuilt from scratch. Backups are current as of the most recent daily cron run.

> **If only the OS disk failed:** If the Nextcloud data disk (`nextcloud_disk`) and Borg backup disk (`backup_disk`) are intact, use the [Disk-Move Migration](#alternative-disk-move-migration) procedure instead of the full Borg restore below. Attach both disks to the new VM1, run `vm1.yml`, then restore only the PostgreSQL databases and Paperless documents from the local Borg archive. This avoids downloading the Borg archive from Nextcloud remote storage.

### Step 1: Provision a new VM1

Follow Step 1 from Part 1 above (provision + resize + cloud-init + `ansible-playbook -i inventory.yml vm1.yml`).

### Step 2: Restore all services

Follow Steps 2–5 from Part 1. For Nextcloud user files (Step 2g), restore from the Borg archive on the second NVMe disk (`borg_backup_path`) — the archive contains the full `nextcloud_path` directory including all user files.

### Step 3: Re-point DNS

DNS already points to VM1's IP. If you used a different IP for the replacement VM, update DNS records as in Part 1, Step 6.

### Step 4: Verification

Run the same verification checklist as Part 1, Step 7.

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
| Vaultwarden SQLite DB | rclone daily | `Nextcloud:<vaultwarden_backup_location>` |
| Navidrome DB | rclone daily | `Nextcloud:<navidrome_backup_location>` |
| Semaphore PostgreSQL 17 DB | rclone daily | `Nextcloud:<semaphore_backup_location>` |
| Navidrome music | External rclone FUSE mount — source unchanged | n/a |
| SWAG/TLS certificates | Regeneratable via DNS-01 challenge | n/a |
| Redis | Cache only — acceptable loss | n/a |

> Variable names above refer to host variables in your `inventory.yml`. See [inventory.md](../inventory.md#vm1-host-vm1-id-120).

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
borg extract <nextcloud_borg_backup_path>::<archive_name> --strip-components 1 --destination /restore_staging
```

**2d. Restore Nextcloud database:**
```bash
podman exec -i postgres psql -U <nextcloud_database_user> -d postgres -c "DROP DATABASE IF EXISTS <nextcloud_database_name>;"
podman exec -i postgres psql -U <nextcloud_database_user> -d postgres -c "CREATE DATABASE <nextcloud_database_name>;"
podman exec -i postgres psql -U <nextcloud_database_user> <nextcloud_database_name> < /restore_staging/nextcloud_db_<DATE>.sql
```

**2e. Restore Paperless database:**
```bash
podman exec -i postgres psql -U <paperless_database_user> -d postgres -c "DROP DATABASE IF EXISTS <paperless_database_name>;"
podman exec -i postgres psql -U <paperless_database_user> -d postgres -c "CREATE DATABASE <paperless_database_name>;"
podman exec -i postgres psql -U <paperless_database_user> <paperless_database_name> < /restore_staging/paperless_db_<DATE>.sql
```

**2f. Import Paperless documents:**
```bash
# The export directory is mounted at paperless_export_path in the container
# Copy the export directory into place
cp -r /restore_staging/<DATE>/ <paperless_export_path>/

# Trigger the document importer
podman exec paperless document_importer /usr/src/paperless/export/<DATE>
```

**2g. Restore Nextcloud user files from the Borg archive on the second NVMe disk:**
```bash
# List available archives
borg list <borg_backup_path>

# Extract the latest archive (contains the full nextcloud_path directory)
mkdir /restore_staging/nextcloud_files
borg extract <borg_backup_path>::<archive_name> --destination /restore_staging/nextcloud_files

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

Navidrome's music library is mounted via rclone from Nextcloud WebDAV — it will be available automatically once the rclone mount service starts. Only the database needs to be restored.

**3a. Download backup from Nextcloud:**
```bash
rclone copy Nextcloud:<navidrome_backup_location>/ /restore_staging/navidrome/
```

**3b. Identify the latest `.db` file and copy it into place:**
```bash
ls /restore_staging/navidrome/
cp /restore_staging/navidrome/<latest>.db <navidrome_path>/data/navidrome.db
```

**3c. Restart Navidrome:**
```bash
systemctl restart navidrome_container
```

---

### Step 4: Restore Vaultwarden

**4a. Download backup from Nextcloud:**
```bash
rclone copy Nextcloud:<vaultwarden_backup_location>/ /restore_staging/vaultwarden/
```

**4b. Stop Vaultwarden, restore the database, restart:**
```bash
systemctl stop vaultwarden
cp /restore_staging/vaultwarden/vaultwarden_db-<DATE>.sqlite3 <vaultwarden_path>/vw-data/db.sqlite3
chown 1000:1000 <vaultwarden_path>/vw-data/db.sqlite3
systemctl start vaultwarden
```

---

### Step 5: Restore Semaphore

**5a. Download backup from Nextcloud:**
```bash
rclone copy Nextcloud:<semaphore_backup_location>/ /restore_staging/semaphore/
```

**5b. Restore the PostgreSQL 17 database:**
```bash
podman exec -i semaphore_postgres psql -U <semaphore_database_user> -d postgres -c "DROP DATABASE IF EXISTS <semaphore_database_name>;"
podman exec -i semaphore_postgres psql -U <semaphore_database_user> -d postgres -c "CREATE DATABASE <semaphore_database_name>;"
podman exec -i semaphore_postgres psql -U <semaphore_database_user> <semaphore_database_name> < /restore_staging/semaphore/semaphore_db_<DATE>.sql
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
- [ ] Navidrome music library is visible (rclone mount may take a minute)
- [ ] Vaultwarden vault unlocks with existing credentials
- [ ] Semaphore projects and inventories are present
- [ ] SWAG issued a valid TLS certificate (check browser padlock)
- [ ] Backup scripts are running: `crontab -l`

---

## Part 2: VM1 Disaster Recovery (Rebuild from Backups)

Use this procedure if VM1 fails and must be rebuilt from scratch. Backups are current as of the most recent daily cron run.

### Step 1: Provision a new VM1

Follow Step 1 from Part 1 above (provision + resize + cloud-init + `ansible-playbook -i inventory.yml vm1.yml`).

### Step 2: Restore all services

Follow Steps 2–5 from Part 1. For Nextcloud user files (Step 2g), restore from the Borg archive on the second NVMe disk (`borg_backup_path`) — the archive contains the full `nextcloud_path` directory including all user files.

### Step 3: Re-point DNS

DNS already points to VM1's IP. If you used a different IP for the replacement VM, update DNS records as in Part 1, Step 6.

### Step 4: Verification

Run the same verification checklist as Part 1, Step 7.

# Disaster Recovery and Restore Guide

Use this procedure to rebuild VM1 from scratch after a failure. Backups are current as of the most recent daily cron run.

> **If only the OS disk failed:** If the data disk (`data_disk`) and Borg backup disk (`backup_disk`) are intact, use the [Disk-Move Migration](#alternative-disk-move-migration) procedure instead of a full Borg restore. Attach both disks to the new VM1 and run `vm1.yml`; homedrive's store is on the data disk, so nothing needs extracting.

For VM provisioning details see [proxmox-setup.md](proxmox-setup.md).

---

## Backup Coverage Reference

| Data | Backup mechanism | Location |
|---|---|---|
| homedrive store: every file and version, trash, and the service backups below | Daily Borg archive (`homedrive-*`, `backup_homedrive.sh`), plus an optional `homedrive backup-store` copy on an external disk | `{{ homedrive_borg_repo }}` (the backup disk's `{{ borg_backup_path }}` by default) |
| Vaultwarden SQLite DB | Daily file, stored in the drive through `homedrive_import_path.sh`; every day is kept | `homedrive_backup_user`'s drive, folder `<vaultwarden_backup_location>` |
| music-server data (sealed roster, playlists, stars, plays) | Daily tar archive stored in the drive; files over 30 days old go to the drive's trash | `homedrive_backup_user`'s drive, folder `<music_server_backup_location>` |
| playbook-runner data (ciphertext only) | Daily tar archive stored in the drive; files over 30 days old go to the drive's trash | `homedrive_backup_user`'s drive, folder `<playbook_runner_backup_location>` |
| playbook-runner master key | Not in any backup by design; kept in Vaultwarden and the external inventory | n/a |
| music-server master key and accounts | Not in any backup by design; `music_server_master_key` and `music_server_users` live in the vaulted inventory, the key also in Vaultwarden | n/a |
| Music library | homedrive's read-only `Music` export, rebuilt from the drive | n/a |
| music-server index and covers | Rebuilt by the first scan | n/a |
| Traefik/Let's Encrypt certificates | Regeneratable via DNS-01 challenge | n/a |
| Proxmox node config | Script on Proxmox host → rclone daily | `Homedrive:<proxmox_backup_location>` |

The service backups are inside the drive, so they are covered by the store's own Borg archive as well. The older `nextcloud_backup-*` archives, and the Borg archives of the Paperless export and the Nextcloud and Paperless databases from before those were retired, may still sit in the backup disk's repository and the Nextcloud data disk; nothing prunes them.

> Variable names above refer to host variables in your `inventory.yml`. See [inventory.md](../inventory.md#vm1-host).

---

## Proxmox Node Configuration

`/etc/pve/` holds all Proxmox node configuration: VM definitions, storage config, users, and datacenter settings. `scripts/backup_proxmox_config.sh` archives this directory and uploads it to homedrive daily via rclone. The script runs directly on the Proxmox host (not via Ansible).

### Restore procedure

**1. Download the latest archive from homedrive:**
```bash
rclone copy Homedrive:<proxmox_backup_location>/proxmox_config_<DATE>.tar.gz /restore_staging/
```

Alternatively, download it from homedrive's web UI.

**2. Extract to a staging directory:**
```bash
mkdir -p /restore_staging/pve
tar -xzf /restore_staging/proxmox_config_<DATE>.tar.gz -C /restore_staging/pve --strip-components 2
```

The archive stores paths below `etc/pve/`; stripping both leading components
places `qemu-server/`, `storage.cfg`, and the other configuration directly in
the staging directory used below.

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

If the data disk and Borg backup disk are **separate virtual disks** in Proxmox (not on the OS disk), you can detach them from the old VM and reattach to VM1 directly. This is faster than a Borg restore because homedrive's store is already on the mounted disk — no extraction required.

The existing Ansible playbooks support this without changes: mounts are UUID-based and idempotent, directory creation is idempotent, and the Borg init script skips initialization if a repo already exists.

### When to use this

- **Disaster recovery:** VM1's OS disk failed but the data disk and/or Borg backup disk are intact.

### What each disk carries

| Disk | Inventory variable | Contains |
|---|---|---|
| Data disk | `data_disk` → `data_disk_mount_path` | homedrive's store (`homedrive_path`) and its exports (`homedrive_export_path`): every file, version, and the service backups stored in the drive |
| Borg backup disk | `backup_disk` → `borg_backup_path` | The daily `homedrive-*` Borg archives of the store |

### SELinux note (Arch Linux source disk → Rocky Linux 10)

Arch Linux does not use SELinux, so files on a disk from an Arch host carry no SELinux xattrs. Rocky Linux 10 runs SELinux enforcing. Two different situations arise:

**Container-mounted directories** (the store and exports)
These are mounted with the `:Z` Podman volume flag, which relabels files to `container_file_t` on first container start. No manual action is needed, but **expect the first startup to be slow** for a large store: Podman relabels every file recursively. The container is not hung; it is relabeling. Check progress with:
```bash
journalctl -fu homedrive
```

**Borg-accessed directories** (`borg_backup_path`)
These are read and written by the host-level `borg` process (via cron), not by a container, so `:Z` never relabels them. SELinux may deny borg access to unlabeled files. Run `restorecon` after `vm1.yml` completes and before the first backup cron fires:
```bash
restorecon -Rv <borg_backup_path>
```

**UID/GID ownership** — numeric UIDs are OS-agnostic. The homedrive container user (10001) is the same value on any distro. No ownership mapping is needed.

---

### Step 1: Move disks in Proxmox

Detach the data disk from the old VM and attach it to VM1. See [proxmox-setup.md — Detaching and Moving an Existing Disk](proxmox-setup.md#detaching-and-moving-an-existing-disk) for the Proxmox UI and CLI procedure.

If the Borg backup disk is also a separate virtual disk, repeat the process for that disk.

The UUIDs are stored on the disks themselves and do not change through a move. No inventory updates are needed.

### Step 2: Run the playbook

```bash
ansible-playbook -i inventory.yml vm1.yml
```

The playbook mounts both disks (data already present), deploys all container services, and sets up backup scripts. homedrive starts on the existing store (it refuses to start on a directory without `store.id`, so an unmounted disk can never become a new, empty store).

### Step 3: Check the store

```bash
podman exec homedrive hd-server fsck --deep
```

### Step 4: Restore music-server, Vaultwarden, playbook-runner

These backup files are in the drive, which is already back. Follow [Steps 3–5](#step-3-restore-music-server) below.

### Step 5: DNS cutover and verification

Follow [Steps 6–7](#step-6-re-point-dns) below.

---

## Step 1: Provision a new VM1

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
   With `homedrive_deploy` set and no store on the data disk, set `homedrive_init_store: true` for this first run only, so the server may create an empty store. Take it out again before the restore below.

---

## Step 2: Restore the homedrive store

The store's Borg archives (`homedrive-*`) are on the backup disk, or in a `homedrive backup-store` copy on an external disk. The archive leaves out `history.id`, so the restored store makes a new one and every sync client compares everything afresh and uploads what the restore lost.

**2a. List the archives:**
```bash
borg list <borg_backup_path>
```

**2b. Stop the server and extract the newest archive over an empty store:**
```bash
systemctl stop homedrive
borg extract --strip-components <depth of the store path> <borg_backup_path>::<archive_name> <store path without the leading slash>
```

The strip count is the number of directories in the store path (`/data_drive/homedrive/store` is 3). The store directory must be empty first.

**2c. Start the server and check the store:**
```bash
systemctl start homedrive
podman exec homedrive hd-server fsck --deep
```

See [homedrive.md](homedrive.md#backups-and-restores) for the rest of the restore and repair procedures. Run the [restore drill](homedrive.md#the-restore-drill-proof-the-backups-work) to prove the archive restores before you need it.

---

## Step 3: Restore music-server

The music library is homedrive's `Music` export, so it is back once the store is restored. Only the data directory needs restoring: the sealed roster and each user's playlists, stars, and plays. The cache (library index and resized covers) rebuilds on the first scan.

The inventory must still carry the same `music_server_master_key` (also in Vaultwarden); without it the archive cannot be opened. Accounts and passwords come from `music_server_users` in the inventory, not the archive.

**3a. Fetch the newest archive from the drive.** The backups are files in `homedrive_backup_user`'s drive, in the `<music_server_backup_location>` folder. Restore that folder to plain files from a signed-in sync client, and copy the newest archive to VM1:
```bash
homedrive restore <music_server_backup_location> --to ~/restored/music_server
scp ~/restored/music_server/music_server_<latest>.tar.gz vm1:/restore_staging/music_server/
```

Without a client, `hd-server restore-tree --user <homedrive_backup_user> --to /restore_staging/drive` on VM1 writes the user's whole drive out as plain files with the server not using that store copy (see [homedrive.md](homedrive.md#restoring-to-plain-files-on-a-client)); the backups are then in the folder named above.

**3b. Stop the service and unpack the newest archive:**
```bash
systemctl stop music_server
tar -xzf /restore_staging/music_server/music_server_<latest>.tar.gz \
    -C <music_server_path>/data
chown -R 10001:10001 <music_server_path>/data
systemctl start music_server
```

**3c. Confirm:** `podman logs music_server` reports the accounts and a finished scan.

---

## Step 4: Restore Vaultwarden

**4a. Fetch the backups from the drive:**
Restore the folder to plain files from a signed-in sync client, as in Step 3a, and copy the file you want to VM1:
```bash
homedrive restore <vaultwarden_backup_location> --to ~/restored/vaultwarden
ls ~/restored/vaultwarden
scp ~/restored/vaultwarden/vaultwarden_db-<DATE>.sqlite3 vm1:/restore_staging/vaultwarden/
```

**4b. Stop Vaultwarden, restore the database, restart:**
```bash
systemctl stop vaultwarden
cp /restore_staging/vaultwarden/vaultwarden_db-<DATE>.sqlite3 \
    <vaultwarden_path>/vw-data/db.sqlite3
systemctl start vaultwarden
```

---

## Step 5: Restore playbook-runner

The runner needs the master key as well as its data. The key is not in any backup; take it from Vaultwarden (or the external inventory) and set `playbook_runner_master_key` before running `vm1.yml`, which provisions it as a Podman secret. With a wrong or missing key the runner refuses to start rather than serve data it cannot decrypt.

**5a. Fetch the newest archive from the drive:**
Restore the folder to plain files from a signed-in sync client, as in Step 3a, and copy the newest archive to VM1:
```bash
homedrive restore <playbook_runner_backup_location> --to ~/restored/playbook_runner
scp ~/restored/playbook_runner/playbook_runner_<DATE>.tar.gz vm1:/restore_staging/playbook_runner/
```

**5b. Stop the runner, unpack the archive over its data directory, restart:**
```bash
systemctl stop playbook_runner
tar -C <playbook_runner_path> --numeric-owner -xzf \
    /restore_staging/playbook_runner/playbook_runner_<DATE>.tar.gz
systemctl start playbook_runner
```

Runs that were in progress when the archive was taken show as `interrupted`.

---

## Step 6: Re-point DNS

DNS already points to VM1's IP. If you provisioned the replacement VM with a different IP, update DNS records to point each service subdomain to the new address:

| Subdomain | Service |
|---|---|
| `drive.<homelab_internal_domain>` | homedrive |
| `music.<homelab_internal_domain>` | music-server |
| `vault.<top_domain>` | Vaultwarden |
| `<playbook_runner_fqdn>` | playbook-runner |

Traefik will issue fresh per-service certificates via DNS-01 challenge if the existing `acme.json` state does not carry over.

---

## Step 7: Verification

Confirm each service is functional:

- [ ] homedrive's admin page reports no damage and a recent backup, and a sync client signs in and shows the expected files
- [ ] music-server's status page shows the library (populated from homedrive's `Music` export), and play:Sub shows each user's playlists
- [ ] Vaultwarden vault unlocks with existing credentials
- [ ] playbook-runner shows its secrets, inventories, templates, and schedules, and a check-mode run of `vm1.yml` succeeds
- [ ] Traefik issued valid TLS certificates (check browser padlock)
- [ ] Backup scripts are running: `crontab -l`

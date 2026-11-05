# homedrive on VM1

homedrive is the first-party file sync and storage server
(`ghcr.io/matthewdavidmiller/homedrive`, public, prerelease). The
`homedrive` role runs it behind Traefik at `drive.<homelab_internal_domain>`.

## Turning it on

The role does nothing until both:

1. the inventory sets `homedrive_deploy: true`, and
2. `artifacts/containers.lock.yml` has a reviewed `homedrive` entry
   (`scripts/review_container_updates.sh --service homedrive`).

The image is public, so VM1 pulls it anonymously by digest, like the
other first-party images.

homedrive is prerelease software (0.x) and may have issues. Keep the local
Borg backup and an administrator's copy (below) running, and watch the
weekly restore drill.

## Inventory

```yaml
homedrive_deploy: true
homedrive_users:                          # Vault
  - {name: alice, password: "...", admin: true, quota_gb: 500}
  - {name: bob, password: "...", quota_gb: 200}
homedrive_exports: "alice:Music=>music"         # optional
homedrive_borg_repo: /srv/backup/homedrive      # optional, another disk
homedrive_drill_path: /srv/backup/homedrive-drill   # default: <repo>-drill
homedrive_borg_passphrase: "..."                     # optional, Vault: encrypt a new repository
```

The store defaults to `/data_drive/homedrive/store` and exports to
`/data_drive/homedrive/exports`, beside Nextcloud on the data disk. The
`nextcloud` role owns that mount, so leave `homedrive_disk` unset there; a
second entry for the disk would mount it twice. Set `homedrive_disk` and
`homedrive_path` together only to give the store a disk of its own.

None of `homedrive_path`, `homedrive_borg_repo`, `homedrive_drill_path`
and `homedrive_export_path` may be, or be inside, another; the role
refuses the inventory otherwise. `homedrive_keep_all_days` and
`homedrive_trash_days` must be 7-36500, as the server requires.

On the **first** deploy only, add `homedrive_init_store: true` so the
role creates the store, then remove it. Without it the role refuses a
store path that has no `store.id`, so an unmounted disk can never become a
new, empty store.

Large WebDAV or browser uploads can take longer than Traefik's default
60-second read timeout. Set `traefik_read_timeout: 0s` (no limit) or a
long value if you upload large files that way. The sync client uploads in
chunks of at most 4 MiB and is not affected.

Every user needs a `quota_gb`. It counts every version and the trash,
so deleting files frees room only once retention purges them; raise the
quota instead. The quotas plus `homedrive_min_free_gb` must fit on the
store's disk, or homedrive refuses to start, so the drives can never
fill it. Size them against the disk, leaving room for anything else that
shares it. A full drive refuses new content, including backups imported
with `homedrive_import_path.sh`, and is reported to that user's clients.
Restores and rewinds are never refused.

homedrive watches each drive for unusual activity: many files changed or
deleted within an hour, or changes that make files look encrypted
(ransomware through WebDAV, for example). It tells that user's sync
clients, shows a banner in the web UI and the admin page, and logs an
`ALERT` line. Retention holds that drive until the owner dismisses the
alert in the web UI. Backup imports do not count.

## Backups and restores

With `homedrive_borg_repo` set, a nightly script writes a checkpoint and
then archives the store with borg, metadata first so the copy never names
an object it lacks. It leaves out `history.id`: a restored store makes a
new one when it starts, which tells every sync client that the server's
history changed, so they compare everything afresh and upload what the
restore lost instead of trusting what they last saw. If you restore a
store any other way (a disk copy, a snapshot), delete `history.id` from it
before starting the server. Run `hd-server fsck --deep` on a restored store
before trusting it.

Put the repository on another disk. A repository on the store's own disk
is still written, but every run is reported as failed until it moves,
because one disk failure would lose both.

Every run is reported to homedrive. A failed run, or none for two days,
shows on the admin page and as a notification on administrators' sync
clients. So does a failed import, which is how the other services'
backups land in the drive, and so is a full drive refusing one.

### The restore drill: proof the backups work

On Sundays, after the backup, `homedrive_restore_drill.sh` proves the
newest archive restores, all the way to plain files:

1. it extracts the archive to `homedrive_drill_path` (it needs about twice
   the store's size free there, and checks first). The drill marks that
   directory as its own with `.homedrive-drill-scratch` and empties only
   its own `store/` and `plain/` there. It refuses a directory that
   overlaps the store or the repository (after resolving links), or that
   already holds files it did not put there;
2. a one-off container with no network reads every version in the copy
   back (`fsck --deep`), then restores every user's drive to plain files,
   each verified against its SHA-256, with a `sha256sum` manifest per user;
3. each manifest is compared with the live drive: every file the drive had
   when the backup was taken must be there (by path, or by content if it
   has moved since), and nothing the drive never held may be.

The result is reported like a backup ("drill"), and a drill that fails or
has not succeeded for eight days reaches the administrators. The log is
`/var/log/homedrive_drill.log`. Run it by hand at any time:

```sh
/usr/local/bin/homedrive_restore_drill.sh          # restores, checks, cleans up
/usr/local/bin/homedrive_restore_drill.sh --keep   # leaves the plain files in <drill path>/plain
```

### Restoring to plain files on a client

The restored files are ordinary files with a manifest beside them, so
they can be checked anywhere. Copy a user's folder and manifest from a
drill run with `--keep` to a computer, and check them there:

```sh
homedrive check-files ~/restored/alice ~/restored/alice.sha256   # or: cd alice && sha256sum -c ../alice.sha256
```

A client can also restore straight from the server, into a new directory
outside its synced folders, with every file verified and a manifest
written beside it:

```sh
homedrive restore Documents --to ~/restored/Documents
```

`hd-server restore-tree --user U --to DIR` does the same on any store
copy, such as one extracted from a backup with the server not using it.

### A copy off the server

A backup on VM1's own disks is lost with VM1's host, and can be deleted by
anyone with root on VM1, ransomware included. So an administrator keeps a
copy of the whole store on another machine, pulled from the server: nothing
on VM1 can reach it.

- **With the sync client** (an administrator's device): run
  `homedrive backup-store /path/on/an/external/disk` now and then, weekly
  say. The first run copies everything; later runs fetch only what
  changed, since stored objects never change. Every object is verified
  before it is kept, and the copy is never left naming something it does
  not hold, even if a run is cut off.
- **From the browser**: the Admin page's "Download the store (.tar)" gives
  the same copy as one file.

The copy is the store itself, every drive with its history and trash, and
opens as one: `homedrive store-copy-check DIR` reads every version back,
and `homedrive store-copy-restore DIR --user U --to OUT` writes a drive out
as plain files with a manifest. It can also repair VM1's store
(`homedrive_repair.sh DIR`) or be served by a new homedrive. Each copy is
reported to homedrive; after eight days without one, the administrators are
reminded. Each run also keeps the metadata it replaces as a generation, so
the copy can be opened as it was at any earlier run (`--generation`), even
after the server has purged something or its metadata was tampered with.

Keep the copy on a disk you can unplug. It is unencrypted unless you
start it with `homedrive backup-store DIR --encrypt` (or give a passphrase
on the Admin page's download): then every file is sealed under the
passphrase, and the copy shows neither file names nor which content it
holds. Keep the passphrase somewhere other than the copy; without it the
copy cannot be read. Anyone with an administrator's password or device
token can take a copy, so keep those safe.

The local Borg repository is unencrypted too unless
`homedrive_borg_passphrase` (Vault, 20 characters or more) is set. Borg
cannot encrypt an existing repository, so set it together with a new
`homedrive_borg_repo` path; the backup refuses to run on an unencrypted
repository while a passphrase is set, rather than leave you believing it
is encrypted. The restore drill reads the passphrase the same way.

## Disk damage

The server guards against bit rot and a failing disk on its own. It
verifies every read, scrubs everything monthly, and sets aside anything
damaged or unreadable without deleting it. Sync clients that still have
an affected file send it again automatically, and get a notification
saying so; any damage left over shows on the admin page and as a
notification on every client. On Sundays the backup script also runs
`borg check` on the backup repository.

For damage no client can heal (old versions, trash, files only uploaded
through WebDAV), repair from a backup:

```sh
mkdir -p /scratch/store && cd /scratch/store
borg extract --strip-components 3 /srv/backup/homedrive::homedrive-2026-10-27 srv/homedrive/store
/usr/local/bin/homedrive_repair.sh /scratch/store   # stops the server, repairs, starts it
```

Extract to scratch space on another disk (adjust `--strip-components` to
your store path), then pass the extracted store directory. Any backup
that holds the lost objects works, however old, because objects are
named by their content. The repair takes only copies that verify. With
no directory it searches only the store's own quarantine, which is enough
when the disk once failed to read something it now reads. Check SMART
health on the Proxmox host: VM1 sees virtual disks and cannot.

## Using it

- **Backups** store archives with
  `/usr/local/bin/homedrive_import_path.sh <user> <drive path> <file>`.
- **Bulk loads**: mount the source into the container read-only and run
  `podman exec homedrive hd-server import-tree --user U --src /mnt/src`,
  then `verify-tree` with the same arguments. Do not trust an import until
  `verify-tree` is clean, and never retire the source until it is: it
  fails on any file it had to skip (a symbolic link, a special file, a
  name the drive cannot hold), because that file exists only in the
  source. Rename or copy those files so they import, or save them
  elsewhere and pass `--accept-skipped`.
- **music-server** can read an export: point `music_server_music_path` at
  `<homedrive_export_path>/music`.
- **rclone** from other hosts: a `webdav` remote at
  `https://drive.<domain>/dav/<user>` with `vendor = other`, signed in with
  a device token from the web UI's Devices page.

## Importing the previous file service

`homedrive_import.yml` loads the Nextcloud files tree into a drive and
checks it (see [playbooks.md](../playbooks.md#homedrive_importyml)). It is
made for a drive that a sync client has already filled from a copy of the
same files. A run with no tags counts what the drive lacks, by size and
without reading files, stops before writing anything if that is more than
`homedrive_import_max_missing` (100), imports only the missing files, and
checks again that nothing is missing. Old versions are not imported; they
stay in Nextcloud until it is retired.

Before retiring the source, run it with the `full` tag: every source file
must match the drive byte for byte, and `fsck --deep` must be clean. That
reads the whole tree and the whole store, so give its template a long
timeout. Hashes are kept between runs, so a second full run reads only what
changed. A `DIFFERENT` line is a file changed through homedrive since; check
each one before retiring the source. The full output is in
`/var/log/homedrive_import.log`.

## Health

- `podman exec homedrive hd-server fsck --deep` checks every version.
- The web UI's Admin page shows store health, free space, quarantine,
  recovery, and maintenance.
- `/healthz` answers 503 if the store has stopped accepting writes.
